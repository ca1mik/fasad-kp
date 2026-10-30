from models import Lead
from workflow import is_eligible, select_eligible


def lead(**changes: str) -> Lead:
    values = {
        "Компания": "Фасад",
        "E-mail": "Sales@Example.COM",
        "Производство подтверждено": "Да",
        "Статус": "Новый",
        "Дата 1-го письма": "",
        "OpenClaw Message-ID": "",
    }
    values.update(changes)
    return Lead(2, values)


def test_only_confirmed_new_lead_with_email_is_selected() -> None:
    assert is_eligible(lead())
    assert not is_eligible(lead(**{"Производство подтверждено": "Нет"}))
    assert not is_eligible(lead(**{"Статус": "Ответили"}))
    assert not is_eligible(lead(**{"E-mail": ""}))


def test_sent_date_or_message_id_blocks_lead() -> None:
    assert not is_eligible(lead(**{"Дата 1-го письма": "2026-09-22"}))
    assert not is_eligible(lead(**{"OpenClaw Message-ID": "<sent@example.com>"}))


def test_duplicate_stable_keys_are_failed_closed() -> None:
    first = lead()
    duplicate = Lead(3, {**first.values, "Компания": "  ФАСАД  ", "E-mail": "sales@example.com"})
    assert select_eligible([first, duplicate]) == []

