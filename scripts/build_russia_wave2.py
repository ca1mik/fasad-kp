"""Append 20 source-checked Russian prospects without inferring contact permission."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import hashlib
import html
import io
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from serbia_outreach import worker_lock

SALES = ROOT / 'sales/russia'
DATA = ROOT / 'data/russia-outreach'
RESEARCH = DATA / 'research-wave2-2026-09-29'
ORIGIN = 'new_russian_research_wave2_2026_09_29'

# Facts and personalization are grounded in the official pages archived alongside this script's output.
SELECTED = [
 (1, '2 Фасада', 'Казань', 'Фасады MDF; фрезеровка и покраска', 'parket-install@mail.ru', '+7 927 432-21-25',
  'На вашем сайте представлены мебельные фасады MDF и услуги фрезеровки и покраски.',
  'Предлагаю на тестовом заказе показать связь размеров фасадов, расчёта и очереди обработки, чтобы менеджер видел текущий этап каждой партии.'),
 (3, 'Фасады32', 'Брянск', 'Производство мебельных фасадов MDF', 'info@fasady32.ru', '+7 920 855-08-11',
  'Фасады32 предлагает мебельщикам фасады MDF собственного производства.',
  'Для заказов партнёров предлагаю показать одну карточку со спецификацией деталей, материалами, этапами цеха и оплатами.'),
 (5, 'Aras Mebeli', 'Чехов, Московская область', 'Крашеные фасады MDF на заказ', 'info@arasmebeli.ru', '+7 977 768-84-80',
  'На сайте Aras Mebeli представлены крашеные фасады MDF и выбор цвета по RAL и NCS.',
  'На демо предлагаю разобрать заказ с индивидуальными размерами: спецификация, расчёт, расход MDF и переход от обработки к покраске.'),
 (6, 'МУРАШОВМЕБЕЛЬ', 'Армавир', 'Фасады MDF; фрезеровка, шлифовка и покраска', 'murashoff.fasad@yandex.com', '+7 918 490-92-66',
  'МУРАШОВМЕБЕЛЬ описывает производство фасадов MDF с фрезеровкой, шлифовкой и покраской.',
  'Предлагаю показать, как состав заказа остаётся связан с очередью цеха: от размеров и расчёта до готовности и оплаты.'),
 (7, 'ДСП Комплект', 'Москва; производство — Домодедово', 'Фасады MDF; ЧПУ и раскрой', 'dspkomplekt@mail.ru', '+7 495 978-87-75',
  'На сайте ДСП Комплект описаны собственное производство фасадов MDF и работа на оборудовании с ЧПУ.',
  'Для обсуждения вашего процесса покажу связь спецификации заказа с демонстрационной картой раскроя, резервом материала и этапами цеха. Управляющие программы станков продукт пока не формирует.'),
 (8, 'Первая Фабрика Фасадов', 'Екатеринбург', 'Фасады MDF в ABS и PVC; присадка на ЧПУ', 'info@fabfas.ru', '+7 343 222-00-94',
  'На сайте Первой Фабрики Фасадов представлены коллекции на основе MDF в кромке ABS и плёнке PVC, а также присадка на ЧПУ.',
  'Предлагаю обсудить отдельный заказ: как спецификация, материал, состояние обработки и оплаты могут быть видны в одной карточке. Требования к серийному планированию и оборудованию уточним отдельно.'),
 (9, 'Альфа Фасад', 'Санкт-Петербург', 'Производство и покраска мебельных фасадов', 'alfafacade@yandex.ru', '+7 950 224-88-55',
  'Альфа Фасад представляет собственное производство мебельных фасадов и покраску MDF.',
  'Предлагаю показать тестовую партию фасадов: размеры и количество, расчёт, материалы, переход по этапам обработки и готовность к выдаче.'),
 (11, 'Мебельная мастерская MPV', 'Лыткарино, Московская область', 'Фасады MDF, массива и шпона; мебель на заказ', 'mm.mpv@mail.ru', '+7 916 715-99-55',
  'На сайте мастерской MPV представлены фасады из MDF, массива и шпона и изготовление мебели на заказ.',
  'Для одного индивидуального заказа предлагаю показать карточку деталей, материалов и этапов. Раскрой в текущем демо ориентирован на MDF; работу с массивом и шпоном обсудим как отдельное требование.'),
 (12, 'Фиеста-Color', 'Тельмановское сельское поселение, Ленинградская область', 'Фасады MDF; фрезеровка, покраска и шпон', 'info@fiesta-color.ru', '+7 911 108-52-46',
  'Фиеста-Color предлагает мебельные фасады MDF, включая крашеные и шпонированные варианты.',
  'Предлагаю на тестовом заказе показать передачу спецификации в производство, учёт материала и видимость этапов фрезеровки, грунта и покраски.'),
 (13, 'Сидак-СП', 'Сиверский, Ленинградская область', 'Производство мебельных фасадов', 'info@sidak.ru', '+7 812 655-61-51',
  'На сайте Сидак-СП представлены фасады собственного производства и ассортимент для мебельных компаний.',
  'Для разговора с вашим производством предлагаю показать учёт отдельного заказа: детали, материалы, готовность и оплаты. Требования крупного производства и обмен с существующими системами нужно обсудить отдельно.'),
 (14, 'КАРАТ', 'Новосибирск', 'Крашеные фасады MDF по размерам; радиусные фасады', 'dmitrijbondareff@yandex.ru', '+7 913 062-82-54',
  'КАРАТ представляет крашеные фасады MDF по размерам заказчика, в том числе радиусные.',
  'На демо предлагаю разобрать учёт размеров, количества и этапов партии. Карта раскроя сейчас рассчитана на прямоугольные детали; радиусные изделия потребуют отдельного обсуждения.'),
 (15, 'Дар труда', 'Москва', 'Столярные заказы; раскрой, ЧПУ и покраска', 'zakaz@dartruda.ru', '+7 495 120-04-96',
  'В отделе заказов «Дар труда» представлены столярные изделия, фрезеровка на ЧПУ и покраска, включая работу с MDF.',
  'Предлагаю выбрать один тестовый заказ MDF и показать путь от спецификации и расчёта к материалам, очереди цеха и оплате. Для ЧПУ есть только JSON с координатами, не программа станка.'),
 (16, 'ДЕКОВУД', 'Санкт-Петербург', 'Столярное производство; мебель по индивидуальным проектам', 'sale@dekowoods.ru', '+7 921 395-44-17',
  'ДЕКОВУД представляет столярное производство и изготовление мебели по индивидуальным проектам.',
  'Для одного проектного заказа предлагаю показать связь согласованной спецификации с материалами, этапами работы и оплатами; особенности массива и шпона уточним отдельно.'),
 (17, 'Мебельная фабрика 11', 'Новосибирск', 'Мебель на заказ; раскрой и фрезеровка', 'opitmebel11@yandex.ru', '+7 383 212-41-75',
  'Мебельная фабрика 11 предлагает мебель на заказ и услуги раскроя и фрезеровки.',
  'Предлагаю разобрать один заказ: как размеры деталей, расчёт, резерв MDF и очередь цеха могут оставаться в единой карточке до готовности и оплаты.'),
 (18, 'БРИГИТТА МЕБЕЛЬ', 'Челябинск', 'Мебельные фасады MDF и декоративные панели', 'brig-m74@mail.ru', '+7 351 238-48-43',
  'На сайте БРИГИТТА МЕБЕЛЬ представлены фрезерованные фасады MDF, дверные панели и спинки кроватей.',
  'Предлагаю показать на тестовой партии учёт деталей разных размеров, расчёт материала и переходы между этапами производства.'),
 (19, 'Фабрика мебельных фасадов 174', 'Челябинск', 'Производство фасадов MDF в PVC', 'fasad@fasad174.ru', '+7 351 225-04-46',
  'Фабрика мебельных фасадов 174 предлагает фасады MDF, а на сайте выделен отдел обработки заказов на фасады.',
  'Для этого процесса предлагаю показать, как заявка со списком деталей превращается в заказ, связанный с материалами, этапами цеха и оплатами. Этапы вашего покрытия уточним отдельно.'),
 (20, 'Фабрика Фасадов', 'Архангельск', 'Производство фасадов MDF в PVC', 'zakazfasadov@yandex.ru', '+7 921 477-82-26',
  'На сайте Фабрики Фасадов в Архангельске представлены мебельные фасады MDF в плёнке PVC.',
  'Предлагаю показать карточку заказа с размерами, количеством, материалами и готовностью партии. Этапы для плёночных фасадов согласуем в пилоте отдельно.'),
 (21, 'Сибирские мебельные фасады', 'Томск', 'Производство мебельных фасадов в PVC', 'fmtrio@mail.ru', '+7 996 937-37-72',
  'Сибирские мебельные фасады представляет производство фасадов и контакт производственной площадки в Томске.',
  'На демо предлагаю показать учёт отдельной партии: спецификация, материал, очередь обработки и готовность. Ваш маршрут плёночных фасадов обсудим как требование к пилоту.'),
 (22, 'BORA fasad', 'Лермонтов, Ставропольский край', 'Фасады из массива; шпон и мебельный декор', 'fasadbora@mail.ru', '8 800 600-96-16',
  'BORA fasad предлагает фасады из массива, шпонированные элементы и мебельный декор собственного производства.',
  'Предлагаю обсудить учёт индивидуального заказа — спецификацию, этапы и оплаты. Раскрой текущего демо ориентирован на MDF; особенности вашего массива и шпона потребуют отдельной проработки.'),
 (23, 'Альянс Мебель', 'Тверь', 'Фасады MDF с фрезеровкой, эмалью, PVC и шпоном', 'aljans_tver@mail.ru', '+7 4822 41-96-83',
  'В разделе для мебельщиков Альянс Мебель представлены фасады MDF с фрезеровкой, эмалью, плёнкой PVC и натуральным шпоном.',
  'Предлагаю показать отдельный заказ партнёра: размеры и количество деталей, расчёт, материалы и очередь цеха. Разные маршруты покрытия уточним при обсуждении пилота.'),
]

def main():
    sources = json.loads((RESEARCH/'source-checks.json').read_text(encoding='utf-8'))
    sources.append(json.loads((RESEARCH/'extra-source-check.json').read_text(encoding='utf-8')))
    checked = datetime.now(timezone.utc).isoformat()
    supplements = [
      {'candidate_number':8, 'checked_at':checked, 'retrieval_method':'official_site_web_search',
       'url':'https://fabfas.ru/contact/', 'emails':['info@fabfas.ru'],
       'fact_summary':'Центральный офис: Екатеринбург, Николы Теслы 12; телефон +7 343 222 00 94. Производство MDF в ABS/PVC и присадка ЧПУ подтверждены главной страницей.',
       'production_source':'https://fabfas.ru/', 'local_fetch_issue':'TLS validation failed; TLS checks were not bypassed'},
      {'candidate_number':15, 'checked_at':checked, 'retrieval_method':'official_site_web_open',
       'url':'https://www.dartruda.ru/zakaz', 'emails':['zakaz@dartruda.ru'],
       'fact_summary':'Москва. Отдел столярных заказов, изделия MDF/ДСП/массива, раскрой и фрезеровка ЧПУ, покраска. Телефон +7 495 120 04 96.',
       'local_fetch_issue':'HTTP 403; official page read using web tool'},
    ]
    (RESEARCH/'web-source-verifications.json').write_text(json.dumps(supplements,ensure_ascii=False,indent=2),encoding='utf-8')
    by_number={r['candidate_number']:r for r in sources}
    extra={r['candidate_number']:r for r in supplements}
    with worker_lock(DATA/'worker.lock'):
        path=SALES/'campaign_leads.csv'
        original_bytes=path.read_bytes()
        with path.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream); fields=reader.fieldnames; old=list(reader)
        previous=[r for r in old if r['origin']!=ORIGIN]
        email_set={r['email'].casefold() for r in previous}
        hosts={urlparse(r['website']).hostname.removeprefix('www.') for r in previous}
        records=[]
        for offset,(candidate,company,city,direction,email,phone,opening,benefit) in enumerate(SELECTED,15):
            source=by_number[candidate]
            live=[p for p in source['pages'] if p.get('http_status')==200 and email in {e.casefold() for e in p.get('emails',[])}]
            supplement=extra.get(candidate)
            if not live and not supplement:raise ValueError(f'No official email verification: {email}')
            website=source['website']
            host=urlparse(website).hostname.removeprefix('www.')
            if email in email_set or host in hosts:raise ValueError(f'Duplicate company: {company}')
            email_set.add(email);hosts.add(host)
            evidence=live[-1] if live else supplement
            row={k:'' for k in fields}
            row.update(number=str(offset),company=company,city=city,direction=direction,email=email,phone=phone,
                       website=website,source_url=evidence['url'],verified_at=source['checked_at'] if live else supplement['checked_at'],
                       email_verified='true',fit_reason=f'{direction}; релевантны спецификация заказа, материалы, этапы цеха и оплаты.',
                       origin=ORIGIN,relationship='new_researched_prospect; no customer or consent evidence',crm_status='Новый',
                       opening_ru=opening,benefit_ru=benefit,approved='false',do_not_contact='false')
            prior=next((r for r in old if r['email'].casefold()==email),None)
            if prior:
                for k in ('approved','consent_at','consent_evidence','consent_scope','do_not_contact'):row[k]=prior[k]
            records.append(row)
        if len(records)!=20:raise ValueError('Expected exactly twenty new prospects')
        backup=RESEARCH/'queue-before-wave2.csv'
        if not backup.exists():backup.write_bytes(original_bytes)
        buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=fields)
        writer.writeheader();writer.writerows(previous+records)
        temp=path.with_suffix('.csv.tmp');temp.write_text(buffer.getvalue(),encoding='utf-8-sig',newline='')
        temp.replace(path)
        buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=fields)
        writer.writeheader();writer.writerows(records)
        (RESEARCH/'companies.csv').write_text(buffer.getvalue(),encoding='utf-8-sig',newline='')
        manifest={'created_at':checked,'requested_new_companies':20,'existing_records_preserved':len(previous),
                  'queue_size':len(previous)+20,'permission_inferred':False,'sent':0,
                  'before_queue_sha256':hashlib.sha256(original_bytes).hexdigest(),
                  'selected_candidate_numbers':[r[0] for r in SELECTED],
                  'discarded_candidates':[{'number':2,'reason':'No verified business email'},
                                         {'number':4,'reason':'No verified business email'},
                                         {'number':10,'reason':'No verified business email; protected site'}]}
        (RESEARCH/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        lines=['# Ещё 20 российских компаний — Fasad Flow', '',
               'Проверка официальных источников: 29 сентября 2026. Новые найденные контакты, отдельно от 14 лидов исходной CRM. Согласие не установлено. Письма подготовлены локально; отправок этой партии нет.', '',
               '| № | Компания / город | Направление | Деловой email / телефон | Источник |',
               '|---|---|---|---|---|']
        for r in records:
            lines.append(f"| {r['number']} | {r['company']} / {r['city']} | {r['direction']} | {r['email']} / {r['phone']} | [Официальный сайт]({r['source_url']}) |")
        lines += ['', 'Для допуска укажите конкретные адреса, для которых есть основание отправить первое КП и демо Fasad Flow, и само основание или расположение подтверждения. Публичный email и поиск компании не являются согласием.', '',
                  'Для Первой Фабрики Фасадов и Дар труда контакт проверен через web-инструмент по официальной странице; ограничения прямого HTTP-запроса записаны отдельно. Остальные выбранные страницы получены с HTTP 200.']
        (SALES/'wave2-companies.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        print(json.dumps(manifest,ensure_ascii=False))

if __name__=='__main__':main()
