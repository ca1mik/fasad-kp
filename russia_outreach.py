"""Separate Russian Fasad Flow campaign, using the existing Open Claw Gmail profile."""
from __future__ import annotations
import argparse
import base64
from contextlib import ExitStack
import csv
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from email.policy import default
from email.utils import make_msgid, format_datetime
import hashlib
import html
import ipaddress
import json
from pathlib import Path
import re
import socket
import sys
from urllib.parse import urljoin, urlparse
import requests

from config import validate_public_demo_url
from gmail_https import oauth_module
from openclaw_mail import OpenClawBridge
from serbia_outreach import CampaignState, worker_lock, sync_replies
from shared_gmail_control import CONTROL, SharedControlError, account, atomic_json, db_records, read_control, read_sent
from scripts.build_russia_materials import message_for, mime_for

ROOT=Path(__file__).resolve().parent
SALES=ROOT/'sales/russia'
DATA=ROOT/'data/russia-outreach'
CAMPAIGN='fasad-flow-russia-v1'
EMAIL=re.compile(r'^[^\s@<>]+@[^\s@<>]+\.[A-Za-z]{2,}$')
RU_OPTOUT=re.compile(r'(?im)^\s*(?:отписка|unsubscribe|stop|стоп)\s*[.!]?\s*$|не\s+(?:пишите|присылайте|отправляйте|беспокойте)|удалите\s+(?:меня|адрес)|отпишите|отписаться|do\s+not\s+(?:contact|send)|remove\s+me')

class RussiaError(RuntimeError): pass

def read_config():
    cfg=json.loads((SALES/'campaign.json').read_text(encoding='utf-8'))
    if cfg['campaign_id']!=CAMPAIGN or cfg['expected_sender']!='koallalenivaa@gmail.com' or cfg['outbound_transport']!='gmail_https':
        raise RussiaError('Russian campaign identity or transport changed')
    if not (type(cfg['enabled']) is bool and cfg['sender_name']=='Калдин Лев'):
        raise RussiaError('Russian campaign configuration invalid')
    if any(type(cfg[k]) is not int or not 1<=cfg[k]<=100 for k in ['daily_limit','hourly_limit']) or cfg['min_pause_seconds']<90 or cfg['max_per_run']!=1:
        raise RussiaError('Russian campaign limits invalid')
    return cfg

def read_leads():
    with (SALES/'campaign_leads.csv').open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    seen=set()
    for r in rows:
        if None in r or any(v is None for v in r.values()):raise RussiaError('Malformed Russian queue')
        r['email']=r['email'].strip().casefold()
        if r['email'] in seen:raise RussiaError('Duplicate Russian recipient')
        seen.add(r['email'])
        if any(c in r['company']+r['email'] for c in '\r\n'):raise RussiaError('Invalid message header')
    return rows

def consent_problem(lead,cfg,now):
    if lead['approved']!='true':return 'missing_russian_contact_confirmation'
    if lead['consent_scope']!=cfg['consent_scope']:return 'wrong_consent_scope'
    try:
        stamp=datetime.fromisoformat(lead['consent_at'])
        if stamp.tzinfo is None or stamp>now:return 'invalid_consent_time'
        evidence=Path(lead['consent_evidence'])
        if not evidence.is_absolute() or not evidence.is_file():return 'missing_consent_evidence'
        text=evidence.read_text(encoding='utf-8').casefold()
        if lead['email'] not in text or 'fasad flow' not in text:return 'evidence_does_not_cover_recipient'
    except (ValueError,OSError):return 'missing_consent_evidence'
    return ''

def demo_requirement(cfg):
    """Public-link mode is the default; a meeting-only offer needs owner evidence."""
    mode=cfg.get('demo_delivery','public_url')
    if mode=='public_url':
        if not cfg['demo_url']:return 'public_demo_hosting_not_selected'
        if not cfg['demo_verified_at']:return 'public_demo_not_verified'
        return ''
    if mode!='meeting':return 'invalid_demo_delivery_mode'
    if cfg['demo_url']:return 'meeting_demo_must_not_advertise_public_url'
    try:
        evidence=Path(cfg.get('demo_delivery_approval_evidence',''))
        if not evidence.is_absolute() or not evidence.is_file():return 'meeting_demo_owner_confirmation_missing'
        raw=evidence.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=cfg.get('demo_delivery_approval_sha256'):
            return 'meeting_demo_owner_confirmation_changed'
        text=raw.decode('utf-8')
        if 'delivery_mode=pdf_and_meeting_demo' not in text or 'Fasad Flow' not in text:
            return 'meeting_demo_owner_confirmation_invalid'
    except (ValueError,OSError,UnicodeError):return 'meeting_demo_owner_confirmation_missing'
    return ''

