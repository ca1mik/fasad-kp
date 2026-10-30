"""Deterministic classification of Russian-language email replies.

The classifier deliberately has a small vocabulary.  If a reply does not say
enough to choose a safe action, it is sent to manual processing instead of
guessing the sender's intent.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta


_REFUSAL_RE = re.compile(
    r"\b(?:"
    r"не\s+интерес(?:но|ует)|неинтерес(?:но|ует)|"
    r"не\s+надо|не\s+нужно|"
    r"не\s+пишите|не\s+звоните|"
    r"отпишите(?:\s+меня)?|отписаться|"
    r"удалите\s+(?:меня|мой\s+(?:адрес|номер))|"
    r"не\s+связывайтесь|отказываюсь"
    r")\b",
    re.IGNORECASE,
)

_DEFER_RE = re.compile(
    r"\b(?:не\s+сейчас|позже|не\s+готов(?:а|ы)?\s+сейчас|"
    r"верн(?:емся|ёмся)\s+(?:к\s+этому\s+)?позже|"
    r"через\s+\d*\s*(?:д(?:ень|ня|ней)|недел(?:ю|и|ь)|месяц(?:а|ев)?)|"
    r"через\s+(?:один|два|три)\s+месяц(?:а|ев)?|"
    r"в\s+следующем\s+месяце)\b",
    re.IGNORECASE,
)

_POSITIVE_RE = re.compile(
    r"\b(?:да|интересно|заинтересован(?:а|ы)?|готов(?:а|ы)?|"
    r"давайте|согласен|согласна|подходит|обсудим)\b",
    re.IGNORECASE,
)

_CALL_RE = re.compile(
    r"\b(?:позвоните|перезвоните|наберите|созвонимся|созвониться|"
    r"созвон|звонок|поговорим\s+по\s+телефону)\b",
    re.IGNORECASE,
)

_DEMO_RE = re.compile(
    r"\b(?:демо(?:нстраци[яюи])?|встреч(?:а|у|и)|презентаци[яюи])\b",
    re.IGNORECASE,
)

_AGREEMENT_RE = re.compile(
    r"\b(?:да|давайте|согласен|согласна|договорились|подходит|"
    r"подтверждаю|готов(?:а|ы)?|назначим|запланируем)\b",
    re.IGNORECASE,
)

_NEGATED_INTENT_RE = re.compile(
    r"\bне\s+(?:готов(?:а|ы)?|согласен|согласна|подходит|"
    r"хочу|могу|буду|получится|получается)\b",
    re.IGNORECASE,
)

_UNCERTAIN_RE = re.compile(
    r"\b(?:не\s+уверен(?:а|ы)?|может\s+быть|возможно|подумаю|надо\s+подумать)\b",
    re.IGNORECASE,
)

_QUOTE_BOUNDARY_RE = re.compile(
    r"^(?:-{2,}\s*(?:original message|исходное сообщение)\s*-*|"
    r"_{5,}|"
    r"(?:on\s+.+\s+wrote|.+\s+(?:на)?писал(?:а)?):\s*$)",
    re.IGNORECASE,
)

_HEADER_RE = re.compile(r"^(?:from|sent|to|subject|от|отправлено|кому|тема):\s+", re.IGNORECASE)

_SIGNATURE_RE = re.compile(
    r"^(?:--\s*$|с\s+уважением(?:[!,.])?\s*$|"
    r"(?:best\s+)?regards(?:[!,.])?\s*$|"
    r"отправлено\s+с\s+(?:iphone|android)|sent\s+from\s+my\s+iphone)",
    re.IGNORECASE,
)

_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

_WEEKDAYS = {
    "понедельник": 0,
    "вторник": 1,
    "среду": 2,
    "четверг": 3,
    "пятницу": 4,
    "субботу": 5,
    "воскресенье": 6,
}


def _clean_reply(body: str) -> str:
    """Remove common quoted-message and signature tails conservatively."""

    text = body.replace("\r\n", "\n").replace("\r", "\n")
    kept: list[str] = []

    for index, line in enumerate(text.split("\n")):
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if _QUOTE_BOUNDARY_RE.match(stripped):
            break
        # A mail-header block after some reply text starts the quoted message.
        if kept and _HEADER_RE.match(stripped):
            following = text.split("\n")[index : index + 4]
            header_count = sum(bool(_HEADER_RE.match(item.strip())) for item in following)
            if header_count >= 2 or stripped.lower().startswith(("from:", "от:")):
                break
        if kept and _SIGNATURE_RE.match(stripped):
            break
        kept.append(line.rstrip())

    while kept and not kept[-1].strip():
        kept.pop()
    while kept and not kept[0].strip():
        kept.pop(0)

    # Avoid producing giant spreadsheet cells while preserving whole Unicode
    # characters.  The sheet limit required by this module is 10,000 chars.
    return "\n".join(kept)[:10_000]


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _deferred_date(text: str, received: datetime) -> date:
    match = re.search(
        r"\bчерез\s*(?:(\d+|один|два|три)\s*)?"
        r"(день|дня|дней|неделю|недели|недель|месяц|месяца|месяцев)\b",
        text,
        re.IGNORECASE,
    )
    if match:
        values = {None: 1, "": 1, "один": 1, "два": 2, "три": 3}
        raw_number = match.group(1)
        amount = int(raw_number) if raw_number and raw_number.isdigit() else values[raw_number]
        unit = match.group(2).lower()
        if unit.startswith("месяц"):
            return _add_months(received.date(), amount)
        if unit.startswith("недел"):
            return received.date() + timedelta(weeks=amount)
        return received.date() + timedelta(days=amount)
    if re.search(r"\bв\s+следующем\s+месяце\b", text, re.IGNORECASE):
        return _add_months(received.date(), 1)
    # Vague postponements need a concrete review date but do not justify a
    # longer inferred delay.  One week is the fixed, documented review period.
    return received.date() + timedelta(days=7)


def _parse_date(text: str, received: datetime) -> date | None:
    numeric = re.search(r"(?<!\d)(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2}|\d{4}))?(?!\d)", text)
    if numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))
        raw_year = numeric.group(3)
        year = received.year if raw_year is None else int(raw_year)
        if raw_year is not None and len(raw_year) == 2:
            year += 2000
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if raw_year is None and candidate < received.date():
            try:
                candidate = candidate.replace(year=year + 1)
            except ValueError:
                return None
        return candidate

    iso = re.search(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    month_names = "|".join(_MONTHS)
    named = re.search(
        rf"(?<!\d)(\d{{1,2}})\s+({month_names})(?:\s+(\d{{4}}))?\b",
        text,
        re.IGNORECASE,
    )
    if named:
        day = int(named.group(1))
        month = _MONTHS[named.group(2).lower()]
        year = int(named.group(3)) if named.group(3) else received.year
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if named.group(3) is None and candidate < received.date():
            try:
                candidate = candidate.replace(year=year + 1)
            except ValueError:
                return None
        return candidate

    lowered = text.lower()
    if re.search(r"\bпослезавтра\b", lowered):
        return received.date() + timedelta(days=2)
    if re.search(r"\bзавтра\b", lowered):
        return received.date() + timedelta(days=1)
    if re.search(r"\bсегодня\b", lowered):
        return received.date()

    weekday = re.search(
        r"\b(?:(следующ(?:ий|ую|ее))\s+)?"
        r"(понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)\b",
        lowered,
    )
    if weekday:
        target = _WEEKDAYS[weekday.group(2)]
        days = (target - received.weekday()) % 7
        if days == 0 or weekday.group(1):
            days += 7
        return received.date() + timedelta(days=days)
    return None


def _parse_time(text: str) -> time | None:
    # A colon is unambiguously a time separator.  A dot is accepted only with
    # the Russian preposition "в", so a date such as 15.09 is never read as
    # 15:09.
    match = re.search(r"(?<!\d)(?:в\s*)?(\d{1,2}):(\d{2})(?!\d)", text, re.IGNORECASE)
    if not match:
        match = re.search(r"\bв\s+(\d{1,2})\.(\d{2})(?!\d)", text, re.IGNORECASE)
    if not match:
        match = re.search(r"\bв\s+(\d{1,2})\s*(?:час(?:а|ов)?|ч\.)\b", text, re.IGNORECASE)
        minute = 0
    else:
        minute = int(match.group(2))
    if not match:
        return None
    hour = int(match.group(1))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def _has_unnegated(pattern: re.Pattern[str], text: str) -> bool:
    """Reject intent words immediately governed by a Russian negation."""

    for match in pattern.finditer(text):
        prefix = text[max(0, match.start() - 18) : match.start()]
        if not re.search(r"\bне\s+(?:хочу\s+|могу\s+|готов\s+)?$", prefix, re.IGNORECASE):
            return True
    return False


def classify_reply(body: str, received_at: datetime) -> dict[str, str]:
    """Return conservative Google Sheet updates for one inbound reply.

    ``received_at`` must be timezone-aware.  Returned datetimes use its timezone
    and ISO 8601 format, making classification stable across host timezones.
    """

    if not isinstance(body, str):
        raise TypeError("body must be a string")
    if not isinstance(received_at, datetime) or received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError("received_at must be a timezone-aware datetime")

    reply = _clean_reply(body)
    result = {"Ответ": reply}
    normalized = re.sub(r"\s+", " ", reply).strip()

    # An explicit opt-out has priority over every other signal, including a
    # request to contact the sender at some later date.
    refusal_text = re.sub(r"\bне\s+не\s*интересно\b", "", normalized, flags=re.IGNORECASE)
    if _REFUSAL_RE.search(refusal_text):
        result["Статус"] = "Отказ"
        return result

    if _DEFER_RE.search(normalized):
        result.update(
            {
                "Статус": "Ответили",
                "Следующий контакт": _deferred_date(normalized, received_at).isoformat(),
                "Следующий шаг": "Связаться повторно",
            }
        )
        return result

    mentions_demo = bool(_DEMO_RE.search(normalized))
    agreement = (
        bool(_AGREEMENT_RE.search(normalized))
        and not bool(_NEGATED_INTENT_RE.search(normalized))
        and not bool(_UNCERTAIN_RE.search(normalized))
    )
    if mentions_demo and agreement:
        demo_date = _parse_date(normalized, received_at)
        demo_time = _parse_time(normalized)
        if demo_date is not None and demo_time is not None:
            scheduled = datetime.combine(demo_date, demo_time, tzinfo=received_at.tzinfo)
            result.update({"Статус": "Демо назначено", "Дата демо": scheduled.isoformat()})
        else:
            result.update({"Статус": "Ответили", "Следующий шаг": "Уточнить дату и время вручную"})
        return result

    if _has_unnegated(_CALL_RE, normalized):
        result.update({"Статус": "Позвонить", "Следующий шаг": "Позвонить и назначить демо"})
        return result

    if (
        _POSITIVE_RE.search(normalized)
        and not _NEGATED_INTENT_RE.search(normalized)
        and not _UNCERTAIN_RE.search(normalized)
    ):
        result.update({"Статус": "Ответили", "Следующий шаг": "Позвонить / назначить демо"})
        return result

    result.update({"Статус": "Ответили", "Следующий шаг": "Ручная обработка"})
    return result


__all__ = ["classify_reply"]
