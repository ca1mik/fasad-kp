from __future__ import annotations

from datetime import date, datetime
from email.utils import make_msgid
import json
import re
from typing import Any, Protocol

from config import Config
from logger import EventLogger
from models import IncomingMessage, Lead, SendResult
from personalize import MessageTemplateError, render_message
from replies import classify_reply
from state import StateStore


class SheetsPort(Protocol):
    def read_leads(self) -> list[Lead]: ...
    def update_lead(self, lead: Lead, updates: dict[str, str]) -> None: ...
    def healthcheck(self) -> dict[str, Any]: ...


class MailPort(Protocol):
    def send(self, lead: Lead, subject: str, body: str, *, message_id: str) -> SendResult: ...
    def fetch_replies(self, original_ids: set[str]) -> list[IncomingMessage]: ...
    def healthcheck(self) -> dict[str, Any]: ...


class SafetyError(RuntimeError):
    pass


def is_eligible(lead: Lead) -> bool:
    email = lead.email
    return (
        lead.get("Производство подтверждено").casefold() == "да"
        and lead.get("Статус").casefold() == "новый"
        and bool(email)
        and "@" in email
        and not re.search(r"\s", email)
        and not lead.get("Дата 1-го письма")
        and not lead.get("OpenClaw Message-ID")
    )


def select_eligible(leads: list[Lead], blocked_keys: set[str] | None = None) -> list[Lead]:
    blocked = blocked_keys or set()
    result: list[Lead] = []
    seen: set[str] = set()
    duplicate_keys = {lead.key for lead in leads if lead.key in seen or seen.add(lead.key)}
    for lead in leads:
        if lead.key in duplicate_keys or lead.key in blocked:
            continue
        if is_eligible(lead):
            result.append(lead)
    return result


def _sheet_date(value: str, timezone) -> date | None:
    value = value.strip()
    if not value:
        return None
    candidates = (value, value.replace("Z", "+00:00"))
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone)
            return parsed.date()
        except ValueError:
            pass
    for pattern in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    return None


def daily_sent_keys(leads: list[Lead], state: StateStore, day: date, timezone) -> set[str]:
    keys = state.sent_keys_on(day)
    keys.update(
        lead.key for lead in leads if _sheet_date(lead.get("Дата 1-го письма"), timezone) == day
    )
    return keys


