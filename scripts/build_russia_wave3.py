"""Prepare 20 sourced prospects and real PDF drafts without authorizing or sending."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
import hashlib
import html
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_russia_materials import message_for, mime_for
from serbia_outreach import worker_lock
from shared_gmail_control import db_records, read_control

SALES = ROOT / 'sales/russia'
DATA = ROOT / 'data/russia-outreach'
WAVE = DATA / 'research-wave3-2026-09-29'
ORIGIN = 'new_russian_research_wave3_2026_09_29'
OFFICIAL_LOCAL_PHONES = {
    'fasad@temkol.ru': '+7 (391) 219-02-57, доб. 323',
    'fasad@tomskfasad.ru': '+7 (3822) 25-52-02',
    'lad-mebel@mail.ru': '+7 (4812) 31-28-58',
}
SELECTED = [
    (2, 'АКМ Фасады', 'Барнаул', 'Мебельные фасады MDF', 'info@akm22.ru',
     'На сайте АКМ Фасады представлены мебельные фасады MDF и возможность заказа по размерам.'),
    (3, 'Орнамент', 'Самара; Тольятти', 'Фасады MDF, шпона и массива', 'sale-smr@fabrika-ornament.ru',
     'Фабрика Орнамент предлагает мебельному бизнесу фасады из MDF, шпона и массива.'),
    (5, 'V&GVIP', 'Москва; производство — Правдинский', 'Корпусная мебель и изготовление фасадов', 'info@vgvip.ru',
     'На сайте V&GVIP описаны собственное производство корпусной мебели, изготовление и покраска мебельных фасадов.'),
    (6, 'Мебель Прикамья', 'Пермь', 'Корпусная мебель и мебельные комплектующие', 'mp59.01@mail.ru',
     'Мебель Прикамья предлагает корпусную мебель для дома, офиса и торговли и мебельные комплектующие.'),
    (7, 'Ладос-Мебель', 'Москва', 'Мебельные фасады и корпусная мебель', 'alla@lados-m.ru',
     'На сайте Ладос-Мебель представлены мебельные фасады и корпусная мебель; ваш контакт опубликован в оптовом отделе фасадов.'),
    (8, 'Триумф', 'Краснодар', 'Мебельные фасады по размерам', 'triumph-mf@yandex.ru',
     'Триумф предлагает мебельные фасады с изготовлением по параметрам заказчика.'),
    (11, 'GRANDE GLOSS', 'Казань', 'Крашеные и шпонированные фасады; корпусная мебель', 'grande-gloss@mail.ru',
     'GRANDE GLOSS описывает производство крашеных и шпонированных фасадов и корпусной мебели для производителей мебели.'),
    (12, 'СКИФ', 'Ижевск', 'Корпусная мебель, MDF-фасады, распил и ЧПУ', 'info@skif18.ru',
     'Фабрика СКИФ предлагает мебель на заказ, изготовление MDF-фасадов, распиловку и фрезеровку на ЧПУ.'),
    (13, 'ПРЕМЬЕР', 'Екатеринбург', 'Производство мебели и проектные заказы', 'info@premier-mb.ru',
     'На официальном сайте мебельной фабрики ПРЕМЬЕР представлены производство мебели и дизайн-проектирование.'),
    (16, 'Фасадель', 'Воронеж; производство — Подклетное', 'Изготовление и окраска мебельных фасадов', 'facadel-opt@mail.ru',
     'Фасадель описывает изготовление мебельных фасадов по эскизу заказчика и окраску фасадов.'),
    (17, 'Арбор Нова', 'Санкт-Петербург; Ленинградская область', 'Шпонированные и крашеные мебельные фасады', 'zakaz@arbor-nova.ru',
     'Arbor Nova представляет собственное производство шпонированных и крашеных мебельных фасадов.'),
    (18, 'IREN', 'Тюмень; Курган', 'Производство мебельных фасадов MDF в PVC', 'info@iren-fasad.ru',
     'IREN описывает производство мебельных фасадов полного цикла и MDF-фасады в плёнке PVC.'),
    (19, 'Аккера', 'Красноярск', 'Производство фасадов и профессиональная покраска', 'akkera_mdf@mail.ru',
     'Аккера предлагает производство мебельных фасадов по эскизам и профессиональную покраску.'),
    (20, 'Темколь', 'Красноярск', 'Мебельные фасады MDF', 'fasad@temkol.ru',
     'На официальном сайте Темколь представлены мебельные фасады MDF и варианты фрезеровки.'),
    (21, 'Авалон', 'Красноярск', 'Мебельные фасады MDF, PVC и эмаль', 'avalon124@bk.ru',
     'Авалон предлагает мебельные фасады MDF с покрытиями PVC и эмалью.'),
    (22, 'Петропрофиль', 'Санкт-Петербург', 'Производство фасадов и корпусной мебели', 'reception@petroprofil.ru',
     'Петропрофиль описывает производство мебельных фасадов и корпусной мебели в Санкт-Петербурге и Ленинградской области.'),
    (25, 'Макро', 'Санкт-Петербург', 'Алюминиевые мебельные фасады и двери-купе', 'zakaz@makro.ru',
     'Макро описывает изготовление алюминиевых мебельных фасадов со стеклом или пластиком и дверей-купе.'),
    (26, 'Томские мебельные фасады', 'Томск', 'Производство мебельных фасадов и декоративных покрытий', 'fasad@tomskfasad.ru',
     'Томские мебельные фасады представляют мебельные фасады, декоративные покрытия и двери для шкафов.'),
    (27, 'ЭКОНА', 'Смоленск', 'Фасады и корпусная мебель по размерам', 'ekonamebel@gmail.com',
     'ЭКОНА предлагает мебельные фасады по индивидуальным размерам и производство корпусной мебели в Смоленске.'),
    (28, 'ЛАД', 'Смоленск', 'Корпусная мебель и мебель по эскизам', 'lad-mebel@mail.ru',
     'Фабрика ЛАД описывает собственное производство корпусной мебели и изготовление по эскизам и чертежам.'),
]


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def csv_text(fields, rows):
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader(); writer.writerows(rows)
    return buffer.getvalue()


def host(url):
    return (urlparse(url).hostname or '').casefold().removeprefix('www.')


def build():
    sources = {r['candidate_number']: r for r in json.loads((WAVE/'source-checks.json').read_text(encoding='utf-8'))}
    cfg = json.loads((SALES/'campaign.json').read_text(encoding='utf-8'))
    pdf = (SALES/'proposal.pdf').read_bytes()
    digest = hashlib.sha256(pdf).hexdigest()
    assert digest == cfg['proposal_sha256'] and pdf.startswith(b'%PDF-')
    control = read_control()
    history = [r for path in control['journals'] for r in db_records(path)]
    stops = json.loads(Path(control['suppression_path']).read_text(encoding='utf-8'))
    blocked_emails = set(stops['emails']) | {r['email'].casefold() for r in history}
    blocked_companies = set(stops['companies']) | {r['company'].casefold() for r in history}
    checked = datetime.now(timezone.utc).isoformat()
    with worker_lock(DATA/'worker.lock'):
        path = SALES/'campaign_leads.csv'
        original = path.read_bytes()
        fields, old = read_csv(path)
        previous = [r for r in old if r['origin'] != ORIGIN]
        assert len(previous) == 34, 'Queue changed; review concurrent work before appending'
        emails = {r['email'].casefold() for r in previous}
        hosts = {host(r['website']) for r in previous}
        companies = {r['company'].casefold() for r in previous}
        records = []
        for number, (candidate, company, city, direction, email, opening) in enumerate(SELECTED, 35):
            source = sources[candidate]
            live = [p for p in source['pages'] if p.get('http_status') == 200 and email in {e.casefold() for e in p.get('emails', [])}]
            assert live, f'No current official email evidence: {company}'
            site = source['website']; site_host = host(site)
            assert email not in emails | blocked_emails and site_host not in hosts | set(stops['domains'])
            assert company.casefold() not in companies | blocked_companies
            assert email.split('@')[-1] not in stops['domains']
            emails.add(email); hosts.add(site_host); companies.add(company.casefold())
            row = {key: '' for key in fields}
            phones = live[-1].get('phones', [])
            if not phones and email in OFFICIAL_LOCAL_PHONES:
                phone = OFFICIAL_LOCAL_PHONES[email]
                digits = re.sub(r'\D', '', ' '.join(p.get('text', '') for p in source['pages'] if p.get('http_status') == 200))
                assert re.sub(r'\D', '', phone)[-10:] in digits, 'Official phone needs review'
                phones = [phone]
            benefit = 'Предлагаю показать тестовый заказ: спецификацию деталей, расчёт, материалы, очередь цеха, готовность и оплаты. Затем обсудим, какие этапы и поля нужны именно вашему производству.'
            if candidate == 25:
                benefit = 'Предлагаю обсудить спецификацию, очередь сборки, готовность и оплаты одного заказа. Специализированного расчёта алюминиевых систем в прототипе нет; нужные поля и доработки оценим отдельно.'
            if candidate in (5, 6, 12, 13, 27, 28):
                benefit = 'На демо предлагаю пройти один мебельный заказ от заявки и размеров деталей до материалов, этапов производства и оплаты. Требования к вашему планированию и существующему учёту уточним отдельно.'
            row.update(number=str(number), company=company, city=city, direction=direction, email=email,
                       phone=phones[0] if phones else '', website=site, source_url=live[-1]['url'],
                       verified_at=source['checked_at'], email_verified='true', fit_reason=direction+'; предполагаемая применимость к заказам, деталям и этапам производства; потребность не подтверждена',
                       origin=ORIGIN, relationship='new_researched_prospect; no consent or customer evidence',
                       crm_status='Новый', opening_ru=opening, benefit_ru=benefit,
                       approved='false', do_not_contact='false')
            prior = next((r for r in old if r['email'].casefold() == email), None)
            if prior:
                for key in ('approved', 'consent_at', 'consent_evidence', 'consent_scope', 'do_not_contact'):
                    row[key] = prior[key]
            records.append(row)
        assert len(records) == 20
        backup = WAVE/'queue-before-wave3.csv'
        if not backup.exists():backup.write_bytes(original)
        drafts = WAVE/'drafts'; drafts.mkdir(exist_ok=True)
        previews = DATA/'previews'; previews.mkdir(exist_ok=True)
        page = ['<!doctype html><html lang="ru"><meta charset="utf-8"><title>Fasad Flow · ещё 20 компаний</title>',
                '<style>body{max-width:1000px;margin:40px auto;font:16px/1.5 Arial}pre{white-space:pre-wrap}article{border-top:1px solid #ccd;padding:18px 0}a{color:#176653}</style>',
                '<h1>Новая партия: 20 компаний · №35–54</h1><p>Локальные черновики с настоящим PDF-КП. Это не отправленные письма и не Gmail Drafts. Контакты проверены по официальным сайтам; согласия не установлены. Прежнее разрешение 34 адресатов не перенесено.</p>']
        checks = []
        for row in records:
            name = f"{int(row['number']):02d}"
            message = mime_for(row, cfg)
            raw = message.as_bytes()
            parsed = BytesParser(policy=default).parsebytes(raw)
            attachments = list(parsed.iter_attachments())
            assert parsed['To'] == row['email'] and not parsed['Cc'] and not parsed['Bcc']
            assert len(attachments) == 1 and attachments[0].get_payload(decode=True) == pdf
            subject, body = message_for(row, cfg)
            assert row['opening_ru'] in body and row['benefit_ru'] in body
            assert '{DEMO_URL}' not in body and 'localhost' not in body
            for folder in (drafts, previews):
                (folder/f'{name}.eml').write_bytes(raw)
                (folder/f'{name}.txt').write_text('Кому: '+row['email']+'\nТема: '+subject+'\n\n'+body, encoding='utf-8')
            page.append(f"<article><h2>{name}. {html.escape(row['company'])}</h2><p>{html.escape(row['city'])} · {html.escape(row['email'])}</p><pre>{html.escape(body)}</pre><a href='drafts/{name}.eml'>Письмо EML с PDF</a> · <a href='{html.escape(row['source_url'])}'>Официальный источник</a></article>")
            checks.append({'number':int(row['number']), 'email':row['email'], 'pdf_sha256':digest, 'source_url':row['source_url']})
        (WAVE/'letters.html').write_text('\n'.join(page)+'</html>', encoding='utf-8')
        (WAVE/'companies.csv').write_text(csv_text(fields, records), encoding='utf-8-sig', newline='')
        (SALES/'new-researched-prospects-wave3.csv').write_text(csv_text(fields, records), encoding='utf-8-sig', newline='')
        pending = path.with_suffix('.csv.tmp')
        pending.write_text(csv_text(fields, previous+records), encoding='utf-8-sig', newline='')
        pending.replace(path)
        _, after = read_csv(path)
        assert after[:34] == previous and len(after) == 54
        assert hashlib.sha256((SALES/'proposal.pdf').read_bytes()).hexdigest() == digest
        lines = ['# Ещё 20 российских компаний — третья партия Fasad Flow', '',
                 'Официальные сайты проверены 29.09.2026. Адреса №35–54 не входят в уже отправленные 34. Отправлено этой новой партией: 0. Подготовлены 20 персональных EML с тем же проверенным PDF-КП; новые согласия не установлены.', '',
                 '[Просмотр писем](../../data/russia-outreach/research-wave3-2026-09-29/letters.html)', '',
                 '| № | Компания / город | Направление | Деловой email | Официальный источник |',
                 '|---|---|---|---|---|']
        for row in records:
            lines.append(f"| {row['number']} | {row['company']} / {row['city']} | {row['direction']} | {row['email']} | [Контакт]({row['source_url']}) |")
        lines += ['', 'Контакты проверены на отсутствие повторов по email, компаниям и доменам ранее найденных компаний, по общим журналам попыток и общему стоп-листу. Один деловой контакт на компанию. Валидность почтового ящика и интерес к продукту не установлены.', '',
                  'У Макро алюминиевые системы: применимость прототипа ограничена общим учётом заказов; специализированный расчёт не заявлен. У серийных мебельных фабрик требования к производственному планированию следует выяснить до пилота.', '',
                  'Допуск прошлого списка не переносился на будущие адреса: approved=false, consent_at/consent_evidence/consent_scope пусты. Нужны подтверждение владельца по этому точному списку и реальное основание контакта; публичная публикация email не является согласием.', '',
                  'Сохранены PDF/SHA256, конфигурация, первые 34 записи и их история, отказы и ограничения 100/сутки, 100/час, минимум 90 секунд. VPN не изменялся. Дополнительного отправителя или задачи не создавалось.']
        (SALES/'wave3-companies.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
        summary = {'checked_at':checked, 'new_companies':20, 'queue_size':54, 'previous_records_preserved':34,
                   'individual_pdf_attachments_checked':20, 'duplicate_companies':0, 'permission_inferred':False,
                   'new_sent':0, 'proposal_sha256':digest, 'before_queue_sha256':hashlib.sha256(original).hexdigest(),
                   'discarded_candidates':[r['company'] for n,r in sources.items() if n not in {s[0] for s in SELECTED}],
                   'checks':checks}
        (WAVE/'batch-check.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in summary.items() if k not in ('checks','discarded_candidates')}, ensure_ascii=True))


if __name__ == '__main__':
    build()
