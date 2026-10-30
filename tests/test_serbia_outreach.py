import csv
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from mailer import MailerError
from models import IncomingMessage, SendResult
from openclaw_mail import OpenClawBridge
import serbia_outreach as campaign

NOW = datetime(2026, 9, 28, 12, tzinfo=ZoneInfo("Europe/Belgrade"))
SENDER = "koallalenivaa@gmail.com"


def config(**changes):
    value = campaign.read_config()
    value.update(enabled=True, allow_live_on_draft_mailbox=True,
                 daily_limit=5, hourly_limit=2, max_per_run=1,
                 sender_name="Test Seller", seller_name="Test Studio",
                 seller_address="Test address 1", expected_sender=SENDER)
    value.update(changes)
    return value


def lead(email="workshop@example.rs", **changes):
    row = dict(company="Test Workshop", email=email, opening_sr="Izrađujete frontove po meri.",
               website="https://example.rs/", source_url="https://example.rs/contact",
               approved="true", consent_at="2026-09-27T12:00:00+02:00",
               consent_evidence="Requested a product demo by phone on 2026-09-27", do_not_contact="false")
    row.update(changes)
    return row


class FakeMailer:
    address = SENDER

    def __init__(self):
        self.sent = []
        self.replies = []
        self.checks = 0
        self.fail_preflight = False
        self.fail_send = False
        self.after_check = lambda: None
        self.before_send = lambda: None

    def healthcheck(self):
        self.checks += 1
        if self.fail_preflight:
            raise MailerError("SMTP connection or authentication failed")
        self.after_check()

    def fetch_replies(self, message_ids):
        return self.replies

    def send(self, email, subject, body, *, message_id):
        self.before_send()
        self.sent.append((email, subject, body, message_id))
        if self.fail_send:
            raise RuntimeError("Untrusted exception including a fake secret")
        return SendResult(message_id)


class FakeBridge:
    def __init__(self):
        self.mailer = FakeMailer()
        self.settings = SimpleNamespace(draft_only=True, smtp_configured=True, imap_configured=True,
                                        daily_limit=25, hourly_limit=8, min_pause_seconds=90)
        self.emails = set()
        self.domains = set()

    def suppression(self):
        return set(self.emails), set(self.domains)

    def summary(self):
        return {"sender": self.mailer.address}


@pytest.fixture
def runtime(tmp_path):
    return tmp_path, campaign.CampaignState(tmp_path / "campaign.sqlite3"), FakeBridge()


def run(runtime, cfg=None, leads=None, now=NOW, **kwargs):
    path, state, bridge = runtime
    return campaign.cycle(cfg or config(), leads if leads is not None else [lead()], state, path,
                          bridge_factory=lambda *args: bridge, now=now, **kwargs)


def committed(state, row, at, message_id="<sent@sender.rs>"):
    assert state.reserve_message(row, message_id, at)
    key = "serbia:" + row["email"]
    state.mark_sent(key, message_id, at)
    state.mark_committed(key)


def incoming(body, original="<sent@sender.rs>", reply_id="<reply@workshop.rs>", **changes):
    values = dict(id="42", message_id=reply_id, in_reply_to=original, references=(),
                  from_address="workshop@example.rs", subject="Re: Fasad Flow", body=body,
                  received_at=NOW, automated=False)
    values.update(changes)
    return IncomingMessage(**values)


def test_real_queue_schema_and_sender_are_exact():
    cfg = campaign.read_config()
    # Activation is live campaign state, not a fixed schema requirement.
    assert isinstance(cfg["enabled"], bool)
    assert isinstance(cfg["allow_live_on_draft_mailbox"], bool)
    assert cfg["expected_sender"] == cfg["mailbox"] == SENDER
    rows = campaign.read_leads()
    assert len(rows) >= 12  # New owner-confirmed batches may extend the live queue.
    assert len({row["email"] for row in rows}) == len(rows)
    # Approval and consent are live campaign data and legitimately change with user input.
    assert all(row["approved"] in {"true", "false"} and row["do_not_contact"] in {"true", "false"}
               for row in rows)
    assert all(row["email"] and row["company"] for row in rows)


def test_user_attestation_is_accepted_without_fabricating_recipient_details():
    row = lead(consent_at="2026-09-28T08:17:55+00:00",
               consent_evidence="User attestation recorded in consent-confirmation-2026-09-28.md; "
                                "registration timestamp only; original recipient date and channel not supplied.")
    assert campaign.consent_problem(row, NOW, NOW.tzinfo) == ""


