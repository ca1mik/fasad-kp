"""Isolated Gmail HTTPS sending; reuse the agent's OAuth/DPAPI helper, never its queue."""

from __future__ import annotations

import base64
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import SMTP, default
from email.utils import formataddr, make_msgid
import importlib
import re
from pathlib import Path
import sys

from mailer import MailerError
from models import SendResult
from openclaw_mail import OpenClawMailer


def oauth_module(agent_root: Path):
    path = agent_root / "src" / "tools" / "otpremaops_gmail_api.py"
    if not path.is_file():
        raise MailerError("Open Claw Gmail HTTPS helper is missing")
    sys.path.insert(0, str(agent_root))
    try:
        module = importlib.import_module("src.tools.otpremaops_gmail_api")
        if Path(module.__file__).resolve() != path.resolve():
            raise MailerError("A different Gmail OAuth helper is already imported")
        return module
    finally:
        sys.path.remove(str(agent_root))


class GmailHttpsMailer(OpenClawMailer):
    outbound_transport = "gmail_https"

    def __init__(self, settings, identity, display_name: str, data: Path, agent_root: Path):
        super().__init__(settings, identity, display_name)
        self.oauth_root = data.resolve()
        self.oauth_path = self.oauth_root / "gmail_oauth.dpapi"
        self.agent_root = agent_root.resolve()

    def _client(self):
        if not self.oauth_path.is_file():
            raise MailerError("Gmail HTTPS OAuth is not connected; open connect_fasad_gmail.cmd")
        try:
            return oauth_module(self.agent_root).GmailApiClient(
                {"root": self.oauth_root, "sender_email": self.address})
        except Exception:
            raise MailerError("Gmail HTTPS OAuth verification failed; no SMTP fallback was attempted") from None

    def _open_smtp(self):
        raise MailerError("SMTP fallback is disabled for this Gmail HTTPS campaign")

    def healthcheck(self) -> bool:
        # The helper verifies the actual Google identity, email_verified and scopes.
        client = self._client()
        client.quit()
        imap = self._open_imap()
        try:
            status, _ = imap.select(self.folder, readonly=True)
            if str(status).upper() != "OK":
                raise MailerError("Gmail IMAP folder cannot be opened read-only")
        finally:
            self._close_imap(imap)
        return True

    def has_sent_message(self, recipient: str, subject: str) -> bool:
        """Check Gmail Sent read-only, without an additional API read scope."""
        imap = self._open_imap()
        try:
            status, folders = imap.list()
            if status != "OK":
                raise MailerError("Cannot check Gmail Sent; sending is blocked")
            sent = next((line for line in folders or [] if isinstance(line, bytes) and b"\\Sent" in line), None)
            match = re.search(rb'\)\s+(?:"[^"]*"|NIL)\s+(.+)$', sent or b"")
            if match is None:
                raise MailerError("Gmail Sent folder was not identified; sending is blocked")
            status, _ = imap.select(match[1].decode("ascii"), readonly=True)
            if status != "OK":
                raise MailerError("Cannot open Gmail Sent read-only")
            status, values = imap.uid("search", None, "TO", f'"{recipient}"')
            if status != "OK":
                raise MailerError("Cannot search Gmail Sent; sending is blocked")
            ids = (values[0] if values else b"").split()
            if len(ids) > 100:
                raise MailerError("Too many matching sent messages; manual reconciliation is required")
            for uid in ids:
                status, values = imap.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
                raw = next((part[1] for part in values or [] if isinstance(part, tuple)), None)
                if status != "OK" or not isinstance(raw, bytes):
                    raise MailerError("Cannot read a sent header; sending is blocked")
                if str(BytesParser(policy=default).parsebytes(raw).get("Subject", "")).strip() == subject.strip():
                    return True
            return False
        finally:
            self._close_imap(imap)

    def send(self, recipient: str, subject: str, body: str, *, message_id: str | None = None) -> SendResult:
        if any("\r" in value or "\n" in value for value in (recipient, subject)) or not recipient:
            raise MailerError("Invalid Gmail message header")
        actual_id = message_id or make_msgid(domain="gmail.com")
        message = EmailMessage(policy=SMTP)
        message["From"] = formataddr((self.config.mail_display_name, self.address))
        message["To"] = recipient
        message["Reply-To"] = self.address
        message["Subject"] = subject
        message["Message-ID"] = actual_id
        message.set_content(body)
        client = self._client()
        try:
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
            # Exactly ONE send POST. No retry, redirect, SMTP or other sender fallback.
            response = client.session.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": "Bearer " + client.payload["access_token"]},
                json={"raw": raw}, timeout=(5, 12), allow_redirects=False,
            )
            if response.status_code != 200:
                raise MailerError("Gmail HTTPS send was not confirmed; reconcile Sent before retrying")
            result = response.json()
            if not isinstance(result.get("id"), str) or not result["id"]:
                raise MailerError("Gmail HTTPS returned no provider message ID; reconcile Sent before retrying")
            return SendResult(actual_id, str(result.get("threadId") or ""), result["id"])
        except MailerError:
            raise
        except Exception:
            raise MailerError("Gmail HTTPS send outcome is uncertain; message was not retried") from None
        finally:
            client.quit()
