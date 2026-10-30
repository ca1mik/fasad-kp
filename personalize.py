from __future__ import annotations

from models import Lead


class MessageTemplateError(ValueError):
    pass


def render_message(lead: Lead, demo_url: str) -> tuple[str, str]:
    """Render only the spreadsheet-authored message and its one documented token."""
    subject = lead.get("Тема письма")
    body = lead.get("Текст письма")
    if not subject:
        raise MessageTemplateError("пустая тема письма")
    if not body:
        raise MessageTemplateError("пустой текст письма")
    rendered = body.replace("{DEMO_URL}", demo_url)
    if "{DEMO_URL}" in rendered:
        raise MessageTemplateError("placeholder DEMO_URL не заменён")
    if demo_url not in rendered:
        raise MessageTemplateError("в письме отсутствует DEMO_URL")
    return subject, rendered

