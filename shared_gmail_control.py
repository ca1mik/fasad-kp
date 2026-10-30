"""Mailbox-wide, fail-closed limits. No credentials and no send operations."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from email.policy import default
from email.utils import parsedate_to_datetime, getaddresses
import json
from pathlib import Path
import re
import sqlite3
from zoneinfo import ZoneInfo

CONTROL = Path('E:/open-claw-workdir/mailbox_controls/koallalenivaa@gmail.com.json')

class SharedControlError(RuntimeError): pass

def read_control(path=CONTROL):
    cfg=json.loads(path.read_text(encoding='utf-8'))
    if cfg['sender']!='koallalenivaa@gmail.com' or cfg['daily_limit']!=100 or cfg['hourly_limit']!=100 or cfg['min_pause_seconds']<90:
        raise SharedControlError('Shared Gmail limits or sender changed')
    return cfg

def db_records(path):
    path=Path(path).resolve()
    if not path.is_file(): raise SharedControlError('A registered campaign journal is missing')
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5) as db:
        db.row_factory=sqlite3.Row
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'outbound' in tables:
            rows=[dict(r) for r in db.execute('SELECT company,email,attempted_at AS at,message_id,state FROM outbound')]
            for r in rows:r['accepted']=r['state']=='sent';r['uncertain']=r['state'] in {'sending','unknown'}
        elif 'deliveries' in tables:
            rows=[dict(r) for r in db.execute('SELECT company,email,reserved_at AS at,message_id,status AS state FROM deliveries')]
            for r in rows:r['accepted']=r['state']=='committed';r['uncertain']=r['state']!='committed'
        else: raise SharedControlError('Unknown registered journal schema')
        receipts={}
        if 'delivery_receipts' in tables:
            receipts={r['lead_key']:r['provider_id'] for r in db.execute('SELECT lead_key,provider_id FROM delivery_receipts')}
        for r in rows:
            r['source']=str(path)
            r['provider_id']=next((v for k,v in receipts.items() if k.endswith(':'+r['email'])), '')
        return rows

def read_sent(imap,now):
    status,folders=imap.list()
    if status!='OK':raise SharedControlError('Cannot identify Gmail Sent')
    sent=next((x for x in folders or [] if isinstance(x,bytes) and b'\\Sent' in x),b'')
    match=re.search(rb'\)\s+(?:"[^"]*"|NIL)\s+(.+)$',sent)
    if not match:raise SharedControlError('Cannot identify Gmail Sent')
    status,_=imap.select(match[1].decode('ascii'),readonly=True)
    if status!='OK':raise SharedControlError('Cannot open Gmail Sent read-only')
    # One extra day covers UTC/local-day boundaries; INTERNALDATE is authoritative.
    since=(now-timedelta(days=2)).strftime('%d-%b-%Y')
    status,values=imap.uid('search',None,'SINCE',since)
    if status!='OK':raise SharedControlError('Cannot search Gmail Sent')
    ids=(values[0] if values else b'').split()
    if len(ids)>2000:raise SharedControlError('Sent reconciliation requires manual review')
    records=[]
    if ids:
        status,parts=imap.uid('fetch',b','.join(ids),'(INTERNALDATE X-GM-MSGID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT TO FROM DATE)])')
        if status!='OK':raise SharedControlError('Cannot read Gmail Sent headers')
        for part in parts or []:
            if not isinstance(part,tuple):continue
            meta,raw=part
            stamp=re.search(rb'INTERNALDATE "([^"]+)"',meta)
            provider=re.search(rb'X-GM-MSGID (\d+)',meta)
            if not stamp:raise SharedControlError('Missing Gmail Sent timestamp')
            at=datetime.strptime(stamp[1].decode('ascii'),'%d-%b-%Y %H:%M:%S %z')
            msg=BytesParser(policy=default).parsebytes(raw)
            records.append({'at':at.isoformat(),'message_id':str(msg.get('Message-ID','')),
                            'provider_id':format(int(provider[1]),'x') if provider else '',
                            'subject':str(msg.get('Subject','')),
                            'emails':[a.casefold() for _,a in getaddresses(msg.get_all('To',[]))],
                            'from':str(msg.get('From','')),'accepted':True,'uncertain':False,'source':'gmail_sent'})
    return {'checked_at':now.isoformat(),'records':records}

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

def account(now=None,cfg=None,*,exclude_message_id='',require_fresh=True):
    now=now or datetime.now(timezone.utc);cfg=cfg or read_control()
    if Path(cfg['stop_path']).exists():raise SharedControlError('Shared Gmail STOP requires reconciliation')
    rows=[]
    for path in cfg['journals']:rows.extend(db_records(path))
    cache=Path(cfg['sent_cache'])
    if not cache.exists():raise SharedControlError('Gmail Sent has not been reconciled')
    sent=json.loads(cache.read_text(encoding='utf-8'))
    checked=datetime.fromisoformat(sent['checked_at'])
    if checked.tzinfo is None or checked>now or (require_fresh and (now-checked).total_seconds()>300):
        raise SharedControlError('Gmail Sent snapshot is stale; sending blocked')
    known={r['message_id'] for r in rows if r['message_id']}
    providers={r.get('provider_id') for r in rows if r.get('provider_id')}
    reconciled=[];matched=set()
    # Gmail rewrites the RFC Message-ID. Prefer the true provider ID; legacy
    # journals lacking receipts require a unique recipient/topic/time match.
    for i,r in enumerate(sent['records']):
        if (r['message_id'] and r['message_id'] in known) or (r.get('provider_id') and r['provider_id'] in providers):continue
        candidates=[(j,x) for j,x in enumerate(rows) if j not in matched and x['accepted'] and
                    not x.get('provider_id') and x['email'] in r.get('emails',[]) and
                    '[otpremaops]' in r.get('subject','').casefold() and
                    abs((datetime.fromisoformat(r['at'])-datetime.fromisoformat(x['at'])).total_seconds())<=180]
        if len(candidates)==1:
            j,x=candidates[0]
            alternatives=[s for s in sent['records'] if x['email'] in s.get('emails',[]) and
                          '[otpremaops]' in s.get('subject','').casefold() and
                          abs((datetime.fromisoformat(s['at'])-datetime.fromisoformat(x['at'])).total_seconds())<=180]
            if len(alternatives)==1:
                matched.add(j);reconciled.append({'email':x['email'],'journal_message_id':x['message_id'],
                    'gmail_message_id':r['message_id'],'gmail_provider_id':r.get('provider_id',''),
                    'method':'unique_recipient_topic_time_match','attempt_at':x['at'],'gmail_sent_at':r['at']})
                continue
        rows.append(r|{'company':'','email':','.join(r.get('emails',[]))})
    zone=ZoneInfo(cfg['timezone']);local=now.astimezone(zone)
    stamps=[];daily=hourly=calendar=uncertain=0
    for r in rows:
        if exclude_message_id and r['message_id']==exclude_message_id:continue
        stamp=datetime.fromisoformat(r['at'])
        if stamp.tzinfo is None or stamp>now:raise SharedControlError('Invalid shared attempt timestamp')
        elapsed=(now-stamp).total_seconds();stamps.append(stamp)
        daily+=0<=elapsed<86400
        calendar+=stamp.astimezone(zone).date()==local.date()
        hourly+=0<=elapsed<3600
        uncertain+=r['uncertain']
    daily=max(daily,calendar) # A rolling day is an additional conservative ceiling.
    last=max(stamps) if stamps else None
    reason=('shared_uncertain_attempt' if uncertain else 'shared_daily_limit' if daily>=cfg['daily_limit'] else
            'shared_hourly_limit' if hourly>=cfg['hourly_limit'] else
            'shared_min_pause' if last and (now-last).total_seconds()<cfg['min_pause_seconds'] else '')
    return {'daily':daily,'hourly':hourly,'calendar_daily':calendar,'last_attempt':last.isoformat() if last else None,
            'uncertain':uncertain,'total_attempts':len(stamps),'reason':reason,'records':rows,
            'sent_checked_at':sent['checked_at'],'legacy_sent_reconciliation':reconciled,
            'limits':{'day':100,'hour':100,'min_pause_seconds':90}}

def available_for_native(cfg,now):
    path=Path(cfg['agent_workdir'])/'mailbox_controls'/(cfg.get('sender_email','')+'.json')
    if not path.is_file():return None
    control=read_control(path)
    try:
        result=account(datetime.now(timezone.utc),control)
    except SharedControlError:
        return 0
    return 0 if result['reason'] else min(100-result['daily'],100-result['hourly'],1)

def native_preflight(cfg):
    value=available_for_native(cfg,datetime.now(timezone.utc))
    return value is None or value>0

def other_for_serbia(now):
    result=account(now)
    config=read_control()
    own=db_records(config['fasad_serbia_journal'])
    daily=hourly=0
    for r in own:
        stamp=datetime.fromisoformat(r['at']);elapsed=(now-stamp).total_seconds()
        daily+=0<=elapsed<86400 or stamp.astimezone(ZoneInfo(config['timezone'])).date()==now.astimezone(ZoneInfo(config['timezone'])).date()
        hourly+=0<=elapsed<3600
    return {k:v for k,v in result.items() if k!='records'}|{'daily':max(0,result['daily']-daily),'hourly':max(0,result['hourly']-hourly),
        'total_sent':sum(r['accepted'] for r in result['records'])}
