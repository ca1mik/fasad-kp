"""Keep recipient marks current while the existing Russia task sends its queue."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/russia-outreach'
PYTHON = Path(sys.executable)
LOG = DATA / 'wave3-send-monitor.json'


def snapshot():
    with sqlite3.connect(DATA / 'campaign.sqlite3', timeout=10) as db:
        rows = dict(db.execute('SELECT status, COUNT(*) FROM deliveries GROUP BY status'))
        receipts = db.execute('SELECT COUNT(*) FROM delivery_receipts').fetchone()[0]
    return {'committed': rows.get('committed', 0), 'unresolved': sum(v for k, v in rows.items() if k != 'committed'),
            'receipts': receipts}


def sync_marks():
    result = subprocess.run([str(PYTHON), str(ROOT / 'scripts/sync_russia_send_marks.py')],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode:
        return {'error': result.stderr[-300:]}
    return json.loads(result.stdout)


def restore_serbia():
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-Command',
         "Enable-ScheduledTask -TaskName 'Fasad Flow Serbia Outreach' | Out-Null; "
         "Start-ScheduledTask -TaskName 'Fasad Flow Serbia Outreach'"],
        capture_output=True, text=True, timeout=30,
    )
    return {'ok': result.returncode == 0, 'error': result.stderr[-300:]}


def main():
    last = None
    deadline = time.monotonic() + 4 * 60 * 60
    result = {'status': 'monitoring'}
    try:
        while time.monotonic() < deadline:
            snap = snapshot()
            if snap != last or result.get('marks', {}).get('sent') != snap['committed']:
                marks = sync_marks()
                result = {'checked_at': datetime.now(timezone.utc).isoformat(), **snap, 'marks': marks,
                          'status': 'monitoring'}
                LOG.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                last = snap
            if (DATA / 'STOP').exists():
                result['status'] = 'campaign_stopped'
                break
            if snap['committed'] == 54 and snap['receipts'] == 54 and result.get('marks', {}).get('sent') == 54:
                result['status'] = 'complete'
                break
            time.sleep(20)
        else:
            result['status'] = 'monitor_timeout'
    finally:
        result['serbia_task_restored'] = restore_serbia()
        result['checked_at'] = datetime.now(timezone.utc).isoformat()
        LOG.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
