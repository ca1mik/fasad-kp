"""Research official sites for a new Russian batch. No consent inference or mail."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from urllib.parse import urljoin,urlparse
import requests

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'data/russia-outreach/research-wave2-2026-09-29'
CANDIDATES=[
 ('2 Фасада','https://2fasada.ru/'),('Prem’era','https://ekbfasad.ru/'),
 ('Фасады32','https://fasady32.ru/'),('МДФ КОЛОР','https://mdf-color.ru/'),
 ('Aras Mebeli','https://arasmebeli.ru/'),('МУРАШОВМЕБЕЛЬ','https://murashovfasad.ru/'),
 ('ДСП Комплект','https://dspkomplekt.ru/proizvodstvo_mdf_fasad.html'),
 ('Первая Фабрика Фасадов','https://fabfas.ru/'),('Альфа Фасад','https://alfafacade.ru/'),
 ('Мебель Фасад Про','https://mebel-fasad-pro.ru/'),('Мебельная мастерская MPV','https://www.mm-mpv.ru/'),
 ('Фиеста-Color','https://fiesta-color.ru/'),('Сидак-СП','https://sidak.ru/'),
 ('КАРАТ','https://fasadkarat.com/'),('Дар труда','https://www.dartruda.ru/zakaz'),
 ('ДЕКОВУД','https://dekowoods.ru/kontakty/'),('Мебельная фабрика 11','https://11letopita.ru/'),
 ('БРИГИТТА МЕБЕЛЬ','https://fasad-brig.ru/'),('Фабрика мебельных фасадов 174','https://fasad174.ru/'),
 ('Фабрика Фасадов','https://f-fasad.ru/'),('Сибирские фасады','https://www.siberianfasad.ru/'),
 ('BORA fasad','https://borafasad.ru/'),
]

def get_page(url):
    r=requests.get(url,timeout=(5,15));r.encoding=r.apparent_encoding
    raw=r.text
    clean=re.sub(r'<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>','',raw,flags=re.S|re.I)
    text=html.unescape(re.sub('<[^>]+>',' ',clean));text=re.sub(r'\s+',' ',text)
    emails=sorted(set(re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',html.unescape(raw))))
    phones=sorted(set(re.findall(r'(?:\+7|8)[\s(-]*\d{3}\)?[\s-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}',text)))
    links=[]
    for target in re.findall(r'href\s*=\s*[\"\x27]([^\"\x27]+)',raw,re.I):
        full=urljoin(r.url,target)
        if urlparse(full).hostname!=urlparse(r.url).hostname or re.search(r'\.(?:pdf|jpg|png|zip)',full,re.I):continue
        if re.search(r'(?:contact|kontakty|kontakt|kontact)',urlparse(full).path,re.I) and full not in links:links.append(full)
    return {'url':url,'final_url':r.url,'http_status':r.status_code,'emails':emails,'phones':phones,'text':text,'contact_links':links[:2]}

def check(item):
    number,(company,url)=item;pages=[]
    try:
        first=get_page(url);pages.append(first)
        for contact in first['contact_links']:
            if contact==first['final_url']:continue
            try:pages.append(get_page(contact))
            except Exception as exc:pages.append({'url':contact,'error':type(exc).__name__})
    except Exception as exc:pages.append({'url':url,'error':type(exc).__name__})
    for i,p in enumerate(pages,1):
        (DEST/f'{number:02d}-{i}.txt').write_text(p.get('text',p.get('error','')),encoding='utf-8')
    return {'candidate_number':number,'company':company,'website':url,
            'checked_at':datetime.now(timezone.utc).isoformat(),'pages':pages}

if __name__=='__main__':
    DEST.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(check,enumerate(CANDIDATES,1)))
    (DEST/'source-checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in results:
        texts=' '.join(p.get('text','') for p in r['pages'])
        places=re.findall(r'.{0,35}(?:Казань|Екатеринбург|Москва|Новосибирск|Армавир|Санкт-Петербург|Брянск|Пермь|Челябинск|Нижний Новгород|Самара|Чебоксары|Сиверск|Киров|Йошкар|Ижевск|Тверь|Пенза|Лыткарино|Ростов).{0,85}',texts,re.I)
        print(json.dumps({'number':r['candidate_number'],'company':r['company'],
                         'emails':list(dict.fromkeys(e for p in r['pages'] for e in p.get('emails',[]))),
                         'phones':list(dict.fromkeys(e for p in r['pages'] for e in p.get('phones',[])))[:5],
                         'places':list(dict.fromkeys(places))[:4],
                         'urls':[p['url'] for p in r['pages']]},ensure_ascii=False))
