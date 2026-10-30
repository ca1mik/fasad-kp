from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
from types import SimpleNamespace

import pytest

from mailer import MailerError
from openclaw_mail import OpenClawBridge
import serbia_outreach as campaign
from scripts import send_fasad_wave2 as batch
from tests.test_serbia_outreach import config, lead, committed, runtime, run, NOW
from tests.test_shared_mailbox import shared_bridge


@dataclass(frozen=True)
class Limits:
    daily_limit: int = 25
    hourly_limit: int = 8
    min_pause_seconds: int = 90
    draft_only: bool = True


def test_mailbox_override_is_account_scoped_immutable_and_keeps_pause():
    bridge = OpenClawBridge.__new__(OpenClawBridge)
    bridge.profile_root = Path('H:/serbiya/outreach')
    original = bridge.settings = Limits()
    bridge.mailer = SimpleNamespace(address='koallalenivaa@gmail.com',
                                   identity=SimpleNamespace(label='shared_openclaw_gmail'), settings=original)
    bridge.apply_mailbox_limits(100, 100)
    assert original == Limits() and bridge.settings.daily_limit == bridge.settings.hourly_limit == 100
    assert bridge.settings.min_pause_seconds == 90 and bridge.settings.draft_only is True
    assert bridge.mailer.settings is bridge.settings
    assert bridge.inherited_limits == {'daily_limit': 25, 'hourly_limit': 8}


@pytest.mark.parametrize('daily,hourly', [(101, 100), (100, 0), (True, 100)])
def test_mailbox_override_rejects_unapproved_bounds(daily, hourly):
    bridge = OpenClawBridge.__new__(OpenClawBridge)
    bridge.profile_root = Path('H:/serbiya/outreach')
    bridge.settings = Limits()
    bridge.mailer = SimpleNamespace(address='koallalenivaa@gmail.com',
                                   identity=SimpleNamespace(label='shared_openclaw_gmail'))
    with pytest.raises(MailerError):
        bridge.apply_mailbox_limits(daily, hourly)
    assert bridge.settings == Limits()


def test_limit100_accounts_for_other_campaign_without_erasing_attempts(runtime):
    bridge = shared_bridge(runtime, daily=27, hourly=20)
    bridge.settings.daily_limit = bridge.settings.hourly_limit = 100
    for i in range(2):
        committed(runtime[1], lead(f'old{i}@example.rs'), NOW - timedelta(hours=3))
    result = run(runtime, cfg=config(daily_limit=100, hourly_limit=100), manual_now=True)
    assert result['sent'] == 1 and len(runtime[1].deliveries()) == 3
    assert result['other_campaign_attempts']['daily'] == 27


def test_limit100_still_blocks_the_actual_shared_ceiling(runtime):
    bridge = shared_bridge(runtime, daily=100)
    bridge.settings.daily_limit = bridge.settings.hourly_limit = 100
    result = run(runtime, cfg=config(daily_limit=100, hourly_limit=100), manual_now=True)
    assert result['status'] == 'shared_mailbox_rate_limit' and not bridge.mailer.sent
    assert not runtime[1].deliveries()


def researched():
    return [lead(f'buyer{i}@example.rs', company=f'Workshop {i}') for i in range(20)]


def test_wave_selects_only_twenty_confirmed_targets_and_rejects_changed_company():
    source = researched()
    assert batch.select_wave(source + [lead('outsider@example.rs')], source) == source
    with pytest.raises(campaign.CampaignError):
        batch.select_wave(source, source[:19])
    changed = [{**row} for row in source]
    changed[0]['company'] = 'An unrelated company'
    with pytest.raises(campaign.CampaignError):
        batch.select_wave(changed, source)


def setup_worker(runtime, monkeypatch):
    folder, state, bridge = runtime
    source = researched()
    monkeypatch.setattr(batch, 'BATCH', folder / 'batch')
    monkeypatch.setattr(campaign, 'DATA', folder)
    monkeypatch.setattr(campaign, 'read_leads', lambda path=None: source if path == batch.SOURCE else source + [lead('outsider@example.rs')])
    cfg = dict(enabled=True, allow_live_on_draft_mailbox=True, daily_limit=100, hourly_limit=100,
               max_per_run=1, timezone='Europe/Belgrade', start_hour=10, end_hour=17,
               sender_name='Test Seller', seller_name='Test Studio', seller_address='', demo_url='',
               openclaw_root='E:/open-claw-agent', mailbox='koallalenivaa@gmail.com',
               expected_sender='koallalenivaa@gmail.com')
    monkeypatch.setattr(campaign, 'read_config', lambda: cfg)
    monkeypatch.setattr(campaign, 'CampaignState', lambda path: state)
    monkeypatch.setattr(campaign, 'configured_bridge', lambda cfg: bridge)
    bridge.mailer.outbound_transport = 'gmail_https'
    return source


def test_wave_once_uses_durable_cycle_and_never_sends_old_outsider(runtime, monkeypatch):
    source = setup_worker(runtime, monkeypatch)
    assert batch.run(once=True) == 0
    assert runtime[2].mailer.sent[0][0] == source[0]['email']
    assert runtime[1].deliveries()[0]['status'] == 'committed'
    assert (batch.BATCH / 'status.json').exists() and (batch.BATCH / 'events.jsonl').exists()


def test_wave_once_respects_pause_without_a_new_reservation(runtime, monkeypatch):
    source = setup_worker(runtime, monkeypatch)
    committed(runtime[1], source[0], datetime.now(timezone.utc) - timedelta(seconds=30))
    assert batch.run(once=True) == 0
    assert not runtime[2].mailer.sent and len(runtime[1].deliveries()) == 1


def test_completed_wave_exits_without_opening_mail(runtime, monkeypatch):
    source = setup_worker(runtime, monkeypatch)
    for row in source:
        committed(runtime[1], row, NOW)
    monkeypatch.setattr(campaign, 'configured_bridge', lambda cfg: pytest.fail('Completed batch opened mail'))
    assert batch.run() == 0


def test_wave_stop_flag_prevents_send(runtime, monkeypatch):
    setup_worker(runtime, monkeypatch)
    (runtime[0] / 'STOP').write_text('operator stopped', encoding='utf-8')
    assert batch.run() == 2 and not runtime[2].mailer.sent


def test_scheduled_worker_can_persist_results_without_a_console(runtime, monkeypatch):
    setup_worker(runtime, monkeypatch)
    monkeypatch.setattr(batch.sys, 'stdout', None)
    assert batch.run(once=True) == 0
    status = json.loads((batch.BATCH / 'status.json').read_text(encoding='utf-8'))
    assert status['accepted'] == 1 and status['status'] == 'gmail_api_accepted'


def test_task_is_disabled_only_after_complete_and_with_owned_action_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, 'BATCH', tmp_path)
    calls = []
    monkeypatch.setattr(batch.subprocess, 'run', lambda *args, **kwargs: calls.append((args, kwargs)))
    (tmp_path / 'status.json').write_text(json.dumps({'status': 'waiting_min_pause'}), encoding='utf-8')
    batch.disable_completed_task()
    assert not calls
    (tmp_path / 'status.json').write_text(json.dumps({'status': 'complete'}), encoding='utf-8')
    batch.disable_completed_task()
    command = calls[0][0][0][-1]
    assert batch.TASK_NAME in command and 'Actions.Arguments -like' in command
    assert str(Path(batch.__file__).resolve()) in command and calls[0][1]['capture_output'] is True