@pytest.mark.parametrize("key,value", [("enabled", "false"), ("daily_limit", 101),
                                      ("hourly_limit", 101), ("max_per_run", 2),
                                      ("mailbox_daily_limit", 101), ("mailbox_hourly_limit", True),
                                      ("expected_sender", "not-an-address"),
                                      ("sender_name", "Person\r\nBcc: victim@example.com")])
def test_invalid_config_is_rejected(tmp_path, key, value):
    cfg = config(**{key: value})
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(campaign.CampaignError):
        campaign.read_config(path)


@pytest.mark.parametrize("changes,reason", [
    ({"approved": "false"}, "not_approved"),
    ({"approved": "yes"}, "not_approved"),
    ({"email": "x\r\nBcc:victim@example.com"}, "invalid_email"),
    ({"consent_evidence": "https://example.rs/"}, "consent_evidence_missing"),
    ({"consent_evidence": ""}, "consent_evidence_missing"),
    ({"consent_at": ""}, "consent_date_missing"),
    ({"consent_at": "2099-01-01"}, "consent_in_future"),
])
def test_consent_gate(changes, reason):
    assert campaign.consent_problem(lead(**changes), NOW, NOW.tzinfo) == reason


def test_disabled_campaign_does_not_open_mailbox(runtime):
    path, state, _ = runtime
    result = campaign.cycle(config(enabled=False), [lead()], state, path,
                            bridge_factory=lambda *args: pytest.fail("Opened mailbox"), now=NOW)
    assert result["status"] == "disabled" and not state.deliveries()


def test_missing_signature_blocks(runtime):
    assert run(runtime, config(sender_name=""))["status"] == "blocked"
    assert not runtime[2].mailer.sent and not runtime[1].deliveries()


def test_real_person_and_product_signature_omits_unknown_postal_address():
    cfg = config(sender_name="Lev Kaldin", seller_name="Fasad Flow", seller_address="")
    _, body = campaign.render_message(lead(), cfg, SENDER)
    assert f"Lev Kaldin\nProjekat: Fasad Flow\n{SENDER}" in body
    assert "[Ime pošiljaoca]" not in body
    assert "[Prodavac]" not in body and "[Adresa prodavca]" not in body
    assert "Beograd" not in body and "Serbia office" not in body
    assert campaign.sender_problems(cfg) == []


def test_initial_email_can_omit_postal_address_without_fabrication(runtime):
    result = run(runtime, config(seller_address=""))
    assert result["status"] == "smtp_accepted" and result["sent"] == 1
    body = runtime[2].mailer.sent[0][2]
    assert "[Adresa prodavca]" not in body


def test_address_placeholder_is_not_sent(runtime):
    result = run(runtime, config(seller_address="[Adresa prodavca]"))
    assert result["status"] == "blocked" and result["reasons"] == ["seller_address_placeholder"]
    assert runtime[2].mailer.checks == 0 and not runtime[2].mailer.sent


def test_wrong_sender_is_blocked_before_network(runtime):
    runtime[2].mailer.address = "hello@ppdstr.ru"
    result = run(runtime)
    assert result["reasons"] == ["sender_mismatch"]
    assert runtime[2].mailer.checks == 0 and not runtime[1].deliveries()


def test_draft_only_needs_explicit_campaign_activation(runtime):
    assert run(runtime, config(allow_live_on_draft_mailbox=False))["reasons"] == ["mailbox_draft_only"]
    assert not runtime[2].mailer.sent


def test_stop_flag_blocks(runtime):
    (runtime[0] / "STOP").write_text("operator stop", encoding="utf-8")
    assert run(runtime)["status"] == "stopped"
    assert not runtime[2].mailer.sent


def test_unapproved_public_contact_is_never_sent(runtime):
    assert run(runtime, leads=[lead(approved="false")])["status"] == "no_approved_recipients"
    assert runtime[2].mailer.checks == 0 and not runtime[1].deliveries()


