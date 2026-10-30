import pytest

from config import ConfigError, validate_demo_url, validate_public_demo_url
from models import Lead
from personalize import MessageTemplateError, render_message


def test_demo_url_is_replaced() -> None:
    lead = Lead(2, {"Тема письма": "Тема", "Текст письма": "Демо: {DEMO_URL}"})
    subject, body = render_message(lead, "https://demo.example.test/show")
    assert subject == "Тема"
    assert body == "Демо: https://demo.example.test/show"


def test_template_without_demo_is_rejected() -> None:
    lead = Lead(2, {"Тема письма": "Тема", "Текст письма": "Без ссылки"})
    with pytest.raises(MessageTemplateError):
        render_message(lead, "https://demo.example.test")


@pytest.mark.parametrize("url", ["", "demo.example.test", "javascript:alert(1)"])
def test_invalid_demo_url_is_rejected(url: str) -> None:
    with pytest.raises(ConfigError):
        validate_demo_url(url)


@pytest.mark.parametrize("url", ["http://example.org", "http://127.0.0.1:8765", "https://demo.example.com", "https://demo.example.test"])
def test_live_campaign_requires_public_https_demo(url: str) -> None:
    with pytest.raises(ConfigError):
        validate_public_demo_url(url)


def test_live_campaign_accepts_public_https_demo() -> None:
    assert validate_public_demo_url("https://fasadflow.rs/serbia.html") == "https://fasadflow.rs/serbia.html"

