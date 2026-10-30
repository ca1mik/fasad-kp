"""Isolated, consent-gated Serbian campaign using the existing Open Claw mailbox."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import csv
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid, formataddr
import html
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from config import validate_public_demo_url
from mailer import Mailer, MailerError
from openclaw_mail import OpenClawBridge
from state import StateStore

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "sales" / "serbia" / "campaign.json"
LEADS_PATH = ROOT / "sales" / "serbia" / "campaign_leads.csv"
DATA = ROOT / "data" / "serbia-outreach"
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$")
OPT_OUT = re.compile(
    r"(?im)^\s*(?:odjava|одјава|unsubscribe|stop|стоп|отписка)\s*[.!]?\s*$|"
    r"ne\s+(?:želim|zelim|šaljite|saljite)|не\s+(?:желим|шаљите)|odjavite|одјавите|"
    r"obrišite|obrisite|обришите|nemojte|немојте|"
    r"remove\s+me|do\s+not\s+(?:contact|send|email)|don't\s+(?:contact|send|email)|"
    r"не\s+(?:пишите|присылайте)|удалите\s+меня"
)


class CampaignError(RuntimeError):
    pass


def read_config(path: Path = CONFIG_PATH) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or value.get("campaign_id") != "fasad-flow-serbia-v1":
        raise CampaignError("Unexpected campaign configuration")
    for key in ("enabled", "allow_live_on_draft_mailbox"):
        if type(value.get(key)) is not bool:
            raise CampaignError(f"{key} must be a boolean")
    for key, maximum in (("daily_limit", 100), ("hourly_limit", 100), ("max_per_run", 1)):
        number = value.get(key)
        if type(number) is not int or not 1 <= number <= maximum:
            raise CampaignError(f"{key} must be between 1 and {maximum}")
    if not (type(value.get("start_hour")) is int and type(value.get("end_hour")) is int
            and 0 <= value["start_hour"] < value["end_hour"] <= 24):
        raise CampaignError("Invalid sending hours")
    ZoneInfo(value["timezone"])
    for key in ("sender_name", "seller_name", "seller_address", "demo_url", "mailbox", "openclaw_root", "expected_sender"):
        if not isinstance(value.get(key), str) or "\n" in value[key] or "\r" in value[key]:
            raise CampaignError(f"Invalid {key}")
    if not EMAIL_RE.fullmatch(value["expected_sender"]):
        raise CampaignError("expected_sender must be a valid email address")
    if value.get("outbound_transport", "smtp") not in {"smtp", "gmail_https"}:
        raise CampaignError("Unknown outbound_transport")
    if not isinstance(value.get("mailbox_env", ""), str) or any(char in value.get("mailbox_env", "") for char in "\r\n"):
        raise CampaignError("Invalid mailbox_env")
    if not isinstance(value.get("mailbox_profile", ""), str) or any(char in value.get("mailbox_profile", "") for char in "\r\n"):
        raise CampaignError("Invalid mailbox_profile")
    if value.get("mailbox_profile") and value.get("mailbox_env"):
        raise CampaignError("Choose a single Gmail profile")
    mailbox_limits = ("mailbox_daily_limit", "mailbox_hourly_limit")
    if any(key in value for key in mailbox_limits):
        if (not value.get("mailbox_profile") or not value["expected_sender"].casefold().endswith("@gmail.com")
                or value["mailbox"].casefold() != value["expected_sender"].casefold()):
            raise CampaignError("Mailbox limit overrides require the exact shared Gmail profile")
        for key in mailbox_limits:
            if type(value.get(key)) is not int or not 1 <= value[key] <= 100:
                raise CampaignError(f"{key} must be between 1 and 100")
    if value["demo_url"]:
        validate_public_demo_url(value["demo_url"])
    return value


def read_leads(path: Path = LEADS_PATH) -> list[dict[str, str]]:
    required = {"company", "email", "opening_sr", "approved", "consent_at", "consent_evidence", "do_not_contact"}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not required.issubset(reader.fieldnames or []):
            raise CampaignError("Campaign CSV is missing consent/approval columns")
        rows = []
        seen = set()
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise CampaignError("Malformed campaign CSV row")
            row = {key: value.strip() for key, value in row.items()}
            row["email"] = row["email"].casefold()
            if not row["company"] or any(char in row["company"] for char in "\r\n"):
                raise CampaignError("Invalid company name")
            if row["email"] not in seen:
                rows.append(row)
                seen.add(row["email"])
        try:
            return sorted(rows, key=lambda row: int(row.get("priority") or 99))
        except ValueError:
            raise CampaignError("Invalid recipient priority") from None


def consent_problem(lead: dict, now: datetime, zone: ZoneInfo) -> str:
    if lead.get("approved", "").casefold() != "true":
        return "not_approved"
    if not EMAIL_RE.fullmatch(lead.get("email", "")):
        return "invalid_email"
    evidence = lead.get("consent_evidence", "").strip()
    if len(evidence) < 12 or evidence in {lead.get("website"), lead.get("source_url")}:
        return "consent_evidence_missing"
    try:
        consent_at = datetime.fromisoformat(lead.get("consent_at", "").replace("Z", "+00:00"))
        if consent_at.tzinfo is None:
            consent_at = consent_at.replace(tzinfo=zone)
    except (ValueError, TypeError):
        return "consent_date_missing"
    return "consent_in_future" if consent_at > now else ""


def sender_problems(config: dict) -> list[str]:
    problems = [f"{key}_missing" for key in ("sender_name", "seller_name")
                if not config[key].strip() or "[" in config[key]]
    # The initial email identifies the real person and project. It must not invent
    # a local office merely to fill a signature field. Full seller details belong
    # in the separately verified commercial proposal, not a fabricated footer.
    if "[" in config["seller_address"] or "]" in config["seller_address"]:
        problems.append("seller_address_placeholder")
    return problems


def render_message(lead: dict, config: dict, sender_email: str = "") -> tuple[str, str]:
    subject = f"Fasad Flow — poslovna ponuda za {lead['company']}"
    demo = f"\nDemonstracija sa probnim podacima: {config['demo_url']}\n" if config["demo_url"] else ""
    # A product label is not an invented legal entity or local office.
    # Unknown postal details are omitted; supplied address placeholders are blocked.
    signature = "\n".join(part for part in (
        config["sender_name"].strip(),
        f"Projekat: {config['seller_name'].strip()}" if config["seller_name"].strip() else "",
        config["seller_address"].strip(),
        sender_email.strip(),
    ) if part)
    body = (
        "Poslovna ponuda — Fasad Flow\n\nPoštovani,\n\n"
        f"{lead['opening_sr']}\n\n"
        "Razvijamo Fasad Flow za pregled narudžbina, specifikacija, materijala i faza izrade "
        "u proizvodnji frontova i nameštaja po meri. Ideja je da prodaja i radionica vide "
        "istu potvrđenu specifikaciju i trenutno stanje naloga.\n\n"
        "Mogu da pokažem kratku demonstraciju toka od porudžbine do gotovih delova. "
        "Za stvarnu primenu predlažem ograničen pilot na jednom vašem procesu; "
        "obim, potrebne prilagodbe i cenu bismo dogovorili nakon razgovora.\n"
        f"{demo}\nDa li vam odgovara kratak razgovor od 15 minuta?\n\n"
        "Srdačan pozdrav,\n"
        f"{signature}\n\n"
        "Za odjavu od daljih poslovnih poruka odgovorite sa ODJAVA. "
        "Vaš zahtev ćemo poštovati.\n"
    )
    return subject, body


class CampaignState(StateStore):
    def _init(self):
        super()._init()
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS suppression(email TEXT PRIMARY KEY, reason TEXT NOT NULL, at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS replies(reply_id TEXT PRIMARY KEY, email TEXT NOT NULL, at TEXT NOT NULL,
                                                   category TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS campaign_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS delivery_receipts(lead_key TEXT PRIMARY KEY, transport TEXT NOT NULL,
                    provider_id TEXT NOT NULL, thread_id TEXT NOT NULL);
            """)

    def record_receipt(self, key: str, sent, transport: str):
        if sent.provider_id:
            with self._db() as db:
                db.execute("INSERT INTO delivery_receipts(lead_key,transport,provider_id,thread_id) VALUES(?,?,?,?)",
                           (key, transport, sent.provider_id, sent.thread_id))

    def deliveries(self) -> list[dict]:
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM deliveries ORDER BY reserved_at")]

    def suppressed(self) -> set[str]:
        with self._db() as db:
            return {row[0] for row in db.execute("SELECT email FROM suppression")}

    def suppress_existing(self, email: str, now: datetime):
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO suppression(email,reason,at) VALUES(?,?,?)",
                       (email, "matching_message_in_gmail_sent", now.isoformat()))

    def bind_sender(self, sender: str):
        with self._db() as db:
            row = db.execute("SELECT value FROM campaign_meta WHERE key='sender'").fetchone()
            if row and row[0] != sender:
                raise CampaignError("Changing the sender of an existing campaign is blocked")
            db.execute("INSERT OR IGNORE INTO campaign_meta(key,value) VALUES('sender',?)", (sender,))

    def reserve_message(self, lead: dict, message_id: str, now: datetime) -> bool:
        key = "serbia:" + lead["email"]
        with self._db() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO deliveries(lead_key,company,email,reserved_at,message_id,status) VALUES(?,?,?,?,?,'reserved')",
                (key, lead["company"], lead["email"], now.isoformat(), message_id),
            )
            return bool(cursor.rowcount)

    def budget_used(self, now: datetime) -> tuple[int, int]:
        daily = hourly = 0
        for row in self.deliveries():
            reserved = datetime.fromisoformat(row["reserved_at"]).astimezone(now.tzinfo)
            daily += reserved.date() == now.date()
            elapsed = (now.astimezone(timezone.utc) - reserved.astimezone(timezone.utc)).total_seconds()
            hourly += 0 <= elapsed < 3600
        return daily, hourly

    def record_reply(self, message, delivery: dict) -> bool:
        reply_id = message.message_id or ("imap:" + message.id)
        # Only the fresh text, not our own opt-out footer quoted below the reply.
        fresh = re.split(r"(?im)^\s*(?:>|On .+wrote:|From:|Od:|Dana .+napisa|-----Original|Poslovna ponuda — Fasad Flow)",
                         message.body, maxsplit=1)[0]
        category = "opt_out" if OPT_OUT.search(fresh) else "human_reply"
        with self._db() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO replies(reply_id,email,at,category,subject,body) VALUES(?,?,?,?,?,?)",
                (reply_id, delivery["email"], message.received_at.isoformat(), category, message.subject, message.body[:20000]),
            )
            if not cursor.rowcount:
                return False
            if category == "opt_out":
                db.execute("INSERT OR REPLACE INTO suppression(email,reason,at) VALUES(?,?,?)",
                           (delivery["email"], "recipient_opt_out", message.received_at.isoformat()))
            return True

    def replies(self) -> list[dict]:
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM replies ORDER BY at")]


