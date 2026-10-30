from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from config import Config
from logger import EventLogger
from models import IncomingMessage, Lead, SendResult
from state import StateStore
from workflow import OutreachWorkflow, SafetyError


def config(tmp_path: Path, *, dry_run: bool = False, limit: int = 15) -> Config:
    return Config(
        mail_provider="gmail", mail_address="sender@example.com", mail_auth_mode="app_password",
        mail_app_password="secret", mail_display_name="", smtp_host="", smtp_port=587,
        smtp_security="starttls", imap_host="", imap_port=993, imap_folder="INBOX",
        oauth_client_id="", oauth_client_secret="", oauth_refresh_token="", oauth_token_url="",
        google_service_account_json="{}", google_oauth_client_id="", google_oauth_client_secret="",
        google_oauth_refresh_token="", google_sheet_id="sheet", google_sheet_name="Лиды",
        demo_url="https://demo.example.test", daily_send_limit=limit, dry_run=dry_run,
        enable_followups=False, timezone_name="Europe/Moscow", state_path=tmp_path / "state.sqlite3",
        log_path=tmp_path / "events.jsonl", http_timeout=30,
    )


def make_lead(row: int = 2, email: str = "lead@example.com") -> Lead:
    return Lead(row, {
        "Компания": f"Компания {row}", "E-mail": email, "Производство подтверждено": "Да",
        "Статус": "Новый", "Дата 1-го письма": "", "OpenClaw Message-ID": "",
        "Тема письма": "Короткая тема", "Текст письма": "Здравствуйте. Демо: {DEMO_URL}",
    })


class FakeSheets:
    def __init__(self, leads: list[Lead], *, fail_update: bool = False):
        self.leads = leads
        self.fail_update = fail_update
        self.updates: list[dict[str, str]] = []

    def read_leads(self) -> list[Lead]: return self.leads
    def healthcheck(self): return {"ok": True}
    def update_lead(self, lead: Lead, updates: dict[str, str]) -> None:
        if self.fail_update: raise RuntimeError("sheet failed")
        self.updates.append(updates)
        lead.values.update(updates)


class FakeMailer:
    def __init__(self, *, fail: bool = False, replies=None):
        self.fail = fail; self.calls = 0; self.replies = replies or []
    def healthcheck(self): return {"ok": True}
    def fetch_replies(self, ids): return self.replies
    def send(self, lead, subject, body, *, message_id):
        self.calls += 1
        if self.fail: raise RuntimeError("smtp failed")
        return SendResult(message_id)


def workflow(tmp_path: Path, sheets: FakeSheets, mailer: FakeMailer, **kwargs) -> OutreachWorkflow:
    cfg = config(tmp_path, **kwargs)
    return OutreachWorkflow(cfg, sheets, mailer, StateStore(cfg.state_path), EventLogger(cfg.log_path), output=lambda _: None)


def test_status_changes_only_after_confirmed_send(tmp_path: Path) -> None:
    sheets, mailer = FakeSheets([make_lead()]), FakeMailer()
    result = workflow(tmp_path, sheets, mailer).send_new()
    assert result["sent"] == 1
    assert sheets.updates[0]["Статус"] == "Письмо отправлено"
    assert sheets.updates[0]["OpenClaw Message-ID"].startswith("<")


def test_smtp_error_does_not_change_sheet_and_blocks_restart(tmp_path: Path) -> None:
    sheets, mailer = FakeSheets([make_lead()]), FakeMailer(fail=True)
    first = workflow(tmp_path, sheets, mailer).send_new()
    second = workflow(tmp_path, sheets, mailer).send_new()
    assert first["errors"] == 1
    assert second["sent"] == 0
    assert mailer.calls == 1
    assert sheets.updates == []


def test_sheet_failure_is_reconciled_without_resend(tmp_path: Path) -> None:
    sheets, mailer = FakeSheets([make_lead()], fail_update=True), FakeMailer()
    assert workflow(tmp_path, sheets, mailer).send_new()["errors"] == 1
    sheets.fail_update = False
    assert workflow(tmp_path, sheets, mailer).send_new()["reconciled"] == 1
    assert mailer.calls == 1
    assert sheets.updates[-1]["Статус"] == "Письмо отправлено"


def test_dry_run_never_sends_or_mutates(tmp_path: Path) -> None:
    sheets, mailer = FakeSheets([make_lead()]), FakeMailer()
    result = workflow(tmp_path, sheets, mailer, dry_run=True).dry_run()
    assert result["shown"] == 1
    assert mailer.calls == 0 and sheets.updates == []
    assert StateStore(tmp_path / "state.sqlite3").report().get("reserved", 0) == 0


def test_send_new_is_blocked_while_dry_run_true(tmp_path: Path) -> None:
    with pytest.raises(SafetyError):
        workflow(tmp_path, FakeSheets([make_lead()]), FakeMailer(), dry_run=True).send_new()


def test_daily_limit_survives_restart(tmp_path: Path) -> None:
    sheets, mailer = FakeSheets([make_lead(2), make_lead(3, "other@example.com")]), FakeMailer()
    first = workflow(tmp_path, sheets, mailer, limit=1).send_new()
    second = workflow(tmp_path, sheets, mailer, limit=1).send_new()
    assert first["sent"] == 1 and second["sent"] == 0
    assert mailer.calls == 1


def test_sync_reply_updates_once_and_never_sends(tmp_path: Path) -> None:
    sent = make_lead()
    sent.values.update({"Статус": "Письмо отправлено", "OpenClaw Message-ID": "<original@example.com>"})
    incoming = IncomingMessage(
        id="imap-42", message_id="<reply@example.com>",
        in_reply_to="<original@example.com>", references=(),
        from_address=sent.email, subject="Re: Короткая тема", body="Да, интересно",
        received_at=datetime.fromisoformat("2026-09-22T12:00:00+03:00"),
    )
    sheets, mailer = FakeSheets([sent]), FakeMailer(replies=[incoming])
    flow = workflow(tmp_path, sheets, mailer)
    assert flow.sync_replies()["processed"] == 1
    assert sheets.updates[-1]["Статус"] == "Ответили"
    assert flow.sync_replies()["processed"] == 0
    assert mailer.calls == 0


def test_sync_reply_dry_run_only_prints_plan(tmp_path: Path) -> None:
    sent = make_lead()
    sent.values.update({"Статус": "Письмо отправлено", "OpenClaw Message-ID": "<original@example.com>"})
    incoming = IncomingMessage(
        id="imap-43", message_id="<reply2@example.com>",
        in_reply_to="<original@example.com>", references=(),
        from_address=sent.email, subject="Re", body="Не интересно",
        received_at=datetime.fromisoformat("2026-09-22T12:00:00+03:00"),
    )
    sheets, mailer = FakeSheets([sent]), FakeMailer(replies=[incoming])
    result = workflow(tmp_path, sheets, mailer, dry_run=True).sync_replies()
    assert result == {"processed": 0, "planned": 1, "fetched": 1}
    assert sheets.updates == [] and mailer.calls == 0