def make_bridge(cfg):
    bridge=OpenClawBridge(Path(cfg['openclaw_root']),cfg['expected_sender'],cfg['sender_name'],
                         '', 'gmail_https',DATA,cfg['mailbox_profile'])
    bridge.apply_mailbox_limits(100,100)
    bridge.mailer.timeout=max(bridge.mailer.timeout,45)
    return bridge

def shared_stops():
    p=Path(read_control()['suppression_path'])
    if not p.exists():return set(),set(),set()
    value=json.loads(p.read_text(encoding='utf-8'))
    if any(not isinstance(value.get(k),list) for k in ['emails','domains','companies']):raise RussiaError('Shared stop list invalid')
    return tuple(set(value[k]) for k in ['emails','domains','companies'])

def screen(leads,cfg,state,bridge,now):
    emails,domains=bridge.suppression()
    stop_emails,stop_domains,stop_companies=shared_stops()
    emails|=stop_emails|state.suppressed();domains|=stop_domains
    companies=bridge.contacted_companies()|stop_companies
    rows=[]
    for path in read_control()['journals']:rows.extend(db_records(path))
    for r in rows:
        # Never automatically reuse a company after any journaled attempt.
        emails.add(r['email'].casefold());companies.add(r['company'].casefold())
    ready=[];held=[];excluded=[]
    for lead in leads:
        host=(urlparse(lead['website']).hostname or '').removeprefix('www.').casefold()
        reason=''
        if state.contains('russia:'+lead['email']):reason='already_attempted_in_russia'
        elif lead['do_not_contact']!='false' or lead['email'] in emails or lead['email'].split('@')[-1] in domains or host in domains:
            reason='shared_stop_or_previous_attempt'
        elif lead['company'].casefold() in companies:reason='company_already_contacted_or_stopped'
        elif lead.get('crm_first_email_at') or lead.get('crm_message_id'):reason='previous_crm_contact'
        elif not EMAIL.fullmatch(lead['email']) or lead['email_verified']!='true':reason='email_unverified'
        if reason:excluded.append({'company':lead['company'],'email':lead['email'],'reason':reason});continue
        reason=consent_problem(lead,cfg,now)
        if reason:held.append({'company':lead['company'],'email':lead['email'],'reason':reason})
        else:ready.append(lead)
    return ready,held,excluded

class RussiaState(CampaignState):
    def reserve_message(self,lead,message_id,now):
        with self._db() as db:
            cur=db.execute("INSERT OR IGNORE INTO deliveries(lead_key,company,email,reserved_at,message_id,status) VALUES(?,?,?,?,?,'reserved')",
                           ('russia:'+lead['email'],lead['company'],lead['email'],now.isoformat(),message_id))
            return bool(cur.rowcount)

    def record_reply(self,message,delivery):
        fresh=re.split(r'(?im)^\s*(?:>|On .+wrote:|From:|От:|-----Original|Во вложении)',message.body,maxsplit=1)[0]
        category='opt_out' if RU_OPTOUT.search(fresh) else 'human_reply'
        with self._db() as db:
            cur=db.execute('INSERT OR IGNORE INTO replies(reply_id,email,at,category,subject,body) VALUES(?,?,?,?,?,?)',
                           (message.message_id or 'imap:'+message.id,delivery['email'],message.received_at.isoformat(),category,message.subject,message.body[:20000]))
            if category=='opt_out':
                db.execute('INSERT OR REPLACE INTO suppression(email,reason,at) VALUES(?,?,?)',
                           (delivery['email'],'recipient_opt_out',message.received_at.isoformat()))
        if category=='opt_out':
            publish_stop(delivery)
        return bool(cur.rowcount)