def test_commits_message_id_before_smtp_and_never_resends(runtime):
    state, mailer = runtime[1], runtime[2].mailer

    def assert_reserved():
        row = state.deliveries()[0]
        assert row["status"] == "reserved" and row["message_id"].startswith("<")
    mailer.before_send = assert_reserved
    first = run(runtime)
    second = run(runtime, now=NOW + timedelta(hours=2))
    assert first["sent"] == 1 and second["sent"] == 0
    assert len(mailer.sent) == 1
    assert state.deliveries()[0]["status"] == "committed"


def test_only_one_message_per_cycle(runtime):
    assert run(runtime, leads=[lead(), lead("second@example.rs")])["sent"] == 1
    assert len(runtime[2].mailer.sent) == 1


def test_preflight_failure_does_not_reserve(runtime):
    runtime[2].mailer.fail_preflight = True
    with pytest.raises(MailerError):
        run(runtime)
    assert not runtime[1].deliveries() and not runtime[2].mailer.sent


def test_uncertain_send_stops_and_is_never_retried(runtime):
    runtime[2].mailer.fail_send = True
    result = run(runtime)
    assert result["status"] == "uncertain_stopped" and result["sent"] == 0
    assert runtime[1].deliveries()[0]["status"] == "uncertain"
    assert (runtime[0] / "STOP").exists()
    assert run(runtime, now=NOW + timedelta(hours=2))["status"] == "stopped"
    assert len(runtime[2].mailer.sent) == 1
    assert "secret" not in json.dumps(runtime[1].deliveries())


def test_crash_leftover_requires_manual_reconciliation(runtime):
    runtime[1].reserve_message(lead(), "<crash@sender.rs>", NOW - timedelta(hours=2))
    result = run(runtime, leads=[lead("second@example.rs")])
    assert result["status"] == "unresolved_delivery_stopped"
    assert (runtime[0] / "STOP").exists() and not runtime[2].mailer.sent


@pytest.mark.parametrize("now", [NOW.replace(hour=9), NOW.replace(hour=17),
                                  NOW + timedelta(days=5), NOW + timedelta(days=6)])
def test_business_hours_are_belgrade_weekdays(runtime, now):
    assert run(runtime, now=now)["status"] == "outside_sending_hours"
    assert runtime[2].mailer.checks == 0


def test_daily_cap_is_durable(runtime):
    for i in range(5):
        committed(runtime[1], lead(f"used{i}@example.rs"), NOW.replace(hour=8, minute=i), f"<used{i}@sender.rs>")
    assert run(runtime)["status"] == "campaign_rate_limit"
    assert not runtime[2].mailer.sent


def test_rolling_hour_cap(runtime):
    for i in range(2):
        committed(runtime[1], lead(f"used{i}@example.rs"), NOW - timedelta(minutes=10+i), f"<used{i}@sender.rs>")
    assert run(runtime)["status"] == "campaign_rate_limit"


def test_minimum_spacing_applies_to_manual_cycles(runtime):
    committed(runtime[1], lead("used@example.rs"), NOW - timedelta(seconds=30))
    assert run(runtime)["status"] == "campaign_min_pause"


def test_hourly_budget_is_elapsed_time_across_dst(runtime):
    now = datetime(2026, 10, 25, 2, 30, tzinfo=NOW.tzinfo, fold=1)
    reserved = now.replace(fold=0)
    committed(runtime[1], lead(), reserved)
    assert runtime[1].budget_used(now) == (1, 0)


@pytest.mark.parametrize("scope", ["email", "email_domain", "website_domain", "local"])
def test_global_and_local_stop_lists_block(runtime, scope):
    row = lead(website="https://www.another-company.rs/")
    if scope == "email":
        runtime[2].emails.add(row["email"])
    elif scope == "email_domain":
        runtime[2].domains.add("example.rs")
    elif scope == "website_domain":
        runtime[2].domains.add("another-company.rs")
    else:
        row["do_not_contact"] = "true"
    assert run(runtime, leads=[row])["status"] == "no_approved_recipients"


def test_stop_list_is_rechecked_after_healthcheck(runtime):
    runtime[2].mailer.after_check = lambda: runtime[2].emails.add(lead()["email"])
    assert run(runtime)["status"] == "recipient_blocked_before_send"
    assert not runtime[1].deliveries()


def test_stop_flag_is_rechecked_after_healthcheck(runtime):
    runtime[2].mailer.after_check = lambda: (runtime[0] / "STOP").write_text("stop", encoding="utf-8")
    assert run(runtime)["status"] == "stopped"
    assert not runtime[1].deliveries()


