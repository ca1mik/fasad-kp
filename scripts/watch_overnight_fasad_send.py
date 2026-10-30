"""Synchronize the overnight workbook while the existing Russia task sends."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/russia-outreach'
OUT = DATA / 'overnight-fasad-file-2026-10-01'
LOG = OUT / 'monitor.json'


def snapshot():
    with sqlite3.connect(DATA / 'campaign.sqlite3', timeout=10) as db:
        statuses = dict(db.execute('SELECT status,COUNT(*) FROM deliveries GROUP BY status'))
        receipts = db.execute('SELECT COUNT(*) FROM delivery_receipts').fetchone()[0]
    return {'committed': statuses.get('committed', 0),
            'unresolved': sum(v for k, v in statuses.items() if k != 'committed'),
            'receipts': receipts}


def sync():
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/sync_overnight_xlsx_marks.py')],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    if result.returncode:
        return None, result.stderr[-300:]
    return json.loads(result.stdout), ''


def main():
    deadline = time.monotonic() + 36 * 60 * 60
    result = {'status': 'monitoring'}
    while time.monotonic() < deadline:
        snap = snapshot()
        marks, error = sync()
        result = {'checked_at': datetime.now(timezone.utc).isoformat(), **snap,
                  'marks': marks, 'sync_error': error, 'status': 'monitoring'}
        if (DATA / 'STOP').exists():
            result['status'] = 'campaign_stopped'
        elif marks and marks['pending'] == 0 and marks['unresolved'] == 0:
            result['status'] = 'complete'
        LOG.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        if result['status'] != 'monitoring':
            break
        time.sleep(30)
    else:
        result['status'] = 'monitor_timeout'
        result['checked_at'] = datetime.now(timezone.utc).isoformat()
        LOG.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
