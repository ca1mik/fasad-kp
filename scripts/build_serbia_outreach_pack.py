"""Build a private, offline handoff archive; never connect to mail or send it."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr
import hashlib
import html
import io
import json
from pathlib import Path
import sqlite3
import sys
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from serbia_outreach import (  # noqa: E402
    CampaignError, consent_problem, read_config, read_leads, render_message, sender_problems,
)


def local_exclusions(data: Path) -> dict[str, str]:
    """Read existing journals only. A previous attempt is not safe to retry."""
    reasons = {}
    database = data / "campaign.sqlite3"
    if database.is_file():
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            for (email,) in connection.execute("SELECT email FROM deliveries"):
                reasons[email.casefold()] = "previous_local_attempt"
            for (email,) in connection.execute("SELECT email FROM suppression"):
                reasons[email.casefold()] = "recipient_opt_out"
        finally:
            connection.close()
    journal = data / "gmail-deliveries.jsonl"
    if journal.is_file():
        for line in journal.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or not isinstance(value.get("email"), str) or not value["email"]:
                raise CampaignError("Gmail journal has an invalid record; reconcile it before packing")
            reasons[value["email"].casefold()] = "previous_gmail_record_requires_reconciliation"
    return reasons


def build_pack(root: Path, destination: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise CampaignError("Pack timestamp must include a timezone")
    config = read_config(root / "sales" / "serbia" / "campaign.json")
    if sender_problems(config):
        raise CampaignError("Sender signature is not complete or has placeholders")
    leads = read_leads(root / "sales" / "serbia" / "campaign_leads.csv")
    local = local_exclusions(root / "data" / "serbia-outreach")
    ready, excluded = [], []
    for lead in leads:
        reason = ("do_not_contact" if lead["do_not_contact"].casefold() != "false" else
                  local.get(lead["email"], "") or consent_problem(lead, now, ZoneInfo(config["timezone"])))
        if reason:
            excluded.append({"company": lead["company"], "email": lead["email"], "reason": reason})
        else:
            ready.append(lead)
    if not ready:
        raise CampaignError("No locally eligible recipients; no archive created")

    # Explicit allowlist: never archive the workspace, .env, passwords or reply DB.
    materials = {
        "OUTREACH_HANDOFF.md": root / "docs" / "OUTREACH_HANDOFF.md",
        "market-validation-2026-09-28.md": root / "sales" / "serbia" / "market-validation-2026-09-28.md",
        "consent-confirmation-2026-09-28.md": root / "sales" / "serbia" / "consent-confirmation-2026-09-28.md",
    }
    contents = {name: path.read_bytes() for name, path in materials.items()}
    records, cards = [], []
    for number, lead in enumerate(ready, 1):
        subject, body = render_message(lead, config, config["expected_sender"])
        if "[" in subject or "[" in body or "]" in body:
            raise CampaignError("Unfilled placeholder in email; no archive created")
        message = EmailMessage(policy=SMTP)
        message["From"] = formataddr((config["sender_name"], config["expected_sender"]))
        message["To"] = lead["email"]
        message["Reply-To"] = config["expected_sender"]
        message["Subject"] = subject
        message.set_content(body)
        eml, text = f"messages/{number:02d}.eml", f"messages/{number:02d}.txt"
        contents[eml] = message.as_bytes()
        contents[text] = f"From: {config['expected_sender']}\nTo: {lead['email']}\nSubject: {subject}\n\n{body}".encode("utf-8")
        records.append({"number": number, "company": lead["company"], "email": lead["email"],
                        "subject": subject, "source_url": lead.get("source_url", ""), "eml": eml, "text": text,
                        "eml_sha256": hashlib.sha256(contents[eml]).hexdigest()})
        cards.append(f'<article><h2>{number:02d}. {html.escape(lead["company"])}</h2>'
                     f'<p>{html.escape(lead["email"])}</p><h3>{html.escape(subject)}</h3>'
                     f'<pre>{html.escape(body)}</pre><p><a href="{eml}">EML</a> · '
                     f'<a href="{text}">Текст</a></p></article>')
    table = io.StringIO(newline="")
    writer = csv.DictWriter(table, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)
    contents["recipients.csv"] = table.getvalue().encode("utf-8-sig")
    manifest = {
        "schema_version": 1, "campaign_id": config["campaign_id"], "created_at": now.isoformat(),
        "sender": config["expected_sender"], "sender_name": config["sender_name"],
        "prepared": len(records), "sent_by_pack_builder": 0, "delivery_status": "not_sent_by_pack_builder",
        "preflight_required": ["verify_actual_mail_account", "check_current_global_suppression",
                               "reconcile_local_journals", "check_mailbox_sent_folder", "respect_sending_limits"],
        "limits": {key: config[key] for key in ("daily_limit", "hourly_limit", "max_per_run",
                                                  "timezone", "start_hour", "end_hour")},
        "consent_basis": "Owner attestation; original recipient dates/channels were not supplied",
        "attachments": [], "recipients": records, "excluded": excluded,
    }
    contents["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    contents["README.txt"] = (
        f"Fasad Flow — Сербия. {len(records)} персональных черновиков, исключено {len(excluded)}.\n"
        "Сборка офлайн: ни одного письма не отправляет и не создаёт черновики в Gmail.\n"
        f"Отправитель: {config['sender_name']} <{config['expected_sender']}>.\n"
        "Откройте index.html, затем OUTREACH_HANDOFF.md. Перед отправкой перепроверьте аккаунт,\n"
        "стоп-листы и исходящие: сохранённый архив не подтверждает актуальное состояние почты.\n"
        "Не отправляйте весь архив адресатам. Каждому предназначено только его отдельное письмо.\n"
        "Не включайте SMTP и прямую Gmail-рассылку одновременно. VPN не отключать.\n"
        "В архиве нет КП с placeholders, секретов, паролей, .env или базы ответов.\n"
        "Материалы содержат частные сведения о подтверждении пользователя; не публиковать архив.\n"
    ).encode("utf-8")
    contents["index.html"] = (
        '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Fasad Flow — письма Сербия</title>'
        '<style>body{max-width:920px;margin:30px auto;padding:20px;font:16px system-ui;background:#f4f7f6}'
        'article{background:white;padding:24px;margin:20px 0;border-radius:12px}'
        'pre{white-space:pre-wrap;font:15px/1.6 system-ui}h2{color:#14584e}</style>'
        f'<h1>Fasad Flow: {len(records)} персональных писем</h1>'
        '<p>Это локальные черновики, не отправка. Согласие владельцем подтверждено; '
        'перед отправкой нужны рабочий почтовый доступ и проверка исходящих/стоп-листов.</p>'
        '<p><a href="OUTREACH_HANDOFF.md">Инструкция передачи</a> · '
        '<a href="recipients.csv">Получатели</a> · <a href="manifest.json">Статус и проверки</a></p>'
        + "".join(cards) + '</html>'
    ).encode("utf-8")

    archive = destination.with_name(destination.name + ".zip")
    if destination.exists() or archive.exists():
        raise CampaignError("Pack destination already exists; choose another --output, no files overwritten")
    destination.mkdir(parents=True, exist_ok=False)
    for name, payload in contents.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    with ZipFile(archive, "x", compression=ZIP_DEFLATED) as zipped:
        for name, payload in contents.items():
            zipped.writestr(name, payload)
    return {"prepared": len(records), "excluded": excluded, "sent": 0,
            "directory": str(destination), "archive": str(archive), "preview": str(destination / "index.html")}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "data" / "serbia-outreach" / "outreach-pack-2026-09-28")
    args = parser.parse_args()
    try:
        print(json.dumps(build_pack(ROOT, args.output.resolve()), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, CampaignError) else type(exc).__name__
        print(json.dumps({"status": "error", "error": message, "sent": 0}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
