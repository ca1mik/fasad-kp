import base64
from dataclasses import make_dataclass
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from types import SimpleNamespace

import pytest

from gmail_https import GmailHttpsMailer
from mailer import MailerError
from openclaw_mail import OpenClawBridge

SENDER = "koallalenivaa@gmail.com"


def env_bridge():
    values = dict(provider="reg_ru", default_from_email="hello@example.ru", smtp_host="mail.example.ru",
                  smtp_port=465, smtp_security="ssl", smtp_user="hello@example.ru", smtp_password="old-test-password",
                  imap_host="mail.example.ru", imap_port=993, imap_security="ssl", imap_user="hello@example.ru",
                  imap_password="old-test-password", imap_mailbox="INBOX", secondary_from_email="",
                  secondary_smtp_user="", secondary_smtp_password="", draft_only=True, daily_limit=25,
                  hourly_limit=8, min_pause_seconds=90)
    record = make_dataclass("Settings", [(key, type(value)) for key, value in values.items()])
    bridge = OpenClawBridge.__new__(OpenClawBridge)
    bridge.settings = record(**values)
    return bridge


def test_selected_env_is_exact_readonly_and_not_global(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(f"EMAIL_ADDRESS={SENDER}\nEMAIL_PASSWORD=fake-test-password\n", encoding="utf-8")
    before = path.read_bytes()
    bridge = env_bridge()
    monkeypatch.setenv("EMAIL_ADDRESS", "unrelated@example.ru")
    assert bridge._env_identity(path, SENDER).email_address == SENDER
    assert bridge.settings.imap_user == SENDER and bridge.settings.draft_only is True
    assert bridge.settings.daily_limit == 25 and path.read_bytes() == before
    import os
    assert os.environ["EMAIL_ADDRESS"] == "unrelated@example.ru"


@pytest.mark.parametrize("extra", ["EMAIL_SMTP_SERVER=foreign.example", "EMAIL_USERNAME=other@gmail.com"])
def test_selected_env_rejects_foreign_identity_or_server(tmp_path, extra):
    path = tmp_path / ".env"
    path.write_text(f"EMAIL_ADDRESS={SENDER}\nEMAIL_PASSWORD=fake-test-password\n{extra}\n", encoding="utf-8")
    with pytest.raises(MailerError):
        env_bridge()._env_identity(path, SENDER)


class Session:
    def __init__(self, status=200, result=None, fail=False):
        self.calls = []
        self.status = status
        self.result = {"id": "gmail-provider-id", "threadId": "gmail-thread-id"} if result is None else result
        self.fail = fail

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.fail:
            raise TimeoutError("untrusted transport detail")
        return SimpleNamespace(status_code=self.status, json=lambda: self.result)


def mailer(tmp_path, session):
    adapter = GmailHttpsMailer.__new__(GmailHttpsMailer)
    adapter.address = SENDER
    adapter.config = SimpleNamespace(mail_display_name="Lev Kaldin — Fasad Flow")
    adapter.oauth_path = tmp_path / "gmail_oauth.dpapi"
    adapter.closed = []
    client = SimpleNamespace(session=session, payload={"access_token": "fake-test-token"},
                             quit=lambda: adapter.closed.append(True))
    adapter._client = lambda: client
    return adapter


def test_https_sends_once_and_preserves_actual_ids(tmp_path):
    session = Session()
    adapter = mailer(tmp_path, session)
    result = adapter.send("workshop@example.rs", "Ponuda za Šimšić", "Poštovani", message_id="<reserved@gmail.com>")
    assert result.message_id == "<reserved@gmail.com>" and result.provider_id == "gmail-provider-id"
    assert result.thread_id == "gmail-thread-id" and len(session.calls) == 1 and adapter.closed == [True]
    url, options = session.calls[0]
    assert url == "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    assert options["allow_redirects"] is False
    message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(options["json"]["raw"]))
    assert parseaddr(message["From"])[1] == SENDER and message["To"] == "workshop@example.rs"
    assert message.get("Cc") is None and message.get("Bcc") is None and not list(message.iter_attachments())


@pytest.mark.parametrize("options", [{"status": 500}, {"status": 401}, {"result": {}}, {"fail": True}])
def test_https_error_is_not_retried_or_leaked(tmp_path, options):
    session = Session(**options)
    adapter = mailer(tmp_path, session)
    with pytest.raises(MailerError) as caught:
        adapter.send("workshop@example.rs", "Ponuda", "Body", message_id="<reserved@gmail.com>")
    assert len(session.calls) == 1 and adapter.closed == [True]
    assert "fake-test-token" not in str(caught.value)


def test_https_has_no_smtp_fallback(tmp_path):
    with pytest.raises(MailerError, match="fallback is disabled"):
        mailer(tmp_path, Session())._open_smtp()


def test_missing_oauth_fails_before_network(tmp_path):
    adapter = GmailHttpsMailer.__new__(GmailHttpsMailer)
    adapter.oauth_path = tmp_path / "missing.dpapi"
    with pytest.raises(MailerError, match="connect_fasad_gmail.cmd"):
        adapter._client()


@pytest.mark.parametrize("subject,expected", [("Ponuda za Šimšić", True), ("Other project", False)])
def test_gmail_sent_check_is_readonly_and_headers_only(tmp_path, subject, expected):
    from email.message import EmailMessage
    header = EmailMessage()
    header["Subject"] = subject
    selections = []
    fetches = []
    def uid(action, *args):
        if action == "search":
            return "OK", [b"123"]
        fetches.append(args)
        return "OK", [(b"123", header.as_bytes())]
    imap = SimpleNamespace(list=lambda: ("OK", [b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"']),
                           select=lambda folder, readonly: (selections.append((folder, readonly)) or ("OK", [])),
                           uid=uid)
    adapter = mailer(tmp_path, Session())
    adapter._open_imap = lambda: imap
    adapter._close_imap = lambda client: None
    assert adapter.has_sent_message("workshop@example.rs", "Ponuda za Šimšić") is expected
    assert selections == [('"[Gmail]/Sent Mail"', True)]
    assert all("BODY.PEEK[HEADER.FIELDS" in item[1] for item in fetches)
