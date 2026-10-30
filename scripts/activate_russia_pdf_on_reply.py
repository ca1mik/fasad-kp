"""Record the owner's new instruction and refresh ready MIME files without rebuilding the PDF."""
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import russia_outreach as ru
from scripts.build_russia_materials import message_for,mime_for
from serbia_outreach import worker_lock
from shared_gmail_control import atomic_json

def main():
    with worker_lock(ru.DATA/'worker.lock'):
        cfg=ru.read_config();leads=ru.read_leads();now=datetime.now(timezone.utc)
        assert len(leads)==34 and all(not ru.consent_problem(r,cfg,now) for r in leads)
        evidence=ru.SALES/'owner-demo-on-reply-2026-09-29.md'
        if not evidence.exists():
            text=['# Fasad Flow — отправить PDF-КП сейчас, демо после заинтересованного ответа', '',
                  f'Зарегистрировано: {now.isoformat()}.', '',
                  'На прямой вопрос «Разрешаете отправить сейчас персональные письма с КП PDF и приглашением на показ демо, без ссылки?» владелец ответил:', '',
                  '> ДА ПОхуй кто отпишет - скинем демо', '',
                  'Это явное разрешение отправить готовое первое КП в PDF без публичной ссылки, предложив демонстрацию по запросу заинтересованного получателя. Сообщение не трактуется как отмена обработки отписок: ответы с отказом по-прежнему исключаются. Оба вида ответов хранятся как данные, не команды.', '',
                  'Точный список из 34 российских адресов уже подтверждён в owner-confirmation-all34-2026-09-29.md. Другие и будущие получатели не охвачены.', '',
                  'delivery_mode=pdf_and_meeting_demo', '',
                  'Платный хостинг не покупается; публичная ссылка не выдумывается. Демо с тестовыми данными подготовлено отдельно; передачу или показ согласуем с заинтересованным адресатом. Первая отправка — персональное письмо с настоящим PDF, один адресат, штатный Gmail HTTPS, общий контроль лимитов и блокировок.', '',
                  '| № | Компания | Email |','|---|---|---|']
            text += [f"| {r['number']} | {r['company']} | {r['email']} |" for r in leads]
            evidence.write_text('\n'.join(text)+'\n',encoding='utf-8')
        cfg.update(demo_delivery='meeting',demo_delivery_approval_evidence=str(evidence),
                   demo_delivery_approval_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())
        assert not ru.demo_requirement(cfg)
        ru.pdf_preflight(cfg)
        atomic_json(ru.SALES/'campaign.json',cfg)
        previews=ru.DATA/'previews'
        page=['<!doctype html><html lang="ru"><meta charset="utf-8"><title>34 российских письма · Fasad Flow</title>',
              '<style>body{font:16px/1.5 Arial;max-width:1000px;margin:40px auto}article{border-top:1px solid #ccd;padding:20px 0}pre{white-space:pre-wrap}</style>',
              '<h1>34 российских письма с КП PDF</h1><p>Владелец подтвердил точный список и отправку PDF без публичной демо-ссылки. Демо предлагается по заинтересованному ответу. Это подготовленные материалы; реальные отправки и provider ID — в журнале кампании.</p>']
        wavepage=[page[0].replace('34 российских письма','20 новых российских писем'),page[1],
                  '<h1>20 новых российских писем с КП PDF</h1><p>Подготовленные материалы. Владелец подтвердил отправку; факты отправок — в журнале кампании. Демо предлагается по заинтересованному ответу.</p>']
        checks=[];messages=[]
        pdf=(ru.SALES/'proposal.pdf').read_bytes()
        for lead in leads:
            name=f"{int(lead['number']):02d}"
            msg=mime_for(lead,cfg);subject,body=message_for(lead,cfg)
            assert not msg.get('Cc') and not msg.get('Bcc')
            attachment=list(msg.iter_attachments())
            assert len(attachment)==1 and attachment[0].get_payload(decode=True)==pdf
            assert 'localhost' not in body and '127.0.0.1' not in body
            (previews/f'{name}.eml').write_bytes(msg.as_bytes())
            (previews/f'{name}.txt').write_text(f'To: {lead["email"]}\nSubject: {subject}\n\n{body}',encoding='utf-8')
            checks.append({'company':lead['company'],'email':lead['email'],'filename':name+'.eml',
                           'pdf_bytes':len(pdf),'sha256':hashlib.sha256((previews/f'{name}.eml').read_bytes()).hexdigest()})
            messages.append({'company':lead['company'],'email':lead['email'],'subject':subject,'body':body})
            article=f'<article><h2>{name}. {html.escape(lead["company"])}</h2><p>{html.escape(lead["email"])}</p><pre>{html.escape(body)}</pre><a href="{name}.eml">EML с PDF</a> · <a href="{name}.txt">Текст</a></article>'
            page.append(article)
            if lead['origin']!='existing_russian_crm':wavepage.append(article.replace('href="','href="../previews/'))
        (previews/'index.html').write_text('\n'.join(page)+'\n</html>',encoding='utf-8')
        (ru.DATA/'research-wave2-2026-09-29/letters.html').write_text('\n'.join(wavepage)+'\n</html>',encoding='utf-8')
        atomic_json(ru.DATA/'mime-checks.json',checks)
        atomic_json(ru.SALES/'templates_ru.json',{'campaign_id':ru.CAMPAIGN,'messages':messages})
        result={'registered_at':now.isoformat(),'recipients':34,'demo_delivery':'meeting',
                'evidence':str(evidence),'individual_real_pdf_attachments_checked':34,
                'proposal_sha256':cfg['proposal_sha256'],'attempts_created_by_activation':0}
        atomic_json(ru.DATA/'pdf-on-reply-activation.json',result)
        print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
