from datetime import datetime, timedelta, timezone

import pytest

from replies import classify_reply


MOSCOW = timezone(timedelta(hours=3))
RECEIVED = datetime(2026, 9, 22, 11, 30, tzinfo=MOSCOW)


def test_explicit_opt_out_dominates_positive_and_defer_signals() -> None:
    result = classify_reply("Интересно, но не пишите сейчас, возможно через месяц", RECEIVED)

    assert result == {
        "Ответ": "Интересно, но не пишите сейчас, возможно через месяц",
        "Статус": "Отказ",
    }


@pytest.mark.parametrize("phrase", ["Не интересно", "Неинтересно", "Не надо", "Отпишите меня"])
def test_common_refusals(phrase: str) -> None:
    assert classify_reply(phrase, RECEIVED)["Статус"] == "Отказ"


def test_quoted_outreach_and_signature_do_not_supply_intent() -> None:
    body = "Пока затрудняюсь ответить.\n\nС уважением,\nАнна\n\nOn Tue, Sep 22 wrote:\n> Вам интересно демо?\n> Давайте созвонимся."

    assert classify_reply(body, RECEIVED) == {
        "Ответ": "Пока затрудняюсь ответить.",
        "Статус": "Ответили",
        "Следующий шаг": "Ручная обработка",
    }


def test_a_quoted_refusal_does_not_override_new_positive_reply() -> None:
    body = "Да, интересно.\n\nОт: sales@example.test\nКому: anna@example.test\nТема: Предложение\nНе пишите нам"

    assert classify_reply(body, RECEIVED) == {
        "Ответ": "Да, интересно.",
        "Статус": "Ответили",
        "Следующий шаг": "Позвонить / назначить демо",
    }


def test_agreed_demo_with_explicit_date_and_time() -> None:
    result = classify_reply("Да, давайте демо 25 сентября в 15:30", RECEIVED)

    assert result["Статус"] == "Демо назначено"
    assert result["Дата демо"] == "2026-09-25T15:30:00+03:00"


def test_agreed_demo_with_numeric_date_and_time() -> None:
    result = classify_reply("Договорились на демо 25.09 в 15:30", RECEIVED)

    assert result["Дата демо"] == "2026-09-25T15:30:00+03:00"


@pytest.mark.parametrize(
    "body",
    [
        "Можно демо как-нибудь на следующей неделе?",
        "Не уверен, что согласен на демо 25.09 в 15:30",
        "Да, давайте демо 25.09",
        "Да, давайте демо в 15:30",
        "Да, давайте демо 15.09",
        "Возможно, давайте демо 25.09 в 15:30",
    ],
)
def test_no_false_scheduled_demo(body: str) -> None:
    result = classify_reply(body, RECEIVED)

    assert result["Статус"] != "Демо назначено"
    assert "Дата демо" not in result


def test_explicit_call_request_and_negated_call() -> None:
    assert classify_reply("Позвоните мне завтра", RECEIVED) == {
        "Ответ": "Позвоните мне завтра",
        "Статус": "Позвонить",
        "Следующий шаг": "Позвонить и назначить демо",
    }
    assert classify_reply("Не могу созвониться", RECEIVED)["Следующий шаг"] == "Ручная обработка"


def test_double_negative_is_not_treated_as_opt_out() -> None:
    result = classify_reply("Мне не неинтересно, но нужно подумать", RECEIVED)

    assert result["Статус"] == "Ответили"
    assert result["Следующий шаг"] == "Ручная обработка"


def test_one_calendar_month_clamps_at_month_end() -> None:
    received = datetime(2025, 1, 31, 9, 0, tzinfo=MOSCOW)

    result = classify_reply("Не сейчас, свяжитесь через месяц", received)

    assert result["Следующий контакт"] == "2025-02-28"


def test_one_calendar_month_uses_leap_day() -> None:
    received = datetime(2024, 1, 31, 9, 0, tzinfo=MOSCOW)

    assert classify_reply("Давайте позже, через месяц", received)["Следующий контакт"] == "2024-02-29"


def test_vague_later_gets_fixed_review_date() -> None:
    result = classify_reply("Сейчас не готов, вернемся позже", RECEIVED)

    assert result == {
        "Ответ": "Сейчас не готов, вернемся позже",
        "Статус": "Ответили",
        "Следующий контакт": "2026-09-29",
        "Следующий шаг": "Связаться повторно",
    }


def test_response_is_limited_to_ten_thousand_characters() -> None:
    assert len(classify_reply("?" * 10_500, RECEIVED)["Ответ"]) == 10_000


def test_naive_received_at_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        classify_reply("Да", datetime(2026, 9, 22))