class OutreachWorkflow:
    def __init__(
        self,
        config: Config,
        sheets: SheetsPort,
        mailer: MailPort,
        state: StateStore,
        logger: EventLogger,
        *,
        output=print,
    ):
        self.config = config
        self.sheets = sheets
        self.mailer = mailer
        self.state = state
        self.logger = logger
        self.output = output

    def _now(self) -> datetime:
        return datetime.now(self.config.timezone)

    def reconcile_pending(self, leads: list[Lead]) -> int:
        by_key: dict[str, list[Lead]] = {}
        for lead in leads:
            by_key.setdefault(lead.key, []).append(lead)
        repaired = 0
        for record in self.state.pending():
            matches = by_key.get(record["lead_key"], [])
            if len(matches) != 1:
                self.logger.event(
                    company=record["company"], email=record["email"], operation="reconcile",
                    result="blocked", message_id=record.get("message_id", ""),
                    error="lead key is missing or ambiguous in sheet",
                )
                continue
            updates = {
                "Статус": "Письмо отправлено",
                "Дата 1-го письма": record["sent_at"],
                "OpenClaw Message-ID": record["message_id"],
            }
            try:
                self.sheets.update_lead(matches[0], updates)
                self.state.mark_committed(record["lead_key"])
                repaired += 1
            except Exception as exc:
                self.logger.event(
                    company=record["company"], email=record["email"], operation="reconcile",
                    result="error", message_id=record.get("message_id", ""), error=exc,
                )
        return repaired

    def healthcheck(self) -> dict[str, Any]:
        self.config.validate_external()
        sheet = self.sheets.healthcheck()
        mail = self.mailer.healthcheck()
        return {
            "env": "ok",
            "demo_url": self.config.demo_url,
            "sheet": sheet,
            "mail": mail,
            "daily_send_limit": self.config.daily_send_limit,
            "dry_run": self.config.dry_run,
            "state": str(self.state.path),
        }

    def dry_run(self) -> dict[str, int]:
        leads = self.sheets.read_leads()
        today = self._now().date()
        sent_today = daily_sent_keys(leads, self.state, today, self.config.timezone)
        remaining = max(0, self.config.daily_send_limit - len(sent_today))
        eligible = select_eligible(leads, {lead.key for lead in leads if self.state.contains(lead.key)})
        shown = 0
        for lead in eligible[:remaining]:
            try:
                subject, body = render_message(lead, self.config.demo_url)
            except MessageTemplateError as exc:
                self.logger.event(company=lead.company, email=lead.email, operation="dry-run", result="skip", error=exc)
                continue
            self.output(
                "\n".join((
                    "--- DRY RUN ---",
                    f"Компания: {lead.company}",
                    f"Адрес: {lead.email}",
                    f"Тема: {subject}",
                    "Текст:",
                    body,
                ))
            )
            shown += 1
        summary = {"eligible": len(eligible), "shown": shown, "sent_today": len(sent_today), "remaining": remaining}
        return summary

    def send_new(self) -> dict[str, int]:
        if self.config.dry_run:
            raise SafetyError("DRY_RUN=true: реальная отправка заблокирована; используйте dry-run")
        leads = self.sheets.read_leads()
        repaired = self.reconcile_pending(leads)
        if repaired:
            leads = self.sheets.read_leads()
        now = self._now()
        sent_today = daily_sent_keys(leads, self.state, now.date(), self.config.timezone)
        remaining = max(0, self.config.daily_send_limit - len(sent_today))
        blocked = {lead.key for lead in leads if self.state.contains(lead.key)}
        candidates = select_eligible(leads, blocked)
        sent = 0
        errors = 0
        for lead in candidates[:remaining]:
            try:
                subject, body = render_message(lead, self.config.demo_url)
            except MessageTemplateError as exc:
                self.logger.event(company=lead.company, email=lead.email, operation="send-new", result="skip", error=exc)
                errors += 1
                continue
            reserved_at = self._now()
            if not self.state.reserve(lead.key, lead.company, lead.email, reserved_at):
                continue
            domain = self.config.mail_address.rpartition("@")[2] or None
            message_id = make_msgid(domain=domain)
            try:
                result = self.mailer.send(lead, subject, body, message_id=message_id)
                actual_id = result.message_id or message_id
                sent_at = self._now()
                self.state.mark_sent(lead.key, actual_id, sent_at)
            except Exception as exc:
                self.state.mark_uncertain(lead.key, str(exc))
                self.logger.event(
                    company=lead.company, email=lead.email, operation="send-new",
                    result="uncertain", message_id=message_id, error=exc,
                )
                errors += 1
                continue
            try:
                self.sheets.update_lead(lead, {
                    "Статус": "Письмо отправлено",
                    "Дата 1-го письма": sent_at.isoformat(),
                    "OpenClaw Message-ID": actual_id,
                })
                self.state.mark_committed(lead.key)
                self.logger.event(
                    company=lead.company, email=lead.email, operation="send-new",
                    result="sent", message_id=actual_id, error="",
                )
                sent += 1
            except Exception as exc:
                self.logger.event(
                    company=lead.company, email=lead.email, operation="sheet-commit",
                    result="pending", message_id=actual_id, error=exc,
                )
                errors += 1
                break
        return {"sent": sent, "errors": errors, "remaining_before_run": remaining, "reconciled": repaired}

    def sync_replies(self) -> dict[str, int]:
        leads = self.sheets.read_leads()
        original_to_lead = {
            _message_id(lead.get("OpenClaw Message-ID")): lead
            for lead in leads if lead.get("OpenClaw Message-ID")
        }
        messages = self.mailer.fetch_replies(set(original_to_lead))
        processed = 0
        planned = 0
        for message in sorted(messages, key=lambda item: item.received_at):
            reply_id = message.id or message.message_id
            if not reply_id or message.automated or self.state.reply_processed(reply_id):
                continue
            target = _find_target(message, original_to_lead)
            if target is None:
                continue
            updates = classify_reply(message.body, message.received_at)
            if self.config.dry_run:
                self.output(json.dumps({"company": target.company, "email": target.email, "updates": updates}, ensure_ascii=False))
                planned += 1
                continue
            try:
                self.sheets.update_lead(target, updates)
                self.state.mark_reply_processed(reply_id, target.key, self._now())
                self.logger.event(
                    company=target.company, email=target.email, operation="sync-replies",
                    result="updated", message_id=message.message_id, error="",
                )
                processed += 1
            except Exception as exc:
                self.logger.event(
                    company=target.company, email=target.email, operation="sync-replies",
                    result="error", message_id=message.message_id, error=exc,
                )
        return {"processed": processed, "planned": planned, "fetched": len(messages)}


def _message_id(value: str) -> str:
    return value.strip().strip("<>").casefold()


def _find_target(message: IncomingMessage, originals: dict[str, Lead]) -> Lead | None:
    candidates = [message.in_reply_to, *message.references]
    for candidate in candidates:
        lead = originals.get(_message_id(candidate))
        if lead:
            return lead
    if message.thread_id:
        return originals.get(_message_id(message.thread_id))
    return None
