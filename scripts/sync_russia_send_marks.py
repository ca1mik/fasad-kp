"""Copy verified Russian Gmail send results into the live recipient CSV."""

import csv
import io
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from serbia_outreach import worker_lock
import russia_outreach as ru

FIELDS = ('send_status', 'sent_at_utc', 'gmail_provider_id')


def main():
    with worker_lock(ru.DATA / 'worker.lock'):
        queue = ru.SALES / 'campaign_leads.csv'
        with queue.open(encoding='utf-8-sig', newline='') as source:
            reader = csv.DictReader(source)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        if not rows or len({r['email'].casefold() for r in rows}) != len(rows):
            raise ValueError('Recipient CSV is empty or has duplicate addresses')
        with sqlite3.connect(ru.DATA / 'campaign.sqlite3') as db:
            db.row_factory = sqlite3.Row
            deliveries = {
                r['email'].casefold(): dict(r)
                for r in db.execute('SELECT email, sent_at, status, lead_key FROM deliveries')
            }
            receipts = {
                r['lead_key']: dict(r)
                for r in db.execute('SELECT lead_key, provider_id FROM delivery_receipts')
            }
        counts = {'sent': 0, 'pending': 0, 'unresolved': 0}
        for row in rows:
            delivery = deliveries.get(row['email'].casefold())
            receipt = receipts.get(delivery['lead_key']) if delivery else None
            verification = (ru.DATA / 'sent-verifications' / (receipt['provider_id'] + '.json')) if receipt else None
            if delivery and delivery['status'] == 'committed' and receipt and verification.is_file():
                checked = json.loads(verification.read_text(encoding='utf-8'))
                if checked.get('provider_id') != receipt['provider_id']:
                    raise ValueError('Gmail Sent verification differs from receipt')
                row.update(send_status='sent', sent_at_utc=delivery['sent_at'],
                           gmail_provider_id=receipt['provider_id'])
                counts['sent'] += 1
            elif delivery:
                row.update(send_status='unresolved', sent_at_utc='', gmail_provider_id='')
                counts['unresolved'] += 1
            else:
                row.update(send_status='pending', sent_at_utc='', gmail_provider_id='')
                counts['pending'] += 1
        fields = fieldnames + [f for f in FIELDS if f not in fieldnames]
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        updated = output.getvalue().encode('utf-8-sig')
        if queue.read_bytes() != updated:
            temp = queue.with_suffix('.csv.tmp')
            temp.write_bytes(updated)
            temp.replace(queue)
        print(json.dumps(counts))


if __name__ == '__main__':
    main()
