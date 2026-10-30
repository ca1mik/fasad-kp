"""SMTP/IMAP mail adapter with password and OAuth XOAUTH2 authentication."""

from __future__ import annotations

import base64
import email
import imaplib
import re
import smtplib
import ssl
from datetime import date, datetime, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.policy import default
from email.utils import getaddresses, make_msgid, parsedate_to_datetime
from typing import Any, Iterable

import requests

from models import IncomingMessage, Lead, SendResult


class MailerError(RuntimeError):
    """A deliberately sanitized mail transport error."""


_PROVIDERS = {
    "gmail": ("smtp.gmail.com", 465, "ssl", "imap.gmail.com", 993),
    "outlook": ("smtp.office365.com", 587, "starttls", "outlook.office365.com", 993),
    "yandex": ("smtp.yandex.com", 465, "ssl", "imap.yandex.com", 993),
    "mailru": ("smtp.mail.ru", 465, "ssl", "imap.mail.ru", 993),
    "mail.ru": ("smtp.mail.ru", 465, "ssl", "imap.mail.ru", 993),
}

_TOKEN_URLS = {
    "gmail": "https://oauth2.googleapis.com/token",
    "outlook": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
}


def _header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _normalise_message_id(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    return value if value.startswith("<") and value.endswith(">") else f"<{value.strip('<>')}>"


def _message_ids(value: str | None) -> set[str]:
    if not value:
        return set()
    matches = re.findall(r"<[^<>\s]+>", value)
    return {_normalise_message_id(item) for item in (matches or value.split()) if item.strip()}


def _message_id_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    matches = re.findall(r"<[^<>\s]+>", value)
    candidates = matches or value.split()
    # dict provides stable de-duplication while preserving References order.
    return tuple(dict.fromkeys(_normalise_message_id(item) for item in candidates if item.strip()))


def _plain_body(message: Message) -> str:
    if message.is_multipart():
        html = ""
        for part in message.walk():
            disposition = (part.get_content_disposition() or "").lower()
            if disposition == "attachment":
                continue
            content_type = part.get_content_type()
            if content_type not in ("text/plain", "text/html"):
                continue
            try:
                content = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True) or b""
                content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            if content_type == "text/plain":
                return str(content)
            html = str(content)
        return re.sub(r"<[^>]+>", " ", html).strip()
    try:
        return str(message.get_content())
    except Exception:
        payload = message.get_payload(decode=True) or b""
        return payload.decode(message.get_content_charset() or "utf-8", errors="replace")