def publish_stop(delivery):
    cfg=read_control();p=Path(cfg['suppression_path'])
    value=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'emails':[],'domains':[],'companies':[],'events':[]}
    lead=next((x for x in read_leads() if x['email']==delivery['email']),None)
    for k,v in [('emails',delivery['email'].casefold()),('companies',delivery['company'].casefold()),
                ('domains',(urlparse(lead['website']).hostname or '').removeprefix('www.') if lead else '')]:
        if v and v not in value[k]:value[k].append(v)
    if not any(x['email']==delivery['email'] for x in value['events']):
        value['events'].append({'email':delivery['email'],'campaign':CAMPAIGN,'at':datetime.now(timezone.utc).isoformat(),'reason':'recipient_opt_out'})
    atomic_json(p,value)

def public_host(url):
    validate_public_demo_url(url)
    parsed=urlparse(url)
    if parsed.port not in {None,443}:raise RussiaError('Demo requires standard public HTTPS')
    for info in socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(info[4][0]).is_global:raise RussiaError('Demo host resolves to an internal address')

def public_get(url):
    for _ in range(4):
        public_host(url)
        r=requests.get(url,timeout=(5,15),allow_redirects=False)
        if r.status_code in {301,302,303,307,308}:url=urljoin(url,r.headers['Location']);continue
        if r.status_code!=200:raise RussiaError('Public demo is unavailable or requires authentication')
        return r
    raise RussiaError('Too many demo redirects')

def verify_demo(url):
    first=public_get(url)
    manifest=json.loads((SALES/'demo-public/manifest.json').read_text(encoding='utf-8'))
    checks={}
    for filename in ['index.html','app.js','production_flow.js','styles.css']:
        response=first if filename=='index.html' else public_get(urljoin(first.url,filename))
        digest=hashlib.sha256(response.content).hexdigest()
        if digest!=manifest[filename]:raise RussiaError('Public demo differs from reviewed test-data build: '+filename)
        checks[filename]=digest
    return {'url':first.url,'checked_at':datetime.now(timezone.utc).isoformat(),'assets_sha256':checks,'public_https':True,'authentication_required':False}

def pdf_preflight(cfg):
    pdf=SALES/'proposal.pdf'
    if not pdf.is_file() or hashlib.sha256(pdf.read_bytes()).hexdigest()!=cfg['proposal_sha256']:raise RussiaError('Proposal PDF changed; review and rebuild previews')
    import pymupdf
    with pymupdf.open(pdf) as doc:
        text=''.join(p.get_text() for p in doc)
        if not doc.page_count or 'Калдин Лев' not in text or 'Fasad Flow' not in text or '{DEMO_URL}' in text:raise RussiaError('Proposal PDF verification failed')

def sent_matches(bridge,lead):
    # Reuse the existing read-only Sent lookup with exact subject, then inspect the recent account snapshot.
    subject,_=message_for(lead,read_config())
    if bridge.mailer.has_sent_message(lead['email'],subject):return True
    cache=json.loads(Path(read_control()['sent_cache']).read_text(encoding='utf-8'))
    if any(lead['email'] in r['emails'] and 'fasad' in r['subject'].casefold() for r in cache['records']):return True
    return bool(recipient_sent_history(bridge,lead)['matching_offer'])

def recipient_sent_history(bridge,lead,*,selected_sent=None):
    """Check all-time Sent. A batch may lend its already selected read-only Sent connection."""
    owns_imap=selected_sent is None
    imap=bridge.mailer._open_imap() if owns_imap else selected_sent
    try:
        if owns_imap:read_sent(imap,datetime.now(timezone.utc))
        host=(urlparse(lead['website']).hostname or '').removeprefix('www.')
        status,values=imap.uid('search',None,'OR','TO','"'+lead['email']+'"','TO','"@'+host+'"')
        if status!='OK':raise RussiaError('Cannot reconcile company history in Gmail Sent')
        ids=(values[0] if values else b'').split()
        if len(ids)>200:raise RussiaError('Company Sent history needs manual review')
        found=[]
        for uid in ids:
            status,parts=imap.uid('fetch',uid,'(X-GM-MSGID BODY.PEEK[])')
            raw=next((p[1] for p in parts or [] if isinstance(p,tuple)),None)
            if status!='OK' or not raw:raise RussiaError('Cannot inspect company Gmail Sent history')
            msg=BytesParser(policy=default).parsebytes(raw)
            bodies=[]
            for part in msg.walk():
                if part.get_content_type() in {'text/plain','text/html'} and part.get_content_disposition()!='attachment':
                    bodies.append(part.get_content())
            text=(str(msg.get('Subject',''))+'\n'+'\n'.join(bodies)).casefold()
            matches=('fasad flow' in text or 'fasad-flow' in text or ('crm' in text and 'фасад' in text))
            found.append({'to':str(msg.get('To','')),'subject':str(msg.get('Subject','')),
                          'message_id':str(msg.get('Message-ID','')),'matching_offer':matches})
        return {'company':lead['company'],'email':lead['email'],'checked_at':datetime.now(timezone.utc).isoformat(),
                'sent_matches_found':len(found),'matching_offer':any(r['matching_offer'] for r in found),'messages':found}
    finally:
        if owns_imap:bridge.mailer._close_imap(imap)

