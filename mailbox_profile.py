"""Read-only shared mailbox history; never reuse another campaign's queue."""

from contextlib import contextmanager, closing
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sqlite3

from mailer import MailerError


def read_profile(path: Path, sender: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if (value.get("mail_provider") != "gmail" or value.get("outbound_transport") != "gmail_api"
                or value.get("sender_confirmed") is not True
                or str(value.get("sender_email", "")).casefold() != sender):
            raise ValueError
        return {"root": path.resolve().parent, "sender_email": sender, "mail_provider": "gmail",
                "agent_workdir": value["agent_workdir"]}
    except Exception:
        raise MailerError("The shared Open Claw Gmail profile is invalid or belongs to another sender") from None


def snapshot(root: Path) -> dict:
    path = root / "campaign.sqlite3"
    if not path.is_file():
        raise MailerError("Shared mailbox history is missing; sending is blocked")
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            attempts = [dict(row) for row in db.execute(
                "SELECT company,email,attempted_at,state FROM outbound")]
            stops = [dict(row) for row in db.execute("SELECT email,company FROM stops")]
        if any(row["state"] not in {"sent", "rejected", "sending", "unknown"} for row in attempts):
            raise ValueError
        stopped_companies = {row["company"].strip().casefold() for row in stops if row["company"]}
        blocked_emails = {row["email"].strip().casefold() for row in stops}
        blocked_emails.update(row["email"].strip().casefold() for row in attempts
                              if row["state"] in {"sent", "sending", "unknown"}
                              or row["company"].strip().casefold() in stopped_companies)
        blocked_companies = stopped_companies | {
            row["company"].strip().casefold() for row in attempts
            if row["state"] in {"sent", "sending", "unknown"}}
        from shared_gmail_control import CONTROL, read_control, db_records
        if CONTROL.is_file():
            control = read_control()
            if Path(control["profile_root"]).resolve() == root.resolve():
                own_serbia = Path(control["fasad_serbia_journal"]).resolve()
                for journal in control["journals"]:
                    candidate = Path(journal).resolve()
                    if candidate == path.resolve() or candidate == own_serbia:
                        continue
                    for row in db_records(candidate):
                        blocked_emails.add(row["email"].casefold())
                        blocked_companies.add(row["company"].casefold())
        return {"attempts": attempts, "emails": blocked_emails, "companies": blocked_companies}
    except Exception:
        raise MailerError("Shared mailbox history or opt-outs are unreadable; sending is blocked") from None


def budget(root: Path, now: datetime) -> dict:
    # The separately registered Gmail envelope includes all active journals and
    # a fresh read-only Sent reconciliation, while this caller adds its own
    # Fasad Serbia queue below. Keep its existing config and history intact.
    from shared_gmail_control import CONTROL, read_control, other_for_serbia
    if CONTROL.is_file() and Path(read_control()["profile_root"]).resolve() == root.resolve():
        return other_for_serbia(now)
    history = snapshot(root)
    stamps = []
    try:
        for row in history["attempts"]:
            stamp = datetime.fromisoformat(row["attempted_at"])
            if stamp.tzinfo is None or stamp > now:
                raise ValueError
            stamps.append(stamp)
    except Exception:
        raise MailerError("Shared mailbox attempt timestamps are invalid; sending is blocked") from None
    return {"daily": sum(stamp.astimezone(now.tzinfo).date() == now.date() for stamp in stamps),
            "hourly": sum(0 <= (now.astimezone(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
                          < 3600 for stamp in stamps),
            "last_attempt": max(stamps).isoformat() if stamps else None,
            "uncertain": sum(row["state"] in {"sending", "unknown"} for row in history["attempts"]),
            "total_attempts": len(stamps),
            "total_sent": sum(row["state"] == "sent" for row in history["attempts"])}


@contextmanager
def guard(root: Path, campaign_id: str = "fasad-flow-serbia-v1"):
    # Reuse the existing worker's lock name only for mailbox coordination. No
    # changes to its queue, configuration, templates, or scheduled task.
    locks = importlib.import_module("src.runtime_lock")
    try:
        lock = locks.acquire_runtime_lock(root, "otpremaops_campaign",
                                         metadata={"owner_campaign": campaign_id})
    except locks.RuntimeLockError:
        raise MailerError("Another Open Claw mailbox worker is running; no email attempted") from None
    try:
        yield
    finally:
        lock.release()
