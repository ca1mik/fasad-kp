from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr
import re
from typing import Mapping


REQUIRED_COLUMNS: tuple[str, ...] = (
    "Компания",
    "Тип производства",
    "Город",
    "E-mail",
    "Телефон",
    "Сайт",
    "Источник",
    "Производство подтверждено",
    "Почему это производство",
    "Статус",
    "Дата 1-го письма",
    "Ответ",
    "Дата звонка",
    "Результат звонка",
    "Дата демо",
    "Результат демо",
    "Следующий контакт",
    "Следующий шаг",
    "Сделка",
    "Сумма, ₽",
    "Тема письма",
    "Текст письма",
    "OpenClaw Message-ID",
)


def normalize_email(value: str) -> str:
    """Return a stable mailbox-only representation for idempotency."""
    _, address = parseaddr(value or "")
    return address.strip().casefold()


def normalize_company(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def make_lead_key(email: str, company: str) -> str:
    return f"{normalize_email(email)}|{normalize_company(company)}"


@dataclass(frozen=True, slots=True)
class Lead:
    row_number: int
    values: Mapping[str, str]

    def get(self, column: str, default: str = "") -> str:
        value = self.values.get(column, default)
        return default if value is None else str(value).strip()

    @property
    def company(self) -> str:
        return self.get("Компания")

    @property
    def email(self) -> str:
        return normalize_email(self.get("E-mail"))

    @property
    def key(self) -> str:
        return make_lead_key(self.email, self.company)


@dataclass(frozen=True, slots=True)
class SendResult:
    message_id: str
    thread_id: str = ""
    provider_id: str = ""


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    id: str
    message_id: str
    in_reply_to: str
    references: tuple[str, ...]
    from_address: str
    subject: str
    body: str
    received_at: datetime
    thread_id: str = ""
    automated: bool = False