def inspect_accepted_mime(bridge,provider_id,pdf_bytes):
    """Verify the real Gmail Sent copy and retain Gmail's rewritten RFC ID."""
    imap=bridge.mailer._open_imap()
    try:
        read_sent(imap,datetime.now(timezone.utc)) # Selects Sent read-only.
        status,values=imap.uid('search',None,'X-GM-MSGID',str(int(provider_id,16)))
        ids=(values[0] if values else b'').split()
        if status!='OK' or len(ids)!=1:raise RussiaError('Accepted Gmail message not yet reconciled in Sent')
        status,parts=imap.uid('fetch',ids[0],'(BODY.PEEK[])')
        raw=next((p[1] for p in parts or [] if isinstance(p,tuple)),None)
        if status!='OK' or not raw:raise RussiaError('Cannot inspect accepted Gmail MIME')
        message=BytesParser(policy=default).parsebytes(raw)
        attachments=list(message.iter_attachments())
        if len(attachments)!=1 or attachments[0].get_payload(decode=True)!=pdf_bytes:
            raise RussiaError('Accepted Gmail attachment does not match reviewed PDF')
        if not message.get('Message-ID'):raise RussiaError('Accepted Gmail canonical Message-ID missing')
        return {'provider_id':provider_id,'canonical_message_id':str(message['Message-ID']),
                'pdf_sha256':hashlib.sha256(pdf_bytes).hexdigest(),'pdf_bytes':len(pdf_bytes),
                'checked_at':datetime.now(timezone.utc).isoformat()}
    finally:bridge.mailer._close_imap(imap)

def send_mime(bridge,msg):
    attachments=list(msg.iter_attachments())
    if len(attachments)!=1 or attachments[0].get_content_type()!='application/pdf' or attachments[0].get_payload(decode=True)!=(SALES/'proposal.pdf').read_bytes():
        raise RussiaError('Real PDF attachment verification failed')
    if msg.get('Cc') or msg.get('Bcc') or len(msg.get_all('To',[]))!=1:raise RussiaError('One recipient per message is required')
    client=bridge.mailer._client()
    try:
        # Single send POST; do not retry a timeout, redirect, 5xx or malformed receipt.
        response=client.session.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
                                    headers={'Authorization':'Bearer '+client.payload['access_token']},
                                    json={'raw':base64.urlsafe_b64encode(msg.as_bytes()).decode('ascii')},
                                    timeout=(5,12),allow_redirects=False)
        if response.status_code!=200:raise RussiaError('Gmail acceptance not confirmed; reconcile Sent')
        value=response.json()
        if not isinstance(value.get('id'),str) or not value['id']:raise RussiaError('Gmail provider ID missing; reconcile Sent')
        return value
    finally:client.quit()

