from datetime import datetime, timezone
import csv
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
import json
from pathlib import Path
import shutil
from zipfile import ZipFile

import pytest

from scripts.build_serbia_outreach_pack import build_pack, local_exclusions
from serbia_outreach import CampaignError, CampaignState, ROOT, read_leads

NOW = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    for name in ("sales/serbia/campaign.json", "sales/serbia/campaign_leads.csv",
                 "sales/serbia/consent-confirmation-2026-09-28.md",
                 "sales/serbia/market-validation-2026-09-28.md", "docs/OUTREACH_HANDOFF.md"):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    # This fixture models the first batch at its historical NOW. Keep it stable
    # when the real queue later receives separately attested new recipients.
    queue = root / "sales/serbia/campaign_leads.csv"
    with queue.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        original = [row for row in reader if "consent-confirmation-2026-09-28.md" in row["consent_evidence"]]
    assert len(original) == 12
    with queue.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(original)
    return root


def test_pack_has_ten_individual_messages_no_excluded_contacts_or_secrets(project, tmp_path):
    result = build_pack(project, tmp_path / "pack", NOW)
    assert result["prepared"] == 10 and result["sent"] == 0
    assert len(result["excluded"]) == 2
    with ZipFile(result["archive"]) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len([name for name in names if name.endswith(".eml")]) == 10
        assert len([name for name in names if name.endswith(".txt") and name.startswith("messages/")]) == 10
        assert not any(name.endswith((".env", ".sqlite3", ".db", ".pdf")) for name in names)
        assert not any("proposal" in name for name in names)
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["attachments"] == []
        assert manifest["sender"] == "koallalenivaa@gmail.com"
        assert "check_mailbox_sent_folder" in manifest["preflight_required"]
        for row in manifest["recipients"]:
            message = BytesParser(policy=policy.default).parsebytes(archive.read(row["eml"]))
            assert parseaddr(message["From"])[1] == manifest["sender"]
            assert message["To"] == row["email"]
            assert str(message["Subject"]) == row["subject"]
            assert message.get("Cc") is None and message.get("Bcc") is None
            assert not list(message.iter_attachments())
            body = message.get_content()
            assert "Калдин Лев" in body and "Projekat: Fasad Flow" in body
            assert "[" not in body and "]" not in body


def test_pack_does_not_overwrite_existing_output(project, tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    marker = destination / "user-file.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(CampaignError, match="already exists"):
        build_pack(project, destination, NOW)
    assert marker.read_text(encoding="utf-8") == "keep"


def test_pack_excludes_previous_smtp_reservation_and_opt_out(project, tmp_path):
    data = project / "data" / "serbia-outreach"
    data.mkdir(parents=True)
    state = CampaignState(data / "campaign.sqlite3")
    lead = read_leads(project / "sales" / "serbia" / "campaign_leads.csv")[0]
    state.reserve_message(lead, "<previous@gmail.com>", NOW)
    result = build_pack(project, tmp_path / "pack", NOW)
    assert result["prepared"] == 9
    assert any(row["email"] == lead["email"] and row["reason"] == "previous_local_attempt"
               for row in result["excluded"])


def test_pack_excludes_any_existing_gmail_record(project, tmp_path):
    data = project / "data" / "serbia-outreach"
    data.mkdir(parents=True)
    (data / "gmail-deliveries.jsonl").write_text(
        json.dumps({"email": "info@drvokod.rs", "status": "uncertain"}) + "\n", encoding="utf-8")
    result = build_pack(project, tmp_path / "pack", NOW)
    assert result["prepared"] == 9
    assert any(row["email"] == "info@drvokod.rs" for row in result["excluded"])


def test_malformed_gmail_journal_fails_closed(tmp_path):
    (tmp_path / "gmail-deliveries.jsonl").write_text('{"status":"sent"}\n', encoding="utf-8")
    with pytest.raises(CampaignError, match="invalid record"):
        local_exclusions(tmp_path)
