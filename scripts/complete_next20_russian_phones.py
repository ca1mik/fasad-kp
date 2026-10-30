"""Complete three official landline numbers missed by the generic phone extractor."""
import csv
import io
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import russia_outreach as ru
from serbia_outreach import worker_lock
from shared_gmail_control import atomic_json

WAVE=ru.DATA/'research-wave3-2026-09-29'
PHONES={'fasad@temkol.ru':'+7 (391) 219-02-57, доб. 323',
        'fasad@tomskfasad.ru':'+7 (3822) 25-52-02',
        'lad-mebel@mail.ru':'+7 (4812) 31-28-58'}

def main():
    sources=json.loads((WAVE/'source-checks.json').read_text(encoding='utf-8'))
    with worker_lock(ru.DATA/'worker.lock'):
        for path in [ru.SALES/'campaign_leads.csv',ru.SALES/'new-researched-prospects-wave3.csv',WAVE/'companies.csv']:
            with path.open(encoding='utf-8-sig',newline='') as stream:
                reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
            for row in rows:
                phone=PHONES.get(row['email'])
                if not phone:continue
                source=next(r for r in sources if r['website']==row['website'])
                digits=re.sub(r'\D','',' '.join(p.get('text','') for p in source['pages'] if p.get('http_status')==200))
                assert re.sub(r'\D','',phone)[-10:] in digits
                row['phone']=phone
            buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=fields)
            writer.writeheader();writer.writerows(rows)
            temp=path.with_suffix('.csv.tmp');temp.write_text(buffer.getvalue(),encoding='utf-8-sig',newline='');temp.replace(path)
        atomic_json(WAVE/'official-phone-completions.json',{'phones':PHONES,'basis':'Official contact-page text; four-digit area codes and a local number were not parsed by the generic extractor'})
        print(json.dumps({'official_landlines_completed':3,'previous34_records_changed':False,'send_attempts':0}))

if __name__=='__main__':main()
