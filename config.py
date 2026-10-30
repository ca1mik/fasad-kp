from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


class ConfigError(ValueError):
    pass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().casefold()
    if value in {"1", "true", "yes", "да", "on"}:
        return True
    if value in {"0", "false", "no", "нет", "off"}:
        return False
    raise ConfigError(f"{name} должен быть true или false")


def _int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        result = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должен быть целым числом") from exc
    if result < minimum:
        raise ConfigError(f"{name} должен быть не меньше {minimum}")
    return result


def validate_demo_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError("DEMO_URL должен быть полным http(s)-адресом")
    return value


def validate_public_demo_url(value: str) -> str:
    """Prevent a live campaign from pointing recipients to a local or example URL."""
    parsed = urlparse(validate_demo_url(value))
    host = (parsed.hostname or "").casefold()
    reserved = (".localhost", ".local", ".test", ".invalid", ".example")
    example_hosts = ("example.com", "example.org", "example.net")
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or not host
        or "." not in host
        or host == "localhost"
        or any(host == domain or host.endswith("." + domain) for domain in example_hosts)
        or host.endswith(reserved)
        or all(part.isdigit() for part in host.split("."))
    ):
        raise ConfigError("для реальной отправки DEMO_URL должен быть публичным HTTPS-адресом")
    return value


@dataclass(frozen=True, slots=True)
class Config:
    mail_provider: str
    mail_address: str
    mail_auth_mode: str
    mail_app_password: str
    mail_display_name: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    imap_host: str
    imap_port: int
    imap_folder: str
    oauth_client_id: str
    oauth_client_secret: str
    oauth_refresh_token: str
    oauth_token_url: str
    google_service_account_json: str
    google_oauth_client_id: str
    google_oauth_client_secret: str
    google_oauth_refresh_token: str
    google_sheet_id: str
    google_sheet_name: str
    demo_url: str
    daily_send_limit: int
    dry_run: bool
    enable_followups: bool
    timezone_name: str
    state_path: Path
    log_path: Path
    http_timeout: int

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @classmethod
    def from_env(cls, env_file: str | Path | None = None, *, sample: bool = False) -> "Config":
        if env_file:
            path = Path(env_file)
            if not path.is_file():
                raise ConfigError(f"Файл окружения не найден: {path}")
            load_dotenv(path, override=True)
        else:
            load_dotenv(override=False)

        timezone_name = os.getenv("TIMEZONE", "Europe/Moscow").strip()
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"Неизвестный TIMEZONE: {timezone_name}") from exc

        provider = os.getenv("MAIL_PROVIDER", "gmail").strip().casefold()
        auth_mode = os.getenv("MAIL_AUTH_MODE", "oauth").strip().casefold()
        security = os.getenv("SMTP_SECURITY", "starttls").strip().casefold()
        if provider not in {"gmail", "outlook", "yandex", "mailru", "smtp"}:
            raise ConfigError("MAIL_PROVIDER: gmail, outlook, yandex, mailru или smtp")
        if auth_mode not in {"oauth", "app_password"}:
            raise ConfigError("MAIL_AUTH_MODE: oauth или app_password")
        if security not in {"starttls", "ssl"}:
            raise ConfigError("SMTP_SECURITY: starttls или ssl")

        service_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        if service_json:
            try:
                parsed = json.loads(service_json)
                if not isinstance(parsed, dict):
                    raise ValueError
            except (json.JSONDecodeError, ValueError) as exc:
                raise ConfigError("GOOGLE_SERVICE_ACCOUNT_JSON содержит некорректный JSON") from exc

        demo_default = "https://demo.example.com" if sample else ""
        demo_url = validate_demo_url(os.getenv("DEMO_URL", demo_default))
        return cls(
            mail_provider=provider,
            mail_address=os.getenv("MAIL_ADDRESS", "").strip(),
            mail_auth_mode=auth_mode,
            mail_app_password=os.getenv("MAIL_APP_PASSWORD", ""),
            mail_display_name=os.getenv("MAIL_DISPLAY_NAME", "").strip(),
            smtp_host=os.getenv("SMTP_HOST", "").strip(),
            smtp_port=_int("SMTP_PORT", 587),
            smtp_security=security,
            imap_host=os.getenv("IMAP_HOST", "").strip(),
            imap_port=_int("IMAP_PORT", 993),
            imap_folder=os.getenv("IMAP_FOLDER", "INBOX").strip() or "INBOX",
            oauth_client_id=os.getenv("OAUTH_CLIENT_ID", "").strip(),
            oauth_client_secret=os.getenv("OAUTH_CLIENT_SECRET", ""),
            oauth_refresh_token=os.getenv("OAUTH_REFRESH_TOKEN", ""),
            oauth_token_url=os.getenv("OAUTH_TOKEN_URL", "").strip(),
            google_service_account_json=service_json,
            google_oauth_client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip(),
            google_oauth_client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            google_oauth_refresh_token=os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN", ""),
            google_sheet_id=os.getenv(
                "GOOGLE_SHEET_ID", "1soUyxdgnlqU1hMRjtoHAeVii3qcPEMpsH6dXJeQbKqg"
            ).strip(),
            google_sheet_name=os.getenv("GOOGLE_SHEET_NAME", "Лиды").strip(),
            demo_url=demo_url,
            daily_send_limit=_int("DAILY_SEND_LIMIT", 15),
            dry_run=True if sample else _bool("DRY_RUN", True),
            enable_followups=_bool("ENABLE_FOLLOWUPS", False),
            timezone_name=timezone_name,
            state_path=Path(os.getenv("STATE_PATH", "data/outreach.sqlite3")),
            log_path=Path(os.getenv("LOG_PATH", "logs/outreach.jsonl")),
            http_timeout=_int("HTTP_TIMEOUT", 30),
        )

    def validate_external(self) -> None:
        if not self.dry_run:
            validate_public_demo_url(self.demo_url)
        missing: list[str] = []
        if not self.google_sheet_id:
            missing.append("GOOGLE_SHEET_ID")
        if not self.mail_address:
            missing.append("MAIL_ADDRESS")
        if not self.google_service_account_json and not all(
            (self.google_oauth_client_id, self.google_oauth_client_secret, self.google_oauth_refresh_token)
        ):
            missing.append("Google credentials")
        if self.mail_auth_mode == "app_password" and not self.mail_app_password:
            missing.append("MAIL_APP_PASSWORD")
        if self.mail_auth_mode == "oauth" and not all(
            (self.oauth_client_id, self.oauth_client_secret, self.oauth_refresh_token)
        ):
            missing.append("mail OAuth credentials")
        if self.mail_provider == "smtp" and (not self.smtp_host or not self.imap_host):
            missing.append("SMTP_HOST/IMAP_HOST")
        if missing:
            raise ConfigError("Не заполнены: " + ", ".join(missing))

