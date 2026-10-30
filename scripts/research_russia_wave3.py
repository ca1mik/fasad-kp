"""Archive public official sources for a new batch; never send or infer consent."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from research_russia_wave2 import get_page

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/russia-outreach/research-wave3-2026-09-29'
CANDIDATES = [
    ('CONCEPT F', 'https://conceptf.ru/'),
    ('АКМ Фасады', 'https://akm22.ru/'),
    ('Орнамент', 'https://fasady-ornament.ru/'),
    ('МДФ КОЛОР', 'https://mdf-color.ru/'),
    ('V&GVIP', 'https://vgvip.ru/'),
    ('Мебель Прикамья', 'https://mebel-prikamya.ru/contact'),
    ('Ладос-Мебель', 'https://www.lados-m.ru/kontaktyi'),
    ('Триумф', 'https://triumph-mf.ru/'),
    ('Ника Фасад', 'https://nikafasad.ru/'),
    ('Sprego', 'https://sprego.ru/'),
    ('GRANDE GLOSS', 'https://grande-gloss.ru/'),
    ('СКИФ', 'https://skif18.ru/'),
    ('ПРЕМЬЕР', 'https://premier-mb.ru/contacts/'),
    ('Prem’era', 'https://ekbfasad.ru/'),
    ('Фиера', 'https://factory.fiera.ru/'),
    ('Фасадель', 'https://facadel.ru/'),
    ('Арбор Нова', 'https://arbor-nova.ru/1.php'),
    ('IREN', 'https://iren-fasad.ru/'),
    ('Аккера', 'https://akkera.pro/'),
    ('Темколь', 'https://temkol.ru/contact/'),
    ('Авалон', 'https://avalon124.ru/'),
    ('Петропрофиль', 'https://www.petroprofil.ru/production'),
    ('Мебель Energy', 'https://mebel-energy.ru/fasady'),
    ('Квазар', 'https://kvazar.ltd/kontakty/'),
    ('Макро', 'https://makro.ru/'),
    ('Томские мебельные фасады', 'https://tmf70.ru/'),
    ('E-KONA', 'https://e-kona.ru/fasady.html'),
    ('ЛАД', 'https://ladmebel.ru/'),
]


def check(item):
    number, (company, url) = item
    pages = []
    try:
        first = get_page(url)
        pages.append(first)
        for contact in first['contact_links']:
            if contact == first['final_url']:
                continue
            try:
                pages.append(get_page(contact))
            except Exception as exc:
                pages.append({'url': contact, 'error': type(exc).__name__})
    except Exception as exc:
        pages.append({'url': url, 'error': type(exc).__name__})
    for i, page in enumerate(pages, 1):
        (DEST / f'{number:02d}-{i}.txt').write_text(page.get('text', page.get('error', '')), encoding='utf-8')
    return {'candidate_number': number, 'company': company, 'website': url,
            'checked_at': datetime.now(timezone.utc).isoformat(), 'pages': pages}


if __name__ == '__main__':
    DEST.mkdir(parents=True, exist_ok=True)
    items = list(enumerate(CANDIDATES, 1))
    results = []
    if '--extra' in sys.argv:
        results = json.loads((DEST / 'source-checks.json').read_text(encoding='utf-8'))
        existing = {row['candidate_number'] for row in results}
        items = [item for item in items if item[0] not in existing]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results += list(pool.map(check, items))
    (DEST / 'source-checks.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for row in results:
        print(json.dumps({'number': row['candidate_number'], 'company': row['company'],
                          'emails': sorted({e for p in row['pages'] for e in p.get('emails', [])}),
                          'phones': sorted({e for p in row['pages'] for e in p.get('phones', [])})[:4],
                          'statuses': [p.get('http_status', p.get('error')) for p in row['pages']]}, ensure_ascii=True))
