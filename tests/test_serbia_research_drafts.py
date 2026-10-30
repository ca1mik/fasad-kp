from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
import shutil

import pytest

import serbia_outreach as campaign
from scripts.build_serbia_research_drafts import build

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "sales/serbia/new-prospects-2026-09-29.csv"


def test_new_twenty_registry_remains_an_unapproved_research_snapshot():
    leads = campaign.read_leads(REGISTRY)
    assert len(leads) == 20
    assert len({row["email"] for row in leads}) == 20
    assert len({row["company"].casefold() for row in leads}) == 20
    assert all(row["approved"] == "false" and not row["consent_at"] and not row["consent_evidence"] for row in leads)
    assert all(campaign.EMAIL_RE.fullmatch(row["email"]) and row["source_url"].startswith("https://") for row in leads)


def test_live_promotion_requires_its_own_owner_attestation_not_public_sources():
    research = {row["email"]: row for row in campaign.read_leads(REGISTRY)}
    for row in campaign.read_leads():
        if row["email"] not in research or row["approved"] != "true":
            continue
        assert "consent-confirmation-wave2-2026-09-29.md" in row["consent_evidence"]
        assert "registration timestamp only" in row["consent_evidence"]
        assert row["consent_at"] and row["opening_sr"] == research[row["email"]]["opening_sr"]
        assert row["source_url"] == research[row["email"]]["source_url"]
        evidence = (ROOT / "sales/serbia/consent-confirmation-wave2-2026-09-29.md").read_text(encoding="utf-8")
        assert row["email"] in evidence and "ДА ВСЕ СОГЛАСНЫ" in evidence


def test_research_builder_never_calls_mail_and_produces_signed_single_recipient_drafts(tmp_path, monkeypatch):
    folder = tmp_path / "sales/serbia"
    folder.mkdir(parents=True)
    shutil.copyfile(REGISTRY, folder / REGISTRY.name)
    shutil.copyfile(ROOT / "sales/serbia/campaign.json", folder / "campaign.json")
    monkeypatch.setattr(campaign, "configured_bridge", lambda *args: pytest.fail("research must stay offline"))
    result = build(tmp_path)
    assert result["prepared"] == 20 and result["sent"] == 0 and result["approved"] == 0
    previews = Path(result["preview"]).parent
    assert len(list(previews.glob("*.eml"))) == 20
    for path in previews.glob("*.eml"):
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        assert parseaddr(message["From"])[1] == "koallalenivaa@gmail.com"
        assert "Калдин Лев" in str(message["From"]) and "Калдин Лев" in message.get_content()
        assert len(message.get_all("To")) == 1
        assert not message.get("Cc") and not message.get("Bcc") and not list(message.iter_attachments())
    assert REGISTRY.name in Path(result["preview"]).read_text(encoding="utf-8")
    assert not (tmp_path / "data/serbia-outreach/campaign.sqlite3").exists()
