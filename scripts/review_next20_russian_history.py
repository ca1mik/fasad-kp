"""Read-only Gmail and file review of the exact twenty pending Russian companies."""
import csv
from datetime import datetime,timezone
from email.parser import BytesParser
from email.policy import default
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import russia_outreach as ru
from shared_gmail_control import atomic_json,read_control,read_sent

WAVE=ru.DATA/'research-wave3-2026-09-29'

def csv_rows(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))

def main():
    cfg=ru.read_config();queue=ru.read_leads()
    new=csv_rows(ru.SALES/'new-researched-prospects-wave3.csv')
    before=csv_rows(WAVE/'queue-before-wave3.csv')
    assert len(queue)==54 and len(new)==20 and queue[:34]==before
    assert len({r['email'] for r in queue})==54
    old_hosts={urlparse(r['website']).hostname.removeprefix('www.') for r in before}
    sources=json.loads((WAVE/'source-checks.json').read_text(encoding='utf-8'))
    pdf=(ru.SALES/'proposal.pdf').read_bytes();digest=hashlib.sha256(pdf).hexdigest()
    assert digest==cfg['proposal_sha256']
    checks=[]
    for row in new:
        assert row==next(r for r in queue if r['email']==row['email'])
        assert row['approved']=='false' and not any(row[k] for k in ['consent_at','consent_scope','consent_evidence'])
        assert urlparse(row['website']).hostname.removeprefix('www.') not in old_hosts
        source=next(r for r in sources if r['website']==row['website'])
        good=[p for p in source['pages'] if p.get('http_status')==200 and row['email'] in {e.casefold() for e in p.get('emails',[])}]
        assert good, 'No verified official business email for '+row['email']
        assert row['city'] and row['phone'] and row['direction'] and row['fit_reason'] and row['verified_at']
        digits=re.sub(r'\D','',' '.join(p.get('text','') for p in source['pages'] if p.get('http_status')==200))
        phone=re.sub(r'\D','',row['phone'])
        assert len(phone)>=10 and phone[-10:] in digits, 'Phone needs source review: '+row['email']
        name=f"{int(row['number']):02d}.eml"
        msg=BytesParser(policy=default).parsebytes((WAVE/'drafts'/name).read_bytes())
        attachments=list(msg.iter_attachments())
        assert msg['To']==row['email'] and not msg['Cc'] and not msg['Bcc']
        assert len(attachments)==1 and attachments[0].get_payload(decode=True)==pdf
        body=msg.get_body(('plain',)).get_content()
        assert row['opening_ru'] in body and row['benefit_ru'] in body
        assert 'localhost' not in body and '127.0.0.1' not in body and '{DEMO_URL}' not in body
        checks.append({'email':row['email'],'official_email_verified':True,'official_phone_verified':True,'real_pdf_verified':True})
    state=ru.RussiaState(ru.DATA/'campaign.sqlite3')
    assert len(state.deliveries())==34 and all(r['status']=='committed' for r in state.deliveries())
    bridge=ru.make_bridge(cfg)
    with bridge.mailbox_guard(ru.CAMPAIGN):
        ready,held,excluded=ru.screen(new,cfg,state,bridge,datetime.now(timezone.utc))
        assert not ready and len(held)==20 and not excluded
        imap=bridge.mailer._open_imap()
        try:
            cache=read_sent(imap,datetime.now(timezone.utc))
            history=[ru.recipient_sent_history(bridge,row,selected_sent=imap) for row in new]
        finally:bridge.mailer._close_imap(imap)
        assert not any(r['matching_offer'] for r in history), 'Previous offer found; do not send again'
        atomic_json(read_control()['sent_cache'],cache)
        atomic_json(WAVE/'gmail-company-history-review.json',history)
    result={'reviewed_at':datetime.now(timezone.utc).isoformat(),'new_companies':20,'previous_records_preserved':34,
            'total_companies':54,'gmail_accepted_previous_batch':34,'new_send_attempts':0,
            'pending_contact_confirmation':20,'excluded_by_history_or_stops':0,
            'previous_matching_gmail_offers':sum(r['matching_offer'] for r in history),
            'any_previous_gmail_correspondence':sum(bool(r['sent_matches_found']) for r in history),
            'individual_pdf_attachments_checked':20,'proposal_sha256':digest,'checks':checks}
    atomic_json(WAVE/'independent-review.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))

if __name__=='__main__':main()