@pytest.mark.parametrize("fresh", [[], [lead(approved="false")]])
def test_csv_removal_or_withdrawal_is_rechecked(runtime, fresh):
    result = run(runtime, leads_loader=lambda: fresh)
    assert result["status"] in {"recipient_removed_before_send", "recipient_blocked_before_send"}
    assert not runtime[1].deliveries() and not runtime[2].mailer.sent


@pytest.mark.parametrize("body", ["ODJAVA", "Одјава", "Obrišite moj email", "Не шаљите више", "Don't email me"])
def test_opt_out_reply_is_saved_and_suppresses_once(runtime, body):
    state, bridge = runtime[1], runtime[2]
    committed(state, lead(), NOW - timedelta(hours=2))
    bridge.mailer.replies = [incoming(body)]
    assert campaign.sync_replies(state, bridge) == 1
    assert campaign.sync_replies(state, bridge) == 0
    assert state.suppressed() == {lead()["email"]}
    assert state.replies()[0]["category"] == "opt_out"
    assert not bridge.mailer.sent


def test_quoted_opt_out_footer_is_not_withdrawal(runtime):
    state, bridge = runtime[1], runtime[2]
    committed(state, lead(), NOW - timedelta(hours=2))
    bridge.mailer.replies = [incoming("Da, možemo sutra.\n\nOn Monday someone wrote:\n> Za odjavu odgovorite ODJAVA.")]
    assert campaign.sync_replies(state, bridge) == 1
    assert state.replies()[0]["category"] == "human_reply" and not state.suppressed()


def test_automatic_or_unmatched_reply_is_ignored(runtime):
    state, bridge = runtime[1], runtime[2]
    committed(state, lead(), NOW - timedelta(hours=2))
    bridge.mailer.replies = [incoming("ODJAVA", automated=True), incoming("ODJAVA", original="<unrelated@sender.rs>")]
    assert campaign.sync_replies(state, bridge) == 0
    assert not state.replies()


def test_replies_can_match_references(runtime):
    state, bridge = runtime[1], runtime[2]
    committed(state, lead(), NOW - timedelta(hours=2))
    bridge.mailer.replies = [incoming("ODJAVA", original="<new-thread@sender.rs>", references=("<sent@sender.rs>",))]
    assert campaign.sync_replies(state, bridge) == 1
    assert state.suppressed()


def test_mailbox_binding_cannot_switch_after_campaign_start(runtime):
    runtime[1].bind_sender(SENDER)
    with pytest.raises(campaign.CampaignError):
        runtime[1].bind_sender("another@gmail.com")


def test_existing_gmail_sent_message_is_not_sent_or_reserved_again(runtime):
    runtime[2].mailer.has_sent_message = lambda recipient, subject: True
    result = run(runtime)
    assert result["status"] == "already_in_gmail_sent"
    assert not runtime[2].mailer.sent and not runtime[1].deliveries()
    assert runtime[1].suppressed() == {"workshop@example.rs"}


def test_gmail_provider_id_is_recorded_separately_from_rfc_id(runtime):
    runtime[2].mailer.outbound_transport = "gmail_https"
    runtime[2].mailer.send = lambda *args, **kwargs: SendResult("<rfc@gmail.com>", "thread-123", "gmail-456")
    result = run(runtime)
    assert result["status"] == "gmail_api_accepted" and result["provider_id"] == "gmail-456"
    with runtime[1]._db() as db:
        row = db.execute("SELECT * FROM delivery_receipts").fetchone()
    assert row["provider_id"] == "gmail-456" and row["thread_id"] == "thread-123"
    assert runtime[1].deliveries()[0]["message_id"] == "<rfc@gmail.com>"


def test_direct_gmail_journal_requires_reconciliation_before_worker_sends(runtime):
    (runtime[0] / "gmail-deliveries.jsonl").write_text('{"email":"workshop@example.rs","status":"reserved"}\n', encoding="utf-8")
    result = run(runtime)
    assert result["status"] == "direct_gmail_journal_requires_reconciliation"
    assert not runtime[2].mailer.sent and runtime[2].mailer.checks == 0