@contextmanager
def worker_lock(path: Path):
    """OS-held lock: a crash releases it; do not expire a lease during SMTP DATA."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise CampaignError("Another Serbian campaign worker is running") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def screening(leads: list[dict], config: dict, state: CampaignState, now: datetime,
              bridge=None) -> tuple[list[dict], list[dict]]:
    emails, domains = bridge.suppression() if bridge else (set(), set())
    emails |= state.suppressed()
    companies = bridge.contacted_companies() if bridge and hasattr(bridge, "contacted_companies") else set()
    zone = ZoneInfo(config["timezone"])
    ready, blocked = [], []
    for lead in leads:
        email_domain = lead["email"].rpartition("@")[2]
        website_domain = (urlparse(lead.get("website", "")).hostname or "").removeprefix("www.").casefold()
        reason = ""
        if (lead.get("do_not_contact", "").casefold() != "false" or lead["email"] in emails
                or email_domain in domains or website_domain in domains):
            reason = "do_not_contact"
        elif state.contains("serbia:" + lead["email"]):
            reason = "already_reserved_or_sent"
        elif lead["company"].casefold() in companies:
            reason = "company_already_contacted_or_stopped"
        else:
            reason = consent_problem(lead, now, zone)
        if reason:
            blocked.append({"company": lead["company"], "email": lead["email"], "reason": reason})
        else:
            ready.append(lead)
    return ready, blocked


def sync_replies(state: CampaignState, bridge, *, since: date | None = None,
                 header_first: bool = False) -> int:
    originals = {row["message_id"]: row for row in state.deliveries() if row["message_id"]}
    if not originals:
        return 0
    count = 0
    messages = (bridge.mailer.fetch_replies(set(originals), since=since, header_first=header_first) if since or header_first
                else bridge.mailer.fetch_replies(set(originals)))
    for message in messages:
        if message.automated:
            continue
        delivery = next((originals[mid] for mid in (message.in_reply_to, *message.references)
                         if mid in originals), None)
        # Match thread identifiers; never use a guessed address/domain to match a reply.
        if delivery and state.record_reply(message, delivery):
            count += 1
    return count


def configured_bridge(config: dict):
    bridge = OpenClawBridge(Path(config["openclaw_root"]), config["mailbox"],
                           f"{config['sender_name']} — {config['seller_name']}",
                           config.get("mailbox_env", ""), config.get("outbound_transport", "smtp"), DATA,
                           config.get("mailbox_profile", ""))
    if "mailbox_daily_limit" in config:
        bridge.apply_mailbox_limits(config["mailbox_daily_limit"], config["mailbox_hourly_limit"])
    if getattr(bridge.mailer, 'outbound_transport', '') == 'gmail_https':
        bridge.mailer.timeout = max(bridge.mailer.timeout, 45)
    return bridge


def rate_problem(config, state, bridge, now):
    daily, hourly = state.budget_used(now)
    shared = bridge.shared_budget(now) if hasattr(bridge, "shared_budget") else {
        "daily": 0, "hourly": 0, "last_attempt": None, "uncertain": 0}
    if shared["uncertain"]:
        return "shared_mailbox_uncertain_attempt", shared
    if daily >= config["daily_limit"] or hourly >= config["hourly_limit"]:
        return "campaign_rate_limit", shared
    if daily + shared["daily"] >= bridge.settings.daily_limit or hourly + shared["hourly"] >= bridge.settings.hourly_limit:
        return "shared_mailbox_rate_limit", shared
    stamps = [row["reserved_at"] for row in state.deliveries()]
    if shared["last_attempt"]:
        stamps.append(shared["last_attempt"])
    if any((now.astimezone(timezone.utc) - datetime.fromisoformat(stamp).astimezone(timezone.utc)).total_seconds()
           < bridge.settings.min_pause_seconds for stamp in stamps):
        return "campaign_min_pause", shared
    return "", shared


def cycle(config: dict, leads: list[dict], state: CampaignState, data: Path,
          bridge_factory=None, now: datetime | None = None, leads_loader=None, manual_now: bool = False) -> dict:
    explicit_now = now
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(config["timezone"]))
    result: dict[str, Any] = {"checked_at": now.isoformat(), "sent": 0, "replies": 0}
    if not config["enabled"]:
        return {**result, "status": "disabled"}
    with ExitStack() as locks:
        locks.enter_context(worker_lock(data / "worker.lock"))
        if (data / "STOP").exists():
            return {**result, "status": "stopped"}
        direct_journal = data / "gmail-deliveries.jsonl"
        if direct_journal.exists() and direct_journal.read_text(encoding="utf-8-sig").strip():
            return {**result, "status": "direct_gmail_journal_requires_reconciliation"}
        if any(row["status"] != "committed" for row in state.deliveries()):
            (data / "STOP").write_text("Unresolved delivery reservation; manual reconciliation required.\n", encoding="utf-8")
            return {**result, "status": "unresolved_delivery_stopped"}
        if sender_problems(config):
            return {**result, "status": "blocked", "reasons": sender_problems(config)}
        bridge = (bridge_factory(Path(config["openclaw_root"]), config["mailbox"],
                                 f"{config['sender_name']} — {config['seller_name']}")
                  if bridge_factory is not None else configured_bridge(config))
        if hasattr(bridge, "mailbox_guard"):
            locks.enter_context(bridge.mailbox_guard())
        if bridge.mailer.address.casefold() != config["expected_sender"].casefold():
            return {**result, "status": "blocked", "reasons": ["sender_mismatch"]}
        if bridge.settings.draft_only and not config["allow_live_on_draft_mailbox"]:
            return {**result, "status": "blocked", "reasons": ["mailbox_draft_only"]}
        if not bridge.settings.smtp_configured or not bridge.settings.imap_configured:
            return {**result, "status": "blocked", "reasons": ["mailbox_not_configured"]}
        state.bind_sender(bridge.mailer.address)
        if isinstance(bridge.mailer, Mailer):
            prior = state.deliveries()
            reply_since = (min(datetime.fromisoformat(row['reserved_at']) for row in prior)
                           - timedelta(days=1)).date() if prior else None
            result["replies"] = sync_replies(state, bridge, since=reply_since, header_first=True)
        else:
            result["replies"] = sync_replies(state, bridge)
        ready, blocked = screening(leads, config, state, now, bridge)
        result.update(eligible=len(ready), blocked=len(blocked))
        result["manual_now"] = manual_now
        if not manual_now and (now.weekday() >= 5 or not config["start_hour"] <= now.hour < config["end_hour"]):
            return {**result, "status": "outside_sending_hours"}
        rate, shared = rate_problem(config, state, bridge, now)
        result["other_campaign_attempts"] = shared
        if rate:
            return {**result, "status": rate}
        if not ready:
            return {**result, "status": "no_approved_recipients"}
        # A failed preflight must not reserve a company or send a message.
        bridge.mailer.healthcheck()
        now = (explicit_now or datetime.now(timezone.utc)).astimezone(ZoneInfo(config["timezone"]))
        if not manual_now and (now.weekday() >= 5 or not config["start_hour"] <= now.hour < config["end_hour"]):
            return {**result, "status": "outside_sending_hours"}
        lead = ready[0]  # One message per cycle; the scheduler provides spacing.
        if (data / "STOP").exists():
            return {**result, "status": "stopped"}
        # Re-read global stop lists immediately before handing the message to SMTP.
        if leads_loader is not None:
            lead = next((row for row in leads_loader() if row["email"] == lead["email"]), None)
            if lead is None:
                return {**result, "status": "recipient_removed_before_send"}
        current_ready, _ = screening([lead], config, state, now, bridge)
        if not current_ready:
            return {**result, "status": "recipient_blocked_before_send"}
        subject, body = render_message(lead, config, bridge.mailer.address)
        if (hasattr(bridge.mailer, "has_sent_message")
                and bridge.mailer.has_sent_message(lead["email"], subject)):
            state.suppress_existing(lead["email"], now)
            return {**result, "status": "already_in_gmail_sent", "email": lead["email"]}
        if (data / "STOP").exists():
            return {**result, "status": "stopped"}
        # The Sent lookup may take time: re-check actual time, CSV, opt-outs and
        # the combined budget while still holding both workers' mailbox lock.
        now = (explicit_now or datetime.now(timezone.utc)).astimezone(ZoneInfo(config["timezone"]))
        if not manual_now and (now.weekday() >= 5 or not config["start_hour"] <= now.hour < config["end_hour"]):
            return {**result, "status": "outside_sending_hours"}
        if leads_loader is not None:
            lead = next((row for row in leads_loader() if row["email"] == lead["email"]), None)
        if lead is None or not screening([lead], config, state, now, bridge)[0]:
            return {**result, "status": "recipient_blocked_before_send"}
        subject, body = render_message(lead, config, bridge.mailer.address)
        rate, shared = rate_problem(config, state, bridge, now)
        result["other_campaign_attempts"] = shared
        if rate:
            return {**result, "status": rate}
        message_id = make_msgid(domain=bridge.mailer.address.rpartition("@")[2])
        if not state.reserve_message(lead, message_id, now):
            return {**result, "status": "already_reserved"}
        key = "serbia:" + lead["email"]
        try:
            sent = bridge.mailer.send(lead["email"], subject, body, message_id=message_id)
            state.record_receipt(key, sent, getattr(bridge.mailer, "outbound_transport", "smtp"))
            state.mark_sent(key, sent.message_id or message_id, now)
            state.mark_committed(key)
        except Exception:
            # Unknown outcome after SMTP DATA: quarantine, stop, never retry automatically.
            (data / "STOP").write_text("Uncertain send outcome; inspect the mailbox before resuming.\n", encoding="utf-8")
            state.mark_uncertain(key, "transport_or_commit_failed; manual reconciliation required")
            return {**result, "status": "uncertain_stopped", "email": lead["email"]}
        return {**result, "status": ("gmail_api_accepted" if getattr(bridge.mailer, "outbound_transport", "smtp")
                                     == "gmail_https" else "smtp_accepted"), "sent": 1,
                "email": lead["email"], "message_id": sent.message_id or message_id,
                "provider_id": sent.provider_id, "thread_id": sent.thread_id}


def export_previews(leads: list[dict], config: dict, destination: Path, sender: str = "",
                    registry_name: str = "campaign_leads.csv") -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    cards = []
    for number, lead in enumerate(leads, 1):
        subject, body = render_message(lead, config, sender)
        message = EmailMessage()
        message["To"] = lead["email"]
        message["From"] = formataddr((f"{config['sender_name']} — {config['seller_name']}", sender or "draft@sender.invalid"))
        message["Subject"] = subject
        message.set_content(body)
        filename = f"{number:02d}.eml"
        (destination / filename).write_bytes(message.as_bytes())
        cards.append(f'<article><h2>{html.escape(lead["company"])}</h2><p>{html.escape(lead["email"])}</p>'
                     f'<h3>{html.escape(subject)}</h3><pre>{html.escape(body)}</pre>'
                     f'<a href="{filename}">Скачать черновик .eml</a></article>')
    index = destination / "index.html"
    index.write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Fasad Flow: черновики</title>'
                     '<style>body{max-width:880px;margin:35px auto;padding:20px;font:16px system-ui;background:#f4f7f6}'
                     'article{background:white;padding:25px;margin:20px 0;border-radius:12px}pre{white-space:pre-wrap;'
                     'font:15px/1.6 system-ui}h2{color:#14584e}</style><h1>Сербия: черновики писем</h1>'
                     '<p>Это локальные черновики, не отправка. Статус согласий и исключения смотрите в '
                     f'{html.escape(registry_name)}; не все показанные ниже письма допущены к отправке. '
                     'Инструкция: docs/OUTREACH_HANDOFF.md.</p>'
                     + ''.join(cards) + '</html>', encoding="utf-8")
    return {"prepared": len(leads), "sent": 0, "preview": str(index)}


def main() -> int:
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "status", "mail-check", "activate", "pause", "cycle", "replies"))
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--send-now", action="store_true", help="Explicit manual cycle outside business hours; all limits still apply")
    args = parser.parse_args()
    try:
        if args.send_now and args.command != "cycle":
            raise CampaignError("--send-now is allowed only for an explicitly requested cycle")
        config = read_config()
        leads = read_leads()
        DATA.mkdir(parents=True, exist_ok=True)
        state = CampaignState(DATA / "campaign.sqlite3")
        now = datetime.now(timezone.utc).astimezone(ZoneInfo(config["timezone"]))
        if args.command == "prepare":
            # Preparing files must work without credentials and cannot touch another mailbox.
            result = export_previews(leads, config, DATA / "previews", config["expected_sender"])
        elif args.command == "pause":
            if not (DATA / "STOP").exists():
                (DATA / "STOP").write_text("paused_by_operator\n", encoding="utf-8")
            config["enabled"] = False
            CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = {"status": "disabled", "sent": 0}
        elif args.command == "cycle":
            result = cycle(config, leads, state, DATA, leads_loader=read_leads, manual_now=args.send_now)
            (DATA / "last_cycle.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        elif args.command == "replies":
            result = {"replies": state.replies(), "suppressed": sorted(state.suppressed())}
        elif args.command == "status":
            bridge = None
            transport_error = None
            try:
                bridge = configured_bridge(config)
            except MailerError as exc:
                transport_error = str(exc)
            ready, blocked = screening(leads, config, state, now, bridge)
            result = {"enabled": config["enabled"], "expected_sender": config["expected_sender"],
                      "mailbox": bridge.summary() if bridge else None, "transport_error": transport_error,
                      "global_suppression_checked": bridge is not None, "total": len(leads),
                      "approved_local": len(ready), "blocked": blocked, "sender_problems": sender_problems(config),
                      "stopped": (DATA / "STOP").exists(), "ledger": state.report(),
                      "other_campaign_attempts": bridge.shared_budget(now) if bridge else None,
                      "last_cycle": json.loads((DATA / "last_cycle.json").read_text(encoding="utf-8"))
                      if (DATA / "last_cycle.json").exists() else None}
            if bridge and bridge.mailer.address.casefold() != config["expected_sender"].casefold():
                result["transport_error"] = "sender_mismatch"
            elif bridge and config.get("outbound_transport") == "gmail_https" and not bridge.summary()["oauth_connected"]:
                result["transport_error"] = "Gmail HTTPS OAuth is not connected; open connect_fasad_gmail.cmd"
        else:
            bridge = configured_bridge(config)
            if bridge.mailer.address.casefold() != config["expected_sender"].casefold():
                raise CampaignError("Configured mailbox does not match expected_sender; sending is blocked")
            ready, blocked = screening(leads, config, state, now, bridge)
            if args.command == "mail-check":
                bridge.mailer.healthcheck()
                result = {"mailbox": bridge.summary(), "mail_login": "ok", "sent": 0}
            else:
                if not args.confirm_live:
                    raise CampaignError("Activation requires --confirm-live")
                if sender_problems(config):
                    raise CampaignError("Fill sender_name and seller_name; remove any address placeholder before activation")
                if not ready:
                    raise CampaignError("No approved recipients with dated consent evidence")
                stop_path = DATA / "STOP"
                if stop_path.exists() and stop_path.read_text(encoding="utf-8").strip() != "paused_by_operator":
                    raise CampaignError("STOP flag requires manual inspection; activation cannot clear an uncertain send")
                bridge.mailer.healthcheck()
                config.update(enabled=True, allow_live_on_draft_mailbox=True)
                CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                if stop_path.exists():
                    stop_path.unlink()
                result = {"status": "activated", "eligible": len(ready), "sent": 0,
                          "note": "Only this campaign is authorized; Open Claw global draft settings remain unchanged"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        safe = str(exc) if isinstance(exc, (CampaignError, MailerError)) else type(exc).__name__
        print(json.dumps({"status": "error", "error": safe, "sent": 0}, ensure_ascii=False))
        # Scheduled pythonw runs have no terminal. Persist only a sanitized error.
        if args.command == "cycle":
            DATA.mkdir(parents=True, exist_ok=True)
            (DATA / "last_cycle.json").write_text(json.dumps(
                {"status": "error", "error": safe, "sent": 0,
                 "checked_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
