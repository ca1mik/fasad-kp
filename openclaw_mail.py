"""Read the existing Open Claw mailbox configuration without changing its jobs."""

from __future__ import annotations

import csv
from dataclasses import replace
import importlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

from dotenv import dotenv_values

from mailer import Mailer, MailerError


class OpenClawMailer(Mailer):
    """Use the existing mailbox with the demo project's TLS/at-most-once transport."""

    def __init__(self, settings, identity, display_name: str):
        self.settings = settings
        self.identity = identity
        super().__init__(SimpleNamespace(
            mail_provider="smtp", mail_address=identity.email_address,
            mail_display_name=display_name, smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port, smtp_security=settings.smtp_security,
            imap_host=settings.imap_host, imap_port=settings.imap_port,
            imap_folder=settings.imap_mailbox, http_timeout=30,
        ))

    def _smtp_authenticate(self, client):
        client.login(self.identity.username, self.identity.password)

    def _imap_authenticate(self, client):
        client.login(self.settings.imap_user, self.settings.imap_password)


class OpenClawBridge:
    def __init__(self, root: Path, mailbox: str = "primary", display_name: str = "Fasad Flow",
                 mailbox_env: str = "", outbound_transport: str = "smtp", oauth_root: Path | None = None,
                 mailbox_profile: str = ""):
        self.root = root.resolve()
        if not (self.root / "src" / "tools" / "sales_mailbox.py").is_file():
            raise MailerError("Open Claw installation not found")
        sys.path.insert(0, str(self.root))
        try:
            config_module = importlib.import_module("src.config")
            if Path(config_module.PROJECT_ROOT).resolve() != self.root:
                raise MailerError("A different Open Claw installation is already imported")
            sales_mailbox = importlib.import_module("src.tools.sales_mailbox")
            self.settings = sales_mailbox.load_sales_mail_settings()
            configured_workdir = Path(os.getenv("WORKDIR", str(self.root.parent / "open-claw-workdir")))
            self.workdir = (configured_workdir if configured_workdir.is_absolute()
                            else self.root / configured_workdir).resolve()
            identities = sales_mailbox._mail_identities(self.settings)
            wanted = {"hello": "primary", "info": "secondary"}.get(mailbox.casefold(), mailbox.casefold())
            self.credential_source = mailbox_env
            self.profile_root = None
            if mailbox_profile and mailbox_env:
                raise MailerError("Choose one exact Gmail credential source, not two")
            identity = (self._profile_identity(Path(mailbox_profile), wanted) if mailbox_profile else
                        self._env_identity(Path(mailbox_env), wanted) if mailbox_env else
                        next((item for item in identities if wanted in
                              {item.label.casefold(), item.email_address.casefold()}), None))
            if identity is None and "@" in wanted and not mailbox_env:
                # A personal Gmail binding in Open Claw is separate from the ChatGPT connector.
                # Read an existing exact-address binding only; never create a database or fall back.
                identity = self._personal_identity(wanted)
            if identity is None:
                raise MailerError("Requested sender is not connected in Open Claw; no fallback mailbox is allowed")
            if self.settings.smtp_security not in {"ssl", "starttls"}:
                raise MailerError("Unencrypted SMTP is not allowed")
            if self.settings.imap_security != "ssl":
                raise MailerError("This campaign requires IMAP over TLS")
            self.mailer = OpenClawMailer(self.settings, identity, display_name)
            if outbound_transport == "gmail_https":
                from gmail_https import GmailHttpsMailer
                if oauth_root is None:
                    raise MailerError("Gmail OAuth storage must be explicitly selected")
                self.mailer = GmailHttpsMailer(self.settings, identity, display_name,
                                              self.profile_root or oauth_root, self.root)
            elif outbound_transport != "smtp":
                raise MailerError("Unknown mail transport")
            self._global_suppressed = importlib.import_module(
                "src.tools.outreach_reply_agent").load_global_suppressed_emails
        except MailerError:
            raise
        except Exception:
            raise MailerError("Cannot load Open Claw mailbox settings; secrets were not logged") from None
        finally:
            sys.path.remove(str(self.root))

    def _env_identity(self, path: Path, address: str):
        """Read the selected Gmail .env without modifying process/global settings."""
        if not path.is_file():
            raise MailerError("Selected Gmail credential file does not exist")
        values = dotenv_values(path, interpolate=False)
        selected = (values.get("EMAIL_ADDRESS") or "").strip().casefold()
        username = (values.get("EMAIL_USERNAME") or selected).strip().casefold()
        if not address.endswith("@gmail.com") or selected != address or username != address:
            raise MailerError("Selected Gmail credential file does not match the authorized sender")
        if any(values.get(key) and values[key].strip().casefold() != expected for key, expected in (
                ("EMAIL_SMTP_SERVER", "smtp.gmail.com"), ("SMTP_HOST", "smtp.gmail.com"),
                ("EMAIL_IMAP_SERVER", "imap.gmail.com"), ("IMAP_HOST", "imap.gmail.com"))):
            raise MailerError("Selected Gmail credential file has an unexpected mail server")
        password = values.get("EMAIL_PASSWORD") or ""
        if not password:
            raise MailerError("Selected Gmail credential file has no app password")
        # Keep Open Claw's global draft flag and limits unchanged; replace only this
        # in-memory mailbox. No password is copied into the project or its config.
        self.settings = replace(
            self.settings, provider="gmail", default_from_email=address,
            smtp_host="smtp.gmail.com", smtp_port=587, smtp_security="starttls",
            smtp_user=address, smtp_password=password, imap_host="imap.gmail.com",
            imap_port=993, imap_security="ssl", imap_user=address,
            imap_password=password, imap_mailbox="INBOX", secondary_from_email="",
            secondary_smtp_user="", secondary_smtp_password="",
        )
        return SimpleNamespace(label="selected_gmail_env", email_address=address,
                               username=address, password=password)

    def _profile_identity(self, path: Path, address: str):
        from mailbox_profile import read_profile
        profile = read_profile(path, address)
        if not address.endswith("@gmail.com"):
            raise MailerError("The shared profile must be the explicitly selected Gmail sender")
        native = importlib.import_module("src.tools.otpremaops_outreach")
        self.settings = native.campaign_mail_settings(profile, self.settings)
        if not self.settings.imap_configured:
            raise MailerError("The shared Gmail IMAP credential is missing")
        self.profile_root = profile["root"]
        self.credential_source = str(self.profile_root / "gmail_credential.dpapi")
        return SimpleNamespace(label="shared_openclaw_gmail", email_address=address,
                               username=address, password=self.settings.imap_password)

    def mailbox_guard(self, campaign_id: str = "fasad-flow-serbia-v1"):
        from contextlib import nullcontext
        from mailbox_profile import guard
        return guard(self.profile_root, campaign_id) if self.profile_root else nullcontext()

    def apply_mailbox_limits(self, daily: int, hourly: int):
        """Explicit owner-approved limits for this shared Gmail, not other jobs."""
        if (not self.profile_root or not self.mailer.address.casefold().endswith("@gmail.com")
                or self.mailer.identity.label != "shared_openclaw_gmail"):
            raise MailerError("Limit override is restricted to the selected shared Gmail")
        if any(type(value) is not int or not 1 <= value <= 100 for value in (daily, hourly)):
            raise MailerError("The approved mailbox limit must be between 1 and 100")
        self.inherited_limits = {"daily_limit": self.settings.daily_limit,
                                 "hourly_limit": self.settings.hourly_limit}
        self.settings = replace(self.settings, daily_limit=daily, hourly_limit=hourly,
                                min_pause_seconds=max(90, self.settings.min_pause_seconds))
        self.mailer.settings = self.settings

    def shared_budget(self, now):
        from mailbox_profile import budget
        return budget(self.profile_root, now) if self.profile_root else {
            "daily": 0, "hourly": 0, "last_attempt": None, "uncertain": 0,
            "total_attempts": 0, "total_sent": 0}

    def contacted_companies(self) -> set[str]:
        from mailbox_profile import snapshot
        return snapshot(self.profile_root)["companies"] if self.profile_root else set()

    def _personal_identity(self, address: str):
        path = self.workdir / "user_mailboxes.db"
        if not path.is_file():
            return None
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT * FROM user_mailboxes WHERE lower(address)=?", (address,)
            ).fetchall()
        finally:
            connection.close()
        if not rows:
            return None
        if len(rows) != 1:
            raise MailerError("Multiple Open Claw bindings for this sender; choose one explicitly before sending")
        row = rows[0]
        if not row["password"]:
            raise MailerError("Personal Open Claw mailbox credentials are missing")
        if address.endswith("@gmail.com") and (
                row["username"].casefold() != address
                or row["smtp_server"].casefold() != "smtp.gmail.com"
                or row["imap_server"].casefold() != "imap.gmail.com"):
            raise MailerError("Personal Gmail binding has an unexpected username or mail server")
        self.settings = SimpleNamespace(
            smtp_host=row["smtp_server"], smtp_port=row["smtp_port"],
            smtp_security=row["smtp_security"], imap_host=row["imap_server"],
            imap_port=row["imap_port"], imap_security=row["imap_security"],
            imap_user=row["username"], imap_password=row["password"], imap_mailbox=row["mailbox"],
            draft_only=self.settings.draft_only, daily_limit=self.settings.daily_limit,
            hourly_limit=self.settings.hourly_limit, min_pause_seconds=self.settings.min_pause_seconds,
            smtp_configured=True, imap_configured=True,
        )
        return SimpleNamespace(label="personal", email_address=address,
                               username=row["username"], password=row["password"])

    def summary(self) -> dict:
        return {
            "installation": str(self.root), "workdir": str(self.workdir),
            "sender": self.mailer.address, "mailbox": self.mailer.identity.label,
            "smtp_configured": self.settings.smtp_configured,
            "imap_configured": self.settings.imap_configured,
            "draft_only": self.settings.draft_only,
            "daily_limit": self.settings.daily_limit,
            "hourly_limit": self.settings.hourly_limit,
            "min_pause_seconds": self.settings.min_pause_seconds,
            "limits_scope": "explicit Fasad Flow Gmail override" if hasattr(self, "inherited_limits") else "Open Claw defaults",
            "inherited_limits": getattr(self, "inherited_limits", None),
            "credential_source": getattr(self, "credential_source", ""),
            "shared_profile_root": str(self.profile_root) if self.profile_root else None,
            "outbound_transport": getattr(self.mailer, "outbound_transport", "smtp"),
            "oauth_connected": getattr(self.mailer, "oauth_path", Path("__missing_oauth__")).is_file(),
        }

    def suppression(self) -> tuple[set[str], set[str]]:
        """Fail closed on broken stop lists, including domain-level opt-outs."""
        paths = [self.workdir / name / "outreach_suppression_list.json"
                 for name in ("outreach", "outreach_artur_pro", "outreach_service")]
        paths.append(self.workdir / "sales_agent" / "sales_stop_list.json")
        paths.append(self.workdir / "mailbox_controls" / "gmail-shared-suppression.json")
        emails: set[str] = set()
        domains: set[str] = set()
        for path in paths:
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(data, dict):
                    raise ValueError
                for field, target in (("emails", emails), ("domains", domains)):
                    values = data.get(field, [])
                    if not isinstance(values, list):
                        raise ValueError
                    target.update(str(item).strip().casefold() for item in values if str(item).strip())
            except Exception:
                raise MailerError("An Open Claw stop list is unreadable; sending is blocked") from None
        emails.update(self._global_suppressed(self.workdir))
        if self.profile_root:
            from mailbox_profile import snapshot
            emails.update(snapshot(self.profile_root)["emails"])
            native = importlib.import_module("src.tools.otpremaops_outreach")
            emails.update(native.previously_contacted({"agent_root": self.root, "agent_workdir": self.workdir}))
        csv_path = self.root / "do_not_contact.csv"
        if csv_path.exists():
            try:
                with csv_path.open(encoding="utf-8-sig", newline="") as stream:
                    reader = csv.DictReader(stream)
                    if "contact_value" not in (reader.fieldnames or []):
                        raise ValueError
                    emails.update(row["contact_value"].strip().casefold()
                                  for row in reader if "@" in row["contact_value"])
            except Exception:
                raise MailerError("Open Claw do-not-contact CSV is unreadable; sending is blocked") from None
        return emails, domains