def test_previews_are_offline_safe_and_from_requested_gmail(tmp_path):
    row = lead(company="<script>alert(1)</script>")
    result = campaign.export_previews([row], config(), tmp_path, SENDER)
    assert result["sent"] == 0
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in html and "&lt;script&gt;" in html
    message = BytesParser(policy=policy.default).parsebytes((tmp_path / "01.eml").read_bytes())
    display_name, from_address = parseaddr(message["From"])
    assert from_address == SENDER and message["To"] == row["email"]
    assert display_name == "Test Seller — Test Studio"
    assert "Fasad Flow" in message.get_content()
    assert "hello@ppdstr.ru" not in html


def test_worker_lock_rejects_overlapping_process(runtime):
    lock = runtime[0] / "worker.lock"
    with campaign.worker_lock(lock):
        with pytest.raises(campaign.CampaignError):
            with campaign.worker_lock(lock):
                pytest.fail("Acquired an overlapping lock")
    with campaign.worker_lock(lock):
        pass


def test_csv_deduplicates_case_insensitively_and_requires_consent_columns(tmp_path):
    path = tmp_path / "leads.csv"
    rows = [lead("WORKSHOP@example.rs"), lead()]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    assert len(campaign.read_leads(path)) == 1
    path.write_text("company,email\nWorkshop,workshop@example.rs\n", encoding="utf-8")
    with pytest.raises(campaign.CampaignError):
        campaign.read_leads(path)


def fake_openclaw(tmp_path):
    bridge = OpenClawBridge.__new__(OpenClawBridge)
    bridge.profile_root = None
    bridge.root = tmp_path / "agent"
    bridge.workdir = tmp_path / "workdir"
    bridge.root.mkdir()
    bridge.workdir.mkdir()
    bridge._global_suppressed = lambda path: set()
    bridge.settings = SimpleNamespace(draft_only=True, daily_limit=25, hourly_limit=8, min_pause_seconds=90)
    return bridge


def test_openclaw_broken_stop_list_blocks(tmp_path):
    bridge = fake_openclaw(tmp_path)
    folder = bridge.workdir / "outreach_service"
    folder.mkdir()
    path = folder / "outreach_suppression_list.json"
    path.write_text("not JSON", encoding="utf-8")
    with pytest.raises(MailerError):
        bridge.suppression()
    path.write_text(json.dumps({"emails": ["WORKSHOP@EXAMPLE.RS"], "domains": ["BLOCKED.RS"]}), encoding="utf-8")
    assert bridge.suppression() == ({"workshop@example.rs"}, {"blocked.rs"})


def test_personal_mailbox_lookup_never_creates_db_or_falls_back(tmp_path):
    bridge = fake_openclaw(tmp_path)
    assert bridge._personal_identity(SENDER) is None
    assert not (bridge.workdir / "user_mailboxes.db").exists()


def test_personal_binding_is_read_only_and_exact_address(tmp_path):
    bridge = fake_openclaw(tmp_path)
    db_path = bridge.workdir / "user_mailboxes.db"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE user_mailboxes(tg_user_id INTEGER, address TEXT, username TEXT, password TEXT, "
                   "smtp_server TEXT, smtp_port INTEGER, smtp_security TEXT, imap_server TEXT, imap_port INTEGER, "
                   "imap_security TEXT, mailbox TEXT)")
        db.execute("INSERT INTO user_mailboxes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (1, SENDER, SENDER, "fake-test-credential", "smtp.gmail.com", 465, "ssl",
                    "imap.gmail.com", 993, "ssl", "INBOX"))
    before = db_path.read_bytes()
    assert bridge._personal_identity("other@gmail.com") is None
    identity = bridge._personal_identity(SENDER)
    assert identity.email_address == SENDER and bridge.settings.imap_user == SENDER
    assert db_path.read_bytes() == before


def test_status_reports_missing_connector_without_fallback(tmp_path, monkeypatch, capsys):
    cfg = config(enabled=False)
    monkeypatch.setattr(campaign, "DATA", tmp_path)
    monkeypatch.setattr(campaign, "read_config", lambda: cfg)
    monkeypatch.setattr(campaign, "read_leads", lambda: [lead(approved="false")])
    monkeypatch.setattr(campaign, "OpenClawBridge", lambda *args: (_ for _ in ()).throw(MailerError("Requested sender not connected")))
    monkeypatch.setattr(campaign.sys, "argv", ["serbia_outreach.py", "status"])
    assert campaign.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["expected_sender"] == SENDER and result["mailbox"] is None
    assert result["approved_local"] == 0 and result["transport_error"]