def write_status(state,result,bridge=None):
    cfg=read_config();leads=read_leads();now=datetime.now(timezone.utc)
    deliveries=state.deliveries()
    receipts=[]
    with state._db() as db:receipts=[dict(r) for r in db.execute('SELECT * FROM delivery_receipts')]
    accepted=len(receipts)
    if bridge:
        ready,held,excluded=screen(leads,cfg,state,bridge,now)
    else:
        ready=[];held=[];excluded=[]
        for lead in leads:
            if state.contains('russia:'+lead['email']):continue
            reason=consent_problem(lead,cfg,now)
            if reason:held.append({'company':lead['company'],'email':lead['email'],'reason':reason})
    out=result|{'campaign_id':CAMPAIGN,'checked_at':now.isoformat(),'gmail_accepted':accepted,'attempts':len(deliveries),
                'remaining_in_queue':len(leads)-len(deliveries)-len([r for r in excluded if r['reason']!='already_attempted_in_russia']),
                'ready':len(ready),'awaiting_contact_confirmation':len(held),
                'excluded':len([r for r in excluded if r['reason']!='already_attempted_in_russia']),
                'uncertain':sum(r['status'] in {'reserved','uncertain'} for r in deliveries),
                'unresolved':sum(r['status']!='committed' for r in deliveries),
                'errors':int(result.get('errors',0)),
                'held_recipients':held,'excluded_recipients':excluded,'provider_receipts':receipts,
                'demo_public_verified':bool(cfg['demo_url'] and cfg['demo_verified_at']),
                'demo_delivery':cfg.get('demo_delivery','public_url'),
                'paths':{'queue':str(SALES/'campaign_leads.csv'),'journal':str(state.path),'events':str(DATA/'events.jsonl'),
                         'status':str(DATA/'status.json'),'previews':str(DATA/'previews/index.html')},
                'task_name':cfg['task_name']}
    atomic_json(DATA/'status.json',out)
    with (DATA/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(out,ensure_ascii=False)+'\n')
    return out

