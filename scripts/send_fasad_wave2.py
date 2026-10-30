"""Send only the owner-approved Fasad Flow wave, using the durable campaign worker."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
import subprocess
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import serbia_outreach as campaign  # noqa: E402
from mailer import MailerError  # noqa: E402

BATCH_ID = "fasad-flow-wave2-20260929"
BATCH = campaign.DATA / BATCH_ID
SOURCE = ROOT / "sales/serbia/new-prospects-2026-09-29.csv"
TASK_NAME = "Fasad Flow Wave2 Immediate"


def select_wave(live: list[dict], researched: list[dict]) -> list[dict]:
    allowed = {row["email"]: row["company"].casefold() for row in researched}
    if len(researched) != 20 or len(allowed) != 20:
        raise campaign.CampaignError("The explicitly approved wave must contain exactly 20 unique addresses")
    result = [row for row in live if row["email"] in allowed]
    if any(row["company"].casefold() != allowed[row["email"]] for row in result):
        raise campaign.CampaignError("A researched recipient's company changed; review required")
    return result


def progress(state, researched: list[dict]) -> dict:
    allowed = {row["email"] for row in researched}
    attempts = [row for row in state.deliveries() if row["email"] in allowed]
    return {"batch_id": BATCH_ID, "total": len(allowed),
            "accepted": sum(row["status"] == "committed" for row in attempts),
            "unresolved": sum(row["status"] != "committed" for row in attempts),
            "not_attempted": len(allowed - {row["email"] for row in attempts})}


def record(value: dict):
    value = {"checked_at": datetime.now(timezone.utc).isoformat(), "worker_pid": os.getpid(), **value}
    payload = json.dumps(value, ensure_ascii=False)
    temporary = BATCH / "status.tmp"
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(payload + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, BATCH / "status.json")
    with (BATCH / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(payload + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(payload, flush=True)


def disable_completed_task():
    """Disable only our own bounded task after all targets are dispositioned."""
    status = json.loads((BATCH / "status.json").read_text(encoding="utf-8"))
    if status["status"] not in {"complete", "complete_with_exclusions"}:
        return
    script_path = str(Path(__file__).resolve()).replace("'", "''")
    command = (f"$batchTask = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue\n"
               f"if ($batchTask -and $batchTask.Actions.Arguments -like '*{script_path}*') {{\n"
               f"Disable-ScheduledTask -TaskName '{TASK_NAME}' | Out-Null\n}}")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                   capture_output=True, timeout=20, check=False,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def run(*, once: bool = False) -> int:
    BATCH.mkdir(parents=True, exist_ok=True)
    researched = campaign.read_leads(SOURCE)
    select_wave(campaign.read_leads(), researched)
    state = campaign.CampaignState(campaign.DATA / "campaign.sqlite3")
    # This batch lock is distinct from the per-cycle mailbox locks. Waiting must
    # not block other campaigns' reply polling or the ordinary scheduled worker.
    with campaign.worker_lock(BATCH / "worker.lock"):
        for _ in range(300):
            cfg = campaign.read_config()
            counts = progress(state, researched)
            if (BATCH / "STOP").exists() or (campaign.DATA / "STOP").exists() or not cfg["enabled"]:
                record({**counts, "status": "stopped"})
                return 2
            if counts["accepted"] == 20:
                record({**counts, "status": "complete"})
                return 0
            bridge = campaign.configured_bridge(cfg)
            now = datetime.now(timezone.utc).astimezone(ZoneInfo(cfg["timezone"]))
            rate, shared = campaign.rate_problem(cfg, state, bridge, now)
            if rate == "campaign_min_pause":
                stamps = [row["reserved_at"] for row in state.deliveries()]
                if shared["last_attempt"]:
                    stamps.append(shared["last_attempt"])
                next_at = max(datetime.fromisoformat(stamp) for stamp in stamps) + timedelta(
                    seconds=bridge.settings.min_pause_seconds)
                seconds = max(1, (next_at - now).total_seconds())
                record({**counts, "status": "waiting_min_pause", "next_check_seconds": min(30, seconds)})
                if once:
                    return 0
                time.sleep(min(30, seconds))
                continue
            if rate:
                record({**counts, "status": "deferred", "reason": rate, "other_campaign_attempts": shared})
                return 2
            loader = lambda: select_wave(campaign.read_leads(), researched)
            record({**counts, "status": "running", "effective_limits": {
                "campaign_daily": cfg["daily_limit"], "campaign_hourly": cfg["hourly_limit"],
                "mailbox_daily": bridge.settings.daily_limit, "mailbox_hourly": bridge.settings.hourly_limit,
                "min_pause_seconds": bridge.settings.min_pause_seconds}})
            try:
                result = campaign.cycle(cfg, loader(), state, campaign.DATA,
                                        leads_loader=loader, manual_now=True)
            except (campaign.CampaignError, MailerError) as exc:
                # Failure to acquire a mailbox lock made no send attempt. Other
                # errors fail closed; none retries a reserved/uncertain message.
                if "worker is running" not in str(exc):
                    raise
                record({**progress(state, researched), "status": "waiting_for_worker"})
                if once:
                    return 0
                time.sleep(30)
                continue
            counts = progress(state, researched)
            record({**counts, "status": result["status"], "cycle": result})
            if counts["accepted"] == 20:
                record({**counts, "status": "complete"})
                return 0
            if result["status"] == "no_approved_recipients":
                record({**counts, "status": "complete_with_exclusions"})
                return 0
            if result["status"] not in {"gmail_api_accepted", "campaign_min_pause", "already_in_gmail_sent",
                                        "recipient_removed_before_send", "recipient_blocked_before_send", "already_reserved"}:
                return 2
            if once:
                return 0
        record({**progress(state, researched), "status": "deferred", "reason": "bounded_worker_iterations"})
        return 2


if __name__ == "__main__":
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run at most one safe cycle, without waiting")
    parser.add_argument("--scheduled", action="store_true", help="Disable the owned batch task on completion")
    args = parser.parse_args()
    try:
        result = run(once=args.once)
        if args.scheduled and result == 0:
            disable_completed_task()
        raise SystemExit(result)
    except Exception as exc:
        safe = str(exc) if isinstance(exc, (campaign.CampaignError, MailerError)) else type(exc).__name__
        busy = isinstance(exc, campaign.CampaignError) and safe == "Another Serbian campaign worker is running"
        error = {"status": "waiting_for_worker" if busy else "error", "error": safe, "sent": 0,
                 "checked_at": datetime.now(timezone.utc).isoformat()}
        if not busy:
            BATCH.mkdir(parents=True, exist_ok=True)
            (BATCH / "last_error.json").write_text(json.dumps(error, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(error, ensure_ascii=False), flush=True)
        raise SystemExit(0 if busy else 1)
