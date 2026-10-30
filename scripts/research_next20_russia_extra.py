"""Add fresh primary-source reads in an isolated review directory."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
from research_russia_wave2 import get_page

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'data/russia-outreach/next20-russia-2026-09-29'
CANDIDATES=[(101,'Мебельная компания Павлин','https://mkpavlin.ru/'),
            (102,'Фрезер Центр','https://frezercentr.ru/'),
            (103,'ЭКМИ','https://ekmimebel.ru/')]

def check(item):
    number,name,url=item;pages=[]
    first=get_page(url);pages.append(first)
    for contact in first['contact_links']:
        if contact!=first['final_url']:
            try:pages.append(get_page(contact))
            except Exception as exc:pages.append({'url':contact,'error':type(exc).__name__})
    return {'candidate_number':number,'company':name,'website':url,'checked_at':datetime.now(timezone.utc).isoformat(),'pages':pages}

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:records=list(pool.map(check,CANDIDATES))
    (DEST/'fresh-extra-source-checks.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    for rec in records:
        print(json.dumps({'n':rec['candidate_number'],'company':rec['company'],
                          'emails':list(dict.fromkeys(e for p in rec['pages'] if p.get('http_status')==200 for e in p.get('emails',[]))),
                          'phones':list(dict.fromkeys(e for p in rec['pages'] for e in p.get('phones',[])))[:4]},ensure_ascii=False))