def cycle(state,*,send=False,verify_mail=False):
    cfg=read_config();result={'status':'checking','new_gmail_accepted':0,'errors':0}
    bridge=None
    with ExitStack() as locks:
        locks.enter_context(worker_lock(DATA/'worker.lock'))
        bridge=make_bridge(cfg);locks.enter_context(bridge.mailbox_guard(CAMPAIGN))
        bridge.mailer.healthcheck()
        now=datetime.now(timezone.utc)
        imap=bridge.mailer._open_imap()
        try:sent=read_sent(imap,now)
        finally:bridge.mailer._close_imap(imap)
        atomic_json(read_control()['sent_cache'],sent)
        result['mailbox_verified']=True
        prior=state.deliveries()
        reply_since=(min(datetime.fromisoformat(row['reserved_at']) for row in prior)-timedelta(days=1)).date() if prior else None
        result['new_replies']=sync_replies(state,bridge,since=reply_since,header_first=True)
        result['mailbox']=bridge.summary()
        budget=account(datetime.now(timezone.utc))
        result['shared_account']={k:v for k,v in budget.items() if k!='records'}
        blockers=[]
        if not cfg['enabled']:blockers.append('campaign_disabled')
        if (DATA/'STOP').exists():blockers.append('russian_campaign_stopped')
        if any(r['status']!='committed' for r in state.deliveries()):blockers.append('unresolved_russian_attempt')
        ready,held,excluded=screen(read_leads(),cfg,state,bridge,datetime.now(timezone.utc))
        if not ready and not held and not blockers:
            # The queue is exhausted. Continue reply synchronization without a new offer.
            return write_status(state,result|{'status':'queue_completed','blockers':[]},bridge)
        if not ready:blockers.append('no_confirmed_russian_recipients')
        demo_problem=demo_requirement(cfg)
        if demo_problem:blockers.append(demo_problem)
        if budget['reason']:blockers.append(budget['reason'])
        result['blockers']=blockers
        if blockers:return write_status(state,result|{'status':'waiting_for_missing_prerequisites'},bridge)
        if not send:return write_status(state,result|{'status':'ready_no_send'},bridge)
        pdf_preflight(cfg)
        if cfg.get('demo_delivery','public_url')=='public_url':
            demo_check=verify_demo(cfg['demo_url']);atomic_json(DATA/'demo-https-check.json',demo_check)
        lead=ready[0]
        if sent_matches(bridge,lead):
            state.suppress_existing(lead['email'],datetime.now(timezone.utc))
            return write_status(state,result|{'status':'duplicate_in_gmail_sent_excluded'},bridge)
        now=datetime.now(timezone.utc)
        lead=next((x for x in read_leads() if x['email']==lead['email']),None)
        if lead is None or not screen([lead],cfg,state,bridge,now)[0]:
            return write_status(state,result|{'status':'recipient_no_longer_eligible'},bridge)
        # Reconcile Sent and all journals again after material/network checks, under the shared lock.
        imap=bridge.mailer._open_imap()
        try:sent=read_sent(imap,datetime.now(timezone.utc))
        finally:bridge.mailer._close_imap(imap)
        atomic_json(read_control()['sent_cache'],sent)
        now=datetime.now(timezone.utc);budget=account(now)
        if budget['reason']:return write_status(state,result|{'status':budget['reason']},bridge)
        current_cfg=read_config()
        if demo_requirement(current_cfg) or current_cfg.get('demo_delivery','public_url')!=cfg.get('demo_delivery','public_url'):
            return write_status(state,result|{'status':'demo_delivery_approval_changed'},bridge)
        if (DATA/'STOP').exists() or Path(read_control()['stop_path']).exists():raise RussiaError('Stop was set before sending')
        message_id=make_msgid(domain='gmail.com')
        msg=mime_for(lead,cfg,message_id);msg['Date']=format_datetime(now)
        msg['List-Unsubscribe']='<mailto:koallalenivaa@gmail.com?subject=Unsubscribe%20Fasad%20Flow>'
        msg['X-Auto-Response-Suppress']='All'
        message_dir=DATA/'attempted-messages';message_dir.mkdir(exist_ok=True)
        (message_dir/(lead['number']+'.eml')).write_bytes(msg.as_bytes())
        if not state.reserve_message(lead,message_id,now):raise RussiaError('Recipient already reserved')
        # Reservation is committed before the only send POST.
        key='russia:'+lead['email']
        try:
            receipt=send_mime(bridge,msg)
            with state._db() as db:
                db.execute('INSERT INTO delivery_receipts(lead_key,transport,provider_id,thread_id) VALUES(?,?,?,?)',
                           (key,'gmail_https',receipt['id'],receipt.get('threadId','')))
            state.mark_sent(key,message_id,datetime.now(timezone.utc))
            sent_check=inspect_accepted_mime(bridge,receipt['id'],(SALES/'proposal.pdf').read_bytes())
            atomic_json(DATA/'sent-verifications'/(receipt['id']+'.json'),sent_check)
            if not (DATA/'first-real-send-verification.json').exists():
                atomic_json(DATA/'first-real-send-verification.json',sent_check)
            with state._db() as db:
                db.execute('UPDATE deliveries SET message_id=? WHERE lead_key=?',(sent_check['canonical_message_id'],key))
            state.mark_committed(key)
            result.update(status='gmail_api_accepted',new_gmail_accepted=1,email=lead['email'],provider_id=receipt['id'],message_id=message_id)
        except Exception as exc:
            if 'receipt' not in locals():
                state.mark_uncertain(key,type(exc).__name__+'; reconcile Gmail Sent, no automatic POST retry')
            (DATA/'STOP').write_text('Uncertain Russian send. Reconcile Gmail Sent before resuming.\n',encoding='utf-8')
            Path(read_control()['stop_path']).write_text('Uncertain Gmail send in '+CAMPAIGN+'; reconcile Sent.\n',encoding='utf-8')
            result.update(status='accepted_pending_sent_reconciliation' if 'receipt' in locals() else 'uncertain_stopped',
                          errors=1,email=lead['email'],error=type(exc).__name__)
        return write_status(state,result,bridge)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['check','cycle','status','verify-demo'])
    parser.add_argument('--url');parser.add_argument('--scheduled',action='store_true')
    args=parser.parse_args();DATA.mkdir(parents=True,exist_ok=True)
    state=RussiaState(DATA/'campaign.sqlite3')
    try:
        if args.command=='verify-demo':
            if not args.url:raise RussiaError('A user-approved public HTTPS URL is required')
            check=verify_demo(args.url);cfg=read_config();cfg.update(demo_url=check['url'],demo_verified_at=check['checked_at'])
            atomic_json(SALES/'campaign.json',cfg);atomic_json(DATA/'demo-https-check.json',check)
            from scripts.build_russia_materials import build
            build();out=check
        elif args.command=='status':out=json.loads((DATA/'status.json').read_text(encoding='utf-8'))
        else:out=cycle(state,send=args.command=='cycle')
        if sys.stdout is not None:print(json.dumps(out,ensure_ascii=False,indent=2))
        return 0
    except Exception as exc:
        busy='Another Open Claw mailbox worker' in str(exc) or 'Another Serbian campaign worker' in str(exc)
        out=write_status(state,{'status':'shared_worker_busy' if busy else 'error_no_automatic_retry',
                               'errors':0 if busy else 1,'error_type':type(exc).__name__,'error':str(exc)[:250]})
        if sys.stdout is not None:print(json.dumps(out,ensure_ascii=False,indent=2))
        return 0 if busy else 1

if __name__=='__main__':raise SystemExit(main())
