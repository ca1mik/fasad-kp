"""Read official sites for the existing Russian CRM; never send messages."""
import concurrent.futures
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/russia-outreach'

def check(item):
    number, row = item
    company, email, site = row[0], row[3], row[5]
    urls = list(dict.fromkeys([row[6], site]))
    pages = []
    for url in urls:
        try:
            response = requests.get(url, timeout=(5, 18))
            response.encoding = response.apparent_encoding
            raw = response.text
            text = re.sub(r'<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>', '', raw, flags=re.S|re.I)
            text = html.unescape(re.sub('<[^>]+>', ' ', text))
            text = re.sub(r'\s+', ' ', text)
            mails = sorted(set(re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', html.unescape(raw))))
            phones = sorted(set(re.findall(r'(?:\+7|8)\s*[(-]?\d{3}\)?[\s-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}', text)))
            pages.append({'url':url,'final_url':response.url,'http_status':response.status_code,
                          'emails':mails,'phones':phones,'text':text[:50000]})
            (DATA/'sources'/f'{number:02d}-{len(pages)}.txt').write_text(text, encoding='utf-8')
        except Exception as exc:
            pages.append({'url':url,'error':type(exc).__name__})
    return {'number':number,'company':company,'crm_email':email,'checked_at':datetime.now(timezone.utc).isoformat(),
            'email_found':any(email.casefold() in [x.casefold() for x in p.get('emails',[])] for p in pages),
            'pages':pages}

if __name__ == '__main__':
    (DATA/'sources').mkdir(parents=True,exist_ok=True)
    rows=json.loads((DATA/'crm-source-2026-09-29.json').read_text(encoding='utf-8'))['values'][1:]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results=sorted(pool.map(check,enumerate(rows,1)),key=lambda x:x['number'])
    (DATA/'source-checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in results:
        print(json.dumps({k:v for k,v in r.items() if k!='pages'}|{'emails':[p.get('emails',[]) for p in r['pages']], 'phones':[p.get('phones',[])[:4] for p in r['pages']]},ensure_ascii=False))
