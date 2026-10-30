from contextlib import contextmanager
from datetime import timedelta
import json
import sqlite3
from types import SimpleNamespace
import sys

import pytest

import mailbox_profile
from mailer import MailerError
from tests.test_serbia_outreach import NOW, SENDER, config, lead, run, runtime  # noqa: F401


def history(tmp_path, state="sent", when=NOW, stop=False):
    root = tmp_path / "existing"
    root.mkdir()
    path = root / "campaign.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE outbound(company,email,attempted_at,state); CREATE TABLE stops(email,company);")
        db.execute("INSERT INTO outbound VALUES(?,?,?,?)", ("Existing Company", "existing@example.rs", when.isoformat(), state))
        if stop:
            db.execute("INSERT INTO stops VALUES(?,?)", ("stop@example.rs", "Existing Company"))
    return root


def test_history_and_stops_are_readonly(tmp_path):
    root = history(tmp_path, stop=True)
    before = (root / "campaign.sqlite3").read_bytes()
    result = mailbox_profile.snapshot(root)
    assert result["emails"] == {"stop@example.rs", "existing@example.rs"}
    assert result["companies"] == {"existing company"}
    assert (root / "campaign.sqlite3").read_bytes() == before


@pytest.mark.parametrize("state", ["sent", "rejected", "sending", "unknown"])
def test_all_attempt_states_consume_budget(tmp_path, state):
    result = mailbox_profile.budget(history(tmp_path, state), NOW)
    assert result["daily"] == 1 and result["hourly"] == 1
    assert result["uncertain"] == int(state in {"sending", "unknown"})


def test_budget_uses_belgrade_day_and_rolling_hour(tmp_path):
    result = mailbox_profile.budget(history(tmp_path, when=NOW - timedelta(hours=2)), NOW)
    assert result["daily"] == 1 and result["hourly"] == 0


def test_missing_or_malformed_shared_history_blocks(tmp_path):
    with pytest.raises(MailerError):
        mailbox_profile.snapshot(tmp_path)
    (tmp_path / "campaign.sqlite3").write_bytes(b"bad db")
    with pytest.raises(MailerError):
        mailbox_profile.snapshot(tmp_path)


def test_future_attempt_blocks(tmp_path):
    with pytest.raises(MailerError):
        mailbox_profile.budget(history(tmp_path, when=NOW + timedelta(seconds=1)), NOW)


def test_profile_must_match_confirmed_sender(tmp_path):
    path = tmp_path / "campaign.json"
    value = {"mail_provider": "gmail", "outbound_transport": "gmail_api", "sender_confirmed": True,
             "sender_email": SENDER, "agent_workdir": str(tmp_path)}
    path.write_text(json.dumps(value))
    assert mailbox_profile.read_profile(path, SENDER)["root"] == tmp_path.resolve()
    value["sender_email"] = "other@gmail.com"
    path.write_text(json.dumps(value))
    with pytest.raises(MailerError):
        mailbox_profile.read_profile(path, SENDER)


def test_mailbox_guard_uses_existing_worker_lock_and_releases(tmp_path, monkeypatch):
    calls = []
    module = SimpleNamespace(RuntimeLockError=RuntimeError, acquire_runtime_lock=lambda root, name, **kw:
                             (calls.append((root, name)) or SimpleNamespace(release=lambda: calls.append("released"))))
    monkeypatch.setitem(sys.modules, "src.runtime_lock", module)
    with mailbox_profile.guard(tmp_path):
        assert calls == [(tmp_path, "otpremaops_campaign")]
    assert calls[-1] == "released"


def shared_bridge(runtime, **changes):
    path, state, bridge = runtime
    shared = {"daily": 0, "hourly": 0, "last_attempt": None, "uncertain": 0, **changes}
    bridge.shared_budget = lambda now: shared
    return bridge


def test_manual_cycle_can_skip_hours_but_not_campaign_or_shared_limits(runtime):
    bridge = shared_bridge(runtime, hourly=8)
    result = run(runtime, now=NOW.replace(hour=2), manual_now=True)
    assert result["status"] == "shared_mailbox_rate_limit" and bridge.mailer.sent == []
    assert runtime[1].deliveries() == []


def test_manual_cycle_sends_without_altering_configured_hours(runtime):
    cfg = config()
    result = run(runtime, cfg=cfg, now=NOW.replace(hour=2), manual_now=True)
    assert result["sent"] == 1 and result["manual_now"] is True
    assert cfg["start_hour"] == 10


def test_shared_unknown_blocks_without_reserving(runtime):
    shared_bridge(runtime, uncertain=1)
    assert run(runtime)["status"] == "shared_mailbox_uncertain_attempt"
    assert runtime[1].deliveries() == []


def test_shared_min_pause_is_preserved(runtime):
    shared_bridge(runtime, last_attempt=(NOW - timedelta(seconds=30)).isoformat())
    assert run(runtime)["status"] == "campaign_min_pause"


def test_already_contacted_company_blocks_other_address(runtime):
    runtime[2].contacted_companies = lambda: {"test workshop"}
    assert run(runtime, leads=[lead(email="alternative@example.rs")])["status"] == "no_approved_recipients"


def test_shared_mailbox_lock_is_held_during_send(runtime):
    bridge = shared_bridge(runtime)
    held = []
    @contextmanager
    def guard():
        held.append(True)
        try:
            yield
        finally:
            held.pop()
    bridge.mailbox_guard = guard
    bridge.mailer.before_send = lambda: held == [True] or pytest.fail("not locked")
    assert run(runtime)["sent"] == 1 and held == []


def test_budget_is_rechecked_after_sent_lookup(runtime):
    bridge = shared_bridge(runtime)
    def lookup(*args):
        bridge.shared_budget = lambda now: {"daily": 25, "hourly": 0, "last_attempt": None, "uncertain": 0}
        return False
    bridge.mailer.has_sent_message = lookup
    assert run(runtime)["status"] == "shared_mailbox_rate_limit"
    assert runtime[1].deliveries() == []
