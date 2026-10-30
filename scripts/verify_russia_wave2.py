"""Verify the expanded batch and produce a review page for its twenty letters."""
import csv
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
import hashlib
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SALES=ROOT/'sales/russia'
DATA=ROOT/'data/russia-outreach'
WAVE=DATA/'research-wave2-2026-09-29'

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))

before=rows(WAVE/'queue-before-wave2.csv')
queue=rows(SALES/'campaign_leads.csv')
new=rows(SALES/'new-researched-prospects.csv')
by_email={r['email']:r for r in queue}
assert len(queue)==34 and len(new)==20 and len(before)==14
assert len(by_email)==34
assert all(by_email[r['email']]==r for r in before), 'Original CRM row or consent changed'
assert not {r['email'] for r in before}&{r['email'] for r in new}
pdf=(SALES/'proposal.pdf').read_bytes()
assert pdf.startswith(b'%PDF-')
cfg=json.loads((SALES/'campaign.json').read_text(encoding='utf-8'))
assert hashlib.sha256(pdf).hexdigest()==cfg['proposal_sha256']
page=['<!doctype html><html lang="ru"><meta charset="utf-8"><title>Ещё 20 писем · Fasad Flow</title>',
      '<style>body{font:16px/1.5 Arial;max-width:1000px;margin:40px auto}article{border-top:1px solid #ccd;padding:20px 0}pre{white-space:pre-wrap}a{color:#176653}</style>',
      '<h1>Ещё 20 персональных писем · Fasad Flow</h1><p>Подготовленные локальные материалы. Согласия не установлены; отправок этой партии нет. EML содержит настоящий PDF. После выбора публичного HTTPS-демо письма будут обновлены проверенной ссылкой.</p>']
verified=[]
for row in queue:
    name=f"{int(row['number']):02d}"
    message=BytesParser(policy=default).parsebytes((DATA/'previews'/f'{name}.eml').read_bytes())
    assert message['To']==row['email'] and not message['Bcc'] and not message['Cc']
    attachments=list(message.iter_attachments())
    assert len(attachments)==1 and attachments[0].get_payload(decode=True)==pdf
    body=message.get_body(('plain',)).get_content()
    assert row['opening_ru'] in body and row['benefit_ru'] in body
    assert 'localhost' not in body and '{DEMO_URL}' not in body
    if row in new:
        assert row['approved']=='false' and not row['consent_at'] and not row['consent_evidence']
        page.append(f"<article><h2>{name}. {html.escape(row['company'])}</h2><p>{html.escape(row['city'])} · {html.escape(row['email'])}</p><pre>{html.escape(body)}</pre><a href='../previews/{name}.eml'>EML с PDF</a> · <a href='../previews/{name}.txt'>Текст</a> · <a href='{html.escape(row['source_url'])}'>Официальный источник</a></article>")
    verified.append({'number':row['number'],'email':row['email'],'real_pdf_attached':True})
page.append('</html>')
(WAVE/'letters.html').write_text('\n'.join(page),encoding='utf-8')
result={'checked_at':datetime.now(timezone.utc).isoformat(),'original_crm_rows_preserved':14,
        'new_companies':20,'queue_size':34,'individual_pdf_attachments_checked':len(verified),
        'new_approvals_inferred':0,'duplicate_emails':0,'proposal_sha256':cfg['proposal_sha256'],
        'checks':verified}
(WAVE/'batch-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
