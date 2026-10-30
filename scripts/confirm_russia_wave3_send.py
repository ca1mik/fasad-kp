"""Record the owner's current instruction for the 20 unsent Russian leads."""

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from serbia_outreach import worker_lock
import russia_outreach as ru


def main():
    with worker_lock(ru.DATA / 'worker.lock'):
        cfg = ru.read_config()
        queue = ru.SALES / 'campaign_leads.csv'
        original = queue.read_bytes()
        rows = ru.read_leads()
        if len(rows) != 54 or [int(r['number']) for r in rows] != list(range(1, 55)):
            raise ValueError('Expected the reviewed 54-row Russian queue')
        pending = rows[34:]
        if any(r['approved'] != 'false' or r['do_not_contact'] != 'false' for r in pending):
            raise ValueError('The 20 new leads have changed; review before recording approval')
        now = datetime.now(timezone.utc)
        evidence = ru.SALES / 'owner-confirmation-wave3-2026-10-01.md'
        if evidence.exists():
            raise ValueError('Owner instruction is already recorded')
        lines = [
            '# Fasad Flow — поручение отправить КП по текущей российской базе',
            '',
            f'Зарегистрировано: {now.isoformat()}. Это время регистрации поручения, а не дата согласия получателей.',
            '',
            'Владелец написал: «разошли кп всем из базы моей которая была тобою создана вчера - отправляй и отмечай отправленные».',
            '',
            'Текущая российская база содержит 54 адресата. Для первых 34 в журнале уже есть завершённые отправки. '
            'Поручение разрешает отправить первое PDF-КП Fasad Flow оставшимся 20 адресатам ниже и отмечать фактически отправленные письма.',
            '',
            'Это разрешение владельца на обращение, а не независимо подтверждённое согласие получателей. '
            'Отписки, стоп-листы, история отправок, проверка Gmail Sent и лимиты продолжают действовать.',
            '',
            f'Область в конфигурации: {cfg["consent_scope"]}',
            f'SHA-256 очереди до регистрации: {hashlib.sha256(original).hexdigest()}',
            '',
            '| № | Компания | Email |',
            '|---|---|---|',
        ]
        lines.extend(f"| {r['number']} | {r['company']} | {r['email']} |" for r in pending)
        evidence.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        backup = ru.DATA / 'queue-before-owner-wave3-send-2026-10-01.csv'
        backup.write_bytes(original)
        for row in pending:
            row.update(approved='true', consent_at=now.isoformat(),
                       consent_evidence=str(evidence), consent_scope=cfg['consent_scope'])
            if ru.consent_problem(row, cfg, now):
                raise ValueError('Owner instruction failed recipient validation: ' + row['email'])
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        temp = queue.with_suffix('.csv.tmp')
        temp.write_text(output.getvalue(), encoding='utf-8-sig', newline='')
        temp.replace(queue)
        result = {
            'registered_at': now.isoformat(),
            'owner_authorized_remaining': len(pending),
            'recipient_consent_independently_verified': False,
            'evidence': str(evidence),
            'queue_sha256_before': hashlib.sha256(original).hexdigest(),
            'send_attempts_created_by_registration': 0,
        }
        (ru.DATA / 'owner-confirmation-wave3-2026-10-01.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
