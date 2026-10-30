"""Register the owner's explicit instruction for the exact current Russian list."""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from serbia_outreach import worker_lock
import russia_outreach as ru

def main():
    with worker_lock(ru.DATA/'worker.lock'):
        cfg=ru.read_config();rows=ru.read_leads()
        if len(rows)!=34:raise ValueError('The reviewed Russian list must contain 34 recipients')
        now=datetime.now(timezone.utc)
        evidence=ru.SALES/'owner-confirmation-all34-2026-09-29.md'
        if evidence.exists():
            print(json.dumps({'already_registered':True,'evidence':str(evidence)}));return
        queue=ru.SALES/'campaign_leads.csv'
        before=queue.read_bytes()
        lines=['# Fasad Flow — подтверждение владельца по текущему российскому списку', '',
               f'Зарегистрировано: {now.isoformat()}.', '',
               'После отчёта о 34 российских компаниях (14 исходных и 20 новых), готовом КП на русском языке и персональных письмах владелец написал:', '',
               '> ТАК ОТПРАВЬ ИМ ПИСЬМА', '',
               'Сообщение трактуется как явное поручение отправить первое КП и предложение демонстрации Fasad Flow всем 34 конкретным адресам из текущего российского списка, приведённым ниже. Это основание — подтверждение владельца именно этого списка, разрешённое исходным поручением. Оно не является утверждением о независимо проверенных согласиях самих получателей.', '',
               'Подключение Gmail и подпись остаются прежними. Согласование не отменяет отписки, стоп-листы, историю предыдущих кампаний, проверку исходящих Gmail, лимиты и обязательную фиксацию попытки до POST. Неопределённые результаты не повторяются автоматически.', '',
               'Публичной HTTPS-ссылки на демо пока нет. Требование о публичном демо этим сообщением явно не изменено; отдельно задан вопрос о размещении либо отправке PDF с приглашением на показ без ссылки. Регистрация подтверждения не является отправкой.', '',
               f'Область в конфигурации: {cfg["consent_scope"]}', '',
               f'SHA-256 очереди до регистрации: {hashlib.sha256(before).hexdigest()}', '',
               '| № | Компания | Email |', '|---|---|---|']
        lines += [f"| {r['number']} | {r['company']} | {r['email']} |" for r in rows]
        evidence.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        (ru.DATA/'queue-before-owner-all34-confirmation.csv').write_bytes(before)
        for row in rows:
            row.update(approved='true',consent_at=now.isoformat(),consent_evidence=str(evidence),consent_scope=cfg['consent_scope'])
            assert not ru.consent_problem(row,cfg,now)
        buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
        temp=queue.with_suffix('.csv.tmp');temp.write_text(buffer.getvalue(),encoding='utf-8-sig',newline='');temp.replace(queue)
        result={'registered_at':now.isoformat(),'owner_confirmed_recipients':34,'permission_basis':'explicit_owner_confirmation_of_current_exact_list',
                'recipient_consent_independently_verified':False,'evidence':str(evidence),'demo_requirement_changed':False,
                'send_attempts_created_by_registration':0}
        (ru.DATA/'owner-confirmation-all34.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