class Mailer:
    def __init__(
        self,
        config: Any,
        *,
        smtp_factory: Any = smtplib.SMTP,
        smtp_ssl_factory: Any = smtplib.SMTP_SSL,
        imap_factory: Any = imaplib.IMAP4_SSL,
        http_session: Any | None = None,
    ) -> None:
        self.config = config
        self.smtp_factory = smtp_factory
        self.smtp_ssl_factory = smtp_ssl_factory
        self.imap_factory = imap_factory
        self.http_session = http_session or requests.Session()
        provider = str(getattr(config, "mail_provider", "custom") or "custom").casefold()
        self.provider = provider
        defaults = _PROVIDERS.get(provider, ("", 0, "starttls", "", 993))
        self.smtp_host = str(getattr(config, "smtp_host", "") or defaults[0])
        self.smtp_port = int(getattr(config, "smtp_port", 0) or defaults[1])
        self.smtp_security = str(getattr(config, "smtp_security", "") or defaults[2]).casefold()
        self.imap_host = str(getattr(config, "imap_host", "") or defaults[3])
        self.imap_port = int(getattr(config, "imap_port", 0) or defaults[4])
        self.folder = str(getattr(config, "imap_folder", "INBOX") or "INBOX")
        self.address = str(config.mail_address)
        self.timeout = float(getattr(config, "http_timeout", 20))
        if not self.smtp_host or not self.imap_host:
            raise ValueError("SMTP and IMAP hosts must be configured for a custom provider")

    def _oauth_token(self) -> str:
        refresh_token = str(getattr(self.config, "oauth_refresh_token", "") or "")
        client_id = str(getattr(self.config, "oauth_client_id", "") or "")
        client_secret = str(getattr(self.config, "oauth_client_secret", "") or "")
        token_url = str(
            getattr(self.config, "oauth_token_url", "") or _TOKEN_URLS.get(self.provider, "")
        )
        if not (refresh_token and client_id and client_secret and token_url):
            raise MailerError("Mail OAuth credentials are not configured")
        try:
            response = self.http_session.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            token = response.json().get("access_token")
        except Exception:
            raise MailerError("Mail OAuth token refresh failed") from None
        if not token:
            raise MailerError("Mail OAuth token response did not contain an access token")
        return str(token)

    def _auth_mode(self) -> str:
        value = str(getattr(self.config, "mail_auth_mode", "app_password") or "app_password")
        value = value.casefold().replace("-", "_")
        return "oauth" if value in {"oauth", "oauth2", "xoauth2"} else "app_password"

    def _xoauth(self, token: str) -> bytes:
        return f"user={self.address}\x01auth=Bearer {token}\x01\x01".encode("utf-8")

    def _smtp_authenticate(self, client: Any) -> None:
        if self._auth_mode() == "oauth":
            encoded = base64.b64encode(self._xoauth(self._oauth_token())).decode("ascii")
            code, _ = client.docmd("AUTH", "XOAUTH2 " + encoded)
            if int(code) >= 400:
                raise MailerError("SMTP OAuth authentication failed")
        else:
            password = str(getattr(self.config, "mail_app_password", "") or "")
            if not password:
                raise MailerError("Mail app password is not configured")
            client.login(self.address, password)

    def _imap_authenticate(self, client: Any) -> None:
        if self._auth_mode() == "oauth":
            auth = self._xoauth(self._oauth_token())
            client.authenticate("XOAUTH2", lambda _: auth)
        else:
            password = str(getattr(self.config, "mail_app_password", "") or "")
            if not password:
                raise MailerError("Mail app password is not configured")
            client.login(self.address, password)

    def _open_smtp(self) -> Any:
        context = ssl.create_default_context()
        client = None
        try:
            if self.smtp_security in {"ssl", "tls", "implicit_tls"}:
                client = self.smtp_ssl_factory(
                    self.smtp_host, self.smtp_port, timeout=self.timeout, context=context
                )
            else:
                client = self.smtp_factory(self.smtp_host, self.smtp_port, timeout=self.timeout)
                client.ehlo()
                if self.smtp_security in {"starttls", "start_tls"}:
                    client.starttls(context=context)
                    client.ehlo()
            self._smtp_authenticate(client)
            return client
        except MailerError:
            if client is not None:
                self._close_smtp(client)
            raise
        except Exception:
            if client is not None:
                self._close_smtp(client)
            raise MailerError("SMTP connection or authentication failed") from None

    def _open_imap(self) -> Any:
        client = None
        try:
            client = self.imap_factory(self.imap_host, self.imap_port, timeout=self.timeout)
            self._imap_authenticate(client)
            return client
        except MailerError:
            if client is not None:
                self._close_imap(client)
            raise
        except Exception:
            if client is not None:
                self._close_imap(client)
            raise MailerError("IMAP connection or authentication failed") from None

    @staticmethod
    def _close_smtp(client: Any) -> None:
        try:
            client.quit()
        except Exception:
            try:
                client.close()
            except Exception:
                pass

    @staticmethod
    def _close_imap(client: Any) -> None:
        try:
            client.close()
        except Exception:
            pass
        try:
            client.logout()
        except Exception:
            pass

    def healthcheck(self) -> bool:
        """Authenticate to both transports and open IMAP read-only; send nothing."""
        smtp = self._open_smtp()
        self._close_smtp(smtp)
        imap = self._open_imap()
        try:
            status, _ = imap.select(self.folder, readonly=True)
            if str(status).upper() != "OK":
                raise MailerError("IMAP folder cannot be opened read-only")
        finally:
            self._close_imap(imap)
        return True

    def send(
        self,
        recipient: str | Lead,
        subject: str,
        body: str,
        *,
        message_id: str | None = None,
        in_reply_to: str = "",
        references: Iterable[str] = (),
    ) -> SendResult:
        """Send exactly once and return the RFC Message-ID placed in the message."""
        to_address = recipient.email if isinstance(recipient, Lead) else str(recipient)
        if not to_address.strip():
            raise ValueError("recipient address must not be empty")
        domain = self.address.rpartition("@")[2] or None
        actual_id = _normalise_message_id(message_id or make_msgid(domain=domain))
        message = EmailMessage()
        message["From"] = self.address
        display_name = str(getattr(self.config, "mail_display_name", "") or "").strip()
        if display_name:
            message.replace_header("From", f"{display_name} <{self.address}>")
        message["To"] = to_address
        message["Subject"] = subject
        message["Message-ID"] = actual_id
        if in_reply_to:
            message["In-Reply-To"] = _normalise_message_id(in_reply_to)
        reference_values = [_normalise_message_id(value) for value in references if value]
        if reference_values:
            message["References"] = " ".join(reference_values)
        message.set_content(body)

        client = self._open_smtp()
        try:
            refused = client.send_message(message)
            if refused:
                raise MailerError("SMTP server refused one or more recipients")
        except MailerError:
            raise
        except Exception:
            # Deliberately no retry: an exception after DATA may still mean delivery.
            raise MailerError("SMTP send outcome is uncertain; message was not retried") from None
        finally:
            self._close_smtp(client)
        return SendResult(message_id=actual_id, provider_id=actual_id)

    def fetch_replies(
        self,
        sent_message_ids: Iterable[str],
        *,
        limit: int = 200,
        since: date | None = None,
        header_first: bool = False,
    ) -> list[IncomingMessage]:
        """Fetch matching replies without changing their Seen flags."""
        targets = {_normalise_message_id(item) for item in sent_message_ids if item}
        if not targets:
            return []
        client = self._open_imap()
        results: list[IncomingMessage] = []
        try:
            status, _ = client.select(self.folder, readonly=True)
            if str(status).upper() != "OK":
                raise MailerError("IMAP folder cannot be opened read-only")
            criteria = ("SINCE", since.strftime("%d-%b-%Y")) if since else ("ALL",)
            status, data = client.uid("search", None, *criteria)
            if str(status).upper() != "OK":
                raise MailerError("IMAP search failed")
            ids = (data[0] if data else b"").split()[-max(0, int(limit)):]
            if header_first:
                matched = []
                for start in range(0, len(ids), 50):
                    chunk = ids[start:start + 50]
                    status, headers = client.uid(
                        "fetch", b",".join(chunk),
                        "(UID BODY.PEEK[HEADER.FIELDS (IN-REPLY-TO REFERENCES)])",
                    )
                    if str(status).upper() != "OK":
                        raise MailerError("IMAP reply header fetch failed")
                    returned = set()
                    for part in headers or []:
                        if not isinstance(part, tuple) or len(part) < 2:
                            continue
                        match = re.search(rb"\bUID\s+(\d+)\b", part[0])
                        if not match:
                            raise MailerError("IMAP reply header UID is missing")
                        uid = match[1]
                        returned.add(uid)
                        header = email.message_from_bytes(part[1], policy=default)
                        header_ids = _message_ids(_header(header.get("In-Reply-To")))
                        header_ids |= set(_message_id_list(_header(header.get("References"))))
                        if header_ids & targets:
                            matched.append(uid)
                    if returned != set(chunk):
                        raise MailerError("IMAP reply header batch was incomplete")
                ids = matched
            for uid in ids:
                status, payload = client.uid("fetch", uid, "(BODY.PEEK[])")
                if str(status).upper() != "OK":
                    continue
                raw = next(
                    (part[1] for part in payload or [] if isinstance(part, tuple) and len(part) > 1),
                    None,
                )
                if not raw:
                    continue
                parsed = email.message_from_bytes(raw, policy=default)
                in_reply_to = _header(parsed.get("In-Reply-To"))
                references_raw = _header(parsed.get("References"))
                references = _message_id_list(references_raw)
                if not ((_message_ids(in_reply_to) | set(references)) & targets):
                    continue
                message_id = _normalise_message_id(_header(parsed.get("Message-ID")))
                from_addresses = getaddresses([_header(parsed.get("From"))])
                from_address = from_addresses[0][1] if from_addresses else ""
                try:
                    received_at = parsedate_to_datetime(str(parsed.get("Date", "")))
                    if received_at is None:
                        raise ValueError
                    if received_at.tzinfo is None:
                        received_at = received_at.replace(tzinfo=timezone.utc)
                except Exception:
                    received_at = datetime.now(timezone.utc)
                automated = (
                    str(parsed.get("Auto-Submitted", "no")).casefold() not in {"", "no"}
                    or str(parsed.get("Precedence", "")).casefold() in {"bulk", "junk", "list"}
                    or bool(parsed.get("X-Auto-Response-Suppress"))
                )
                results.append(
                    IncomingMessage(
                        id=uid.decode("ascii", errors="replace") if isinstance(uid, bytes) else str(uid),
                        message_id=message_id,
                        in_reply_to=in_reply_to,
                        references=references,
                        from_address=from_address,
                        subject=_header(parsed.get("Subject")),
                        body=_plain_body(parsed),
                        received_at=received_at,
                        thread_id="",
                        automated=automated,
                    )
                )
        except MailerError:
            raise
        except Exception as exc:
            raise MailerError("IMAP reply fetch failed: " + type(exc).__name__) from None
        finally:
            self._close_imap(client)
        return results


EmailAdapter = Mailer
