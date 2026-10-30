"""Build a Russian offer, sanitized static demo and MIME previews. No email sends."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
SALES = ROOT/'sales/russia'
DATA = ROOT/'data/russia-outreach'

PERSONAL = [
 ('На вашем сайте представлены крашеные и плёночные фасады MDF, а заказ принимается по заполненному бланку.', 'Для такого заказа предлагаю посмотреть, как размеры и количество деталей связываются с расчётом и очередью распила, фрезеровки и покраски.'),
 ('На сайте «Восток» представлен ассортимент мебельных фасадов и отдельный контакт представительства в Нижнем Новгороде.', 'Для заказов мебельщиков предлагаю посмотреть единую карточку со спецификацией деталей, оплатами и текущим этапом цеха.'),
 ('На сайте АМК указано собственное производство мебели на заказ; в каталоге есть кухни и мебельные фасады.', 'На демо можно разобрать один индивидуальный заказ: позиции и размеры, расчёт, материалы и переход к этапам производства.'),
 ('На сайте «Атон Мебель» представлен каталог серийной мебели и информация для оптовых покупателей.', 'Для обсуждения с вашим производством предлагаю показать связь карточки заказа с материалами, оплатами и готовностью; требования серийного планирования разберём отдельно.'),
 ('ART AND SHIK описывает собственное производство полного цикла и работу по проектам и эскизам, со сметой и согласованием деталей.', 'Предлагаю показать, как согласованная спецификация может оставаться связанной с заказом и этапами цеха при работе над индивидуальным проектом.'),
 ('На сайте «Василини» представлены кухни, шкафы и другая мебель на заказ, а также замер и дизайн-проект.', 'Для вашего индивидуального заказа предлагаю посмотреть переход от заявки и расчёта к деталям, материалам, этапам производства и оплатам.'),
 ('Evelita предлагает изготовление мебели по индивидуальным размерам: на сайте представлены кухни, шкафы и проекты для разных помещений.', 'В таком формате полезно обсудить связь размеров деталей, сметы и состояния заказа в цехе; именно этот сценарий могу показать в демо.'),
 ('На сайте GS представлены кухни и корпусная мебель на заказ по индивидуальным проектам.', 'Предлагаю показать, как один заказ с размерами деталей проходит от заявки и расчёта к раскрою MDF, материалам и очереди производства.'),
 ('«Мебеллима» предлагает мебель на заказ и показывает индивидуальные проекты на своём сайте.', 'Для нестандартного проекта предлагаю посмотреть карточку с позициями и размерами, расчётом и этапами изготовления, чтобы обсудить ваш способ передачи заказа в цех.'),
 ('В портфолио РИТЕНГО есть мебель и торговое оборудование для коммерческих объектов.', 'На примере одного проектного заказа предлагаю показать связь спецификации деталей, материалов, оплаты и текущего этапа производства.'),
 ('На сайте мебельной фабрики «Атлант» представлены собственный мебельный ассортимент и отдельные контакты отделов.', 'Предлагаю обсудить передачу одного заказа от менеджера к производству и показать карточку с деталями, материалами, оплатами и этапами; потребности фабричного планирования уточним отдельно.'),
 ('Velvex на официальном сайте описывает производство мебели для ванных комнат и поставки партнёрам.', 'Для разговора с вашим производством предлагаю показать материалы и этапы одного заказа; требования к серийным партиям и существующему учёту обсудим отдельно.'),
 ('«Мебель для жизни» на сайте описывает изготовление мебели в Нижнем Новгороде и цикл от обращения и проекта до производства.', 'Предлагаю посмотреть, как заявка, расчёт, размеры деталей и текущий этап производства связываются в одном демонстрационном заказе.'),
 ('На сайте MKвадро представлены кухни, шкафы и другая корпусная мебель на заказ, с проектированием и изготовлением.', 'Для заказа кухни или шкафа могу показать связь спецификации деталей, расчёта, материалов и очереди цеха, а затем обсудить ваш процесс.'),
]

def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def message_for(lead,cfg):
    subject=f"Fasad Flow: заказ и производство — {lead['company']}"
    demo=(f"Демо с тестовыми данными: {cfg['demo_url']}\n" if cfg.get('demo_url') else
          'Если тема актуальна, ответьте на письмо — согласуем показ демо на тестовом заказе.\n'
          if cfg.get('demo_delivery')=='meeting' else '')
    body=(f"Здравствуйте!\n\n{lead['opening_ru']}\n\n"
          "Я развиваю Fasad Flow — прототип CRM для мебельного производства. "
          f"{lead['benefit_ru']}\n\n"
          "Во вложении — краткое КП в PDF: сценарий демо и предложение ограниченного пилота. "
          "Демонстрация работает на тестовых данных; цену, сроки, состав доработок и условия пилота обсудим после знакомства с вашим процессом.\n"
          f"{demo}\nПодойдёт короткий разговор на 15 минут, чтобы выбрать один заказ для демонстрации?\n\n"
          "Калдин Лев\nFasad Flow\nkoallalenivaa@gmail.com\n\n"
          "Если такие предложения неактуальны, ответьте «Отписка» — дальнейшие обращения прекратим.\n")
    return subject,body

def mime_for(lead,cfg,message_id=None):
    pdf=SALES/'proposal.pdf'
    if not pdf.is_file() or not pdf.read_bytes().startswith(b'%PDF-'): raise ValueError('Real PDF attachment missing')
    subject,body=message_for(lead,cfg)
    msg=EmailMessage(policy=SMTP)
    msg['From']=formataddr((cfg['sender_name'],cfg['expected_sender']))
    msg['To']=lead['email'];msg['Reply-To']=cfg['expected_sender'];msg['Subject']=subject
    if message_id: msg['Message-ID']=message_id
    msg.set_content(body)
    msg.add_alternative('<html lang="ru"><body>'+''.join('<p>'+html.escape(p).replace('\n','<br>')+'</p>' for p in body.split('\n\n'))+'</body></html>',subtype='html')
    msg.add_attachment(pdf.read_bytes(),maintype='application',subtype='pdf',filename='Fasad-Flow-KP.pdf')
    return msg

def build():
    SALES.mkdir(parents=True,exist_ok=True)
    DATA.mkdir(parents=True,exist_ok=True)
    snapshot=json.loads((DATA/'crm-source-2026-09-29.json').read_text(encoding='utf-8'))
    checks=json.loads((DATA/'source-checks.json').read_text(encoding='utf-8'))
    header,*rows=snapshot['values']
    config_path=SALES/'campaign.json'
    cfg=json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {
        'campaign_id':'fasad-flow-russia-v1','enabled':True,'expected_sender':'koallalenivaa@gmail.com',
        'sender_name':'Калдин Лев','openclaw_root':'E:\\open-claw-agent',
        'mailbox_profile':'H:\\serbiya\\outreach\\campaign.json','outbound_transport':'gmail_https',
        'timezone':'Europe/Moscow','daily_limit':100,'hourly_limit':100,'min_pause_seconds':90,
        'max_per_run':1,'demo_url':'','demo_sha256':'','demo_verified_at':'',
        'task_name':'Fasad Flow Russia Outreach',
        'consent_scope':'Fasad Flow: российская база CRM от 2026-09-29, первое КП и демо',
        'shared_history':['H:\\serbiya\\outreach\\campaign.sqlite3',str(ROOT/'data/serbia-outreach/campaign.sqlite3')],
    }
    write_json(config_path,cfg)
    leads=[]
    existing={}
    if (SALES/'campaign_leads.csv').exists():
        with (SALES/'campaign_leads.csv').open(encoding='utf-8-sig',newline='') as f: existing={r['email']:r for r in csv.DictReader(f)}
    for i,(row,check,personal) in enumerate(zip(rows,checks,PERSONAL),1):
        values={h:(row[n] if n<len(row) and row[n] is not None else '') for n,h in enumerate(header)}
        lead={'number':str(i),'company':values['Компания'],'city':values['Город'],
              'direction':values['Тип производства'],'email':values['E-mail'].casefold(),
              'phone':values['Телефон'],'website':values['Сайт'],'source_url':values['Источник'],
              'verified_at':check['checked_at'],'email_verified':str(check['email_found']).lower(),
              'fit_reason':values['Почему это производство'],'origin':'existing_russian_crm',
              'relationship':'prospect_in_crm; not proven existing customer',
              'crm_status':values['Статус'],'crm_message_id':values.get('OpenClaw Message-ID',''),
              'crm_first_email_at':values['Дата 1-го письма'],
              'opening_ru':personal[0],'benefit_ru':personal[1],
              'approved':'false','consent_at':'','consent_evidence':'','consent_scope':'',
              'do_not_contact':'false'}
        if i==1: lead['city']='Бор; выставочный зал — Нижний Новгород'
        if i==2: lead['city']='Нижний Новгород (представительство); производство — Йошкар-Ола'
        old=existing.get(lead['email'],{})
        for field in ['approved','consent_at','consent_evidence','consent_scope','do_not_contact']: lead[field]=old.get(field,lead[field])
        leads.append(lead)
    for old in existing.values():
        if old.get('origin')!='existing_russian_crm' and old['email'] not in {lead['email'] for lead in leads}:
            leads.append(old)
    crm_leads=[lead for lead in leads if lead['origin']=='existing_russian_crm']
    new_leads=[lead for lead in leads if lead['origin']!='existing_russian_crm']
    for filename,records in [('campaign_leads.csv',leads),('existing-crm-prospects.csv',crm_leads),('existing-customers.csv',[]),('new-researched-prospects.csv',new_leads)]:
        with (SALES/filename).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(leads[0]));writer.writeheader();writer.writerows(records)
    demo=SALES/'demo-public'
    demo.mkdir(exist_ok=True)
    for name in ['index.html','styles.css','app.js','production_flow.js','favicon.svg']:
        shutil.copyfile(ROOT/'demo'/name,demo/name)
    app=(demo/'app.js').read_text(encoding='utf-8')
    # Replace contact-like fields and names only in the seeded object; do not alter functionality.
    start,end=app.split('const PRODUCTION_STAGES=',1)
    contacts={}
    names=re.findall(r'(?:client|name):"([^"]+)"',start.split('workers:')[0])
    for name in dict.fromkeys(names): contacts[name]=f'Тестовый заказчик {len(contacts)+1:02d}'
    for name,replacement in contacts.items(): start=start.replace('"'+name+'"','"'+replacement+'"')
    start=re.sub(r'phone:"[^"]*"','phone:"Тестовый контакт"',start)
    n=[0]
    def email_repl(match): n[0]+=1;return f'email:"demo-{n[0]:02d}@example.invalid"'
    start=re.sub(r'email:"[^"]*"',email_repl,start)
    start=re.sub(r'address:"[^"]*"','address:"Тестовый адрес"',start)
    workers=start.split('workers:')[1].split('stock:')[0]
    for i,name in enumerate(re.findall(r'name:"([^"]+)"',workers),1):start=start.replace('"'+name+'"',f'"Тестовый сотрудник {i:02d}"')
    for i,name in enumerate(dict.fromkeys(re.findall(r'manager:"([^"]+)"',start)),1):start=start.replace('"'+name+'"',f'"Тестовый менеджер {i:02d}"')
    start=start.replace('Анна Белова','Тестовый менеджер 01').replace('Ольга Миронова','Тестовый менеджер 02')
    app=(start+'const PRODUCTION_STAGES='+end).replace('fasad-demo-data','fasad-public-test-v1')
    (demo/'app.js').write_text(app,encoding='utf-8')
    index=(demo/'index.html').read_text(encoding='utf-8').replace('Интерактивная демо-версия','Демо · только тестовые данные · суммы условные')
    index=index.replace('Фасад Профи','Тестовый цех').replace('Алексей Ковалёв','Тестовый пользователь')
    index=index.replace('<meta charset="utf-8">','<meta charset="utf-8">\n  <meta name="robots" content="noindex,nofollow">\n  <meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'self\'; style-src \'self\' \'unsafe-inline\'; img-src \'self\' data:; connect-src \'none\'; object-src \'none\'; base-uri \'none\'; form-action \'none\'">')
    (demo/'index.html').write_text(index,encoding='utf-8')
    (demo/'README.txt').write_text('Fasad Flow: статическое демо с тестовыми данными.\nРазместить содержимое на согласованном HTTPS-хостинге. Сервера, авторизации и API нет.\nИзменения хранятся только в браузере. Не вводить персональные или рабочие данные.\nСуммы и контактные записи условные; JSON для ЧПУ не является программой станка.\n',encoding='utf-8')
    manifest={p.name:sha(p) for p in demo.iterdir() if p.is_file() and p.name!='manifest.json'}
    write_json(demo/'manifest.json',manifest)
    with ZipFile(SALES/'demo-public.zip','w',ZIP_DEFLATED) as z:
        for p in demo.iterdir():z.write(p,p.name)
    from scripts.sync_public_demo import sync_public_demo
    sync_public_demo()
    intro='Fasad Flow связывает заявку, размеры деталей, расчёт, материалы и этапы изготовления в одном демонстрационном заказе. Предлагаю проверить этот подход на вашем процессе и определить объём пилота.'
    sections=[
      ('Задача','Согласованная спецификация должна быть доступна менеджеру и цеху вместе с текущим этапом заказа. На демонстрации обсуждаем, как сократить ручные уточнения по деталям, материалам и готовности. Эффект на вашем производстве проверяется отдельно.'),
      ('Что покажем за 15 минут','Создание заявки и позиций с размерами и количеством; переход в заказ и расчёт; демонстрационный раскрой MDF с картой, числом листов и оценкой расхода; резервирование и списание материала; этапы распила, фрезеровки, грунта, покраски и упаковки; оплата и выгрузка отчёта CSV.'),
      ('Текущая версия','Интерактивное браузерное демо на тестовых данных. Изменения сохраняются локально в браузере. Это прототип для проверки сценария; совместная работа пользователей, серверное хранение, роли, резервные копии и промышленная эксплуатация требуют отдельной реализации и проверки. Выгрузка ЧПУ — JSON с координатами деталей, не управляющая программа станка. Готовые интеграции с 1С, CAD/CAM и конкретным оборудованием не заявлены.'),
      ('Ограниченный пилот — предложение для обсуждения','Один выбранный процесс и одна согласованная группа пользователей. Начать с нескольких тестовых или обезличенных заказов и одной группы материалов. Сначала согласовать этапы, поля, контрольный сценарий, способ размещения и сохранности данных; затем оценить необходимые доработки. Реальные данные подключать только в согласованном защищённом контуре.'),
      ('Как оценивать пилот','Вместе пройти контрольный заказ: заявка → детали → расчёт → материалы → очередь цеха → готовность → оплата. Сверить размеры, расход и этапы с вашим способом учёта. При переходе к серверной версии отдельно проверить доступы, экспорт и восстановление. Критерии приёмки, ответственность и состав работ согласуются до старта.'),
      ('Следующий шаг','Короткий разговор на 15 минут: выбрать типовой заказ, понять текущую передачу спецификаций в цех и определить, что нужно для пилота. Цена, сроки, поддержка, лицензирование и условия оплаты — предмет обсуждения. В этом КП нет фиксированной цены или обязательства внедрения.'),
    ]
    demo_line=f'<p>Демонстрация: <a href="{html.escape(cfg["demo_url"])}">открыть тестовое демо</a></p>' if cfg['demo_url'] else '<p>На коротком разговоре покажу демонстрацию на тестовом заказе.</p>'
    content=''.join(f'<section><h2>{title}</h2><p>{text}</p></section>' for title,text in sections)
    proposal='''<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Fasad Flow — коммерческое предложение</title><style>
    @page{size:A4;margin:14mm}*{box-sizing:border-box}body{font:12.5px/1.45 Arial,sans-serif;color:#172033;margin:0;background:white}.label{color:#16715b;text-transform:uppercase;letter-spacing:2px;font-size:10px}h1{font-size:30px;line-height:1.08;margin:10px 0;color:#142941}h2{font-size:15px;color:#142941;margin:11px 0 4px}p{margin:4px 0 7px}header{border-bottom:3px solid #16715b;padding-bottom:10px}.flow{display:flex;gap:7px;margin:13px 0}.flow span{background:#edf5f2;padding:7px;font-size:11px;flex:1}section{break-inside:avoid}footer{margin-top:14px;padding-top:10px;border-top:1px solid #ccd6dd;font-size:11px;color:#43596b}a{color:#16715b}</style></head><body>'''
    proposal+=f'<header><div class="label">КП · CRM для мебельного производства · 29 сентября 2026</div><h1>Fasad Flow<br>От заявки к готовому заказу</h1><p>{intro}</p></header>'
    proposal+='<div class="flow"><span>Заявка и детали</span><span>Расчёт и MDF</span><span>Очередь цеха</span><span>Готовность и оплата</span></div>'+content+demo_line
    proposal+='<footer>Калдин Лев · Fasad Flow · koallalenivaa@gmail.com<br>Предложение обсудить пилот. Реквизиты и договорные условия согласуются отдельно.</footer></body></html>'
    (SALES/'proposal.html').write_text(proposal,encoding='utf-8')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.goto((SALES/'proposal.html').as_uri())
        page.pdf(path=str(SALES/'proposal.pdf'),format='A4',print_background=True,prefer_css_page_size=True)
        page.goto((demo/'index.html').as_uri())
        page.wait_for_selector('#app h1')
        page.screenshot(path=str(DATA/'demo-preview.png'),full_page=True)
        browser.close()
    import fitz
    with fitz.open(SALES/'proposal.pdf') as pdf:
        text='\n'.join(p.get_text() for p in pdf)
        assert 'Fasad Flow' in text and 'Калдин Лев' in text and 'предмет обсуждения' in text
        assert '{DEMO_URL}' not in text and 'localhost' not in text
        pdf[0].get_pixmap(matrix=fitz.Matrix(1.4,1.4)).save(DATA/'proposal-page1.png')
        if len(pdf)>1:pdf[1].get_pixmap(matrix=fitz.Matrix(1.4,1.4)).save(DATA/'proposal-page2.png')
        write_json(DATA/'pdf-check.json',{'pages':len(pdf),'bytes':(SALES/'proposal.pdf').stat().st_size,'sha256':sha(SALES/'proposal.pdf'),'text':text,'checked_at':datetime.now(timezone.utc).isoformat()})
    cfg['proposal_sha256']=sha(SALES/'proposal.pdf');write_json(config_path,cfg)
    previews=DATA/'previews';previews.mkdir(exist_ok=True)
    index=[f'<!doctype html><html lang="ru"><meta charset="utf-8"><title>Письма Fasad Flow · Россия</title><style>body{{max-width:1000px;margin:40px auto;font:16px/1.5 Arial}}article{{border-top:1px solid #ccd;padding:20px 0}}pre{{white-space:pre-wrap}}</style><h1>{len(leads)} персональных писем · локальные материалы</h1><p>Исходная российская CRM и отдельные новые исследованные контакты. Фактические отправки — в журнале кампании. Допуск требует основания контакта именно по Fasad Flow; публичный email не является согласием.</p>']
    receipt=[]
    for lead in leads:
        subject,body=message_for(lead,cfg)
        msg=mime_for(lead,cfg)
        filename=f"{int(lead['number']):02d}"
        (previews/(filename+'.eml')).write_bytes(msg.as_bytes())
        (previews/(filename+'.txt')).write_text(f"To: {lead['email']}\nSubject: {subject}\n\n{body}",encoding='utf-8')
        attachments=list(msg.iter_attachments())
        assert len(attachments)==1 and attachments[0].get_payload(decode=True)==(SALES/'proposal.pdf').read_bytes()
        receipt.append({'company':lead['company'],'email':lead['email'],'filename':filename+'.eml','pdf_bytes':len(attachments[0].get_payload(decode=True)),'sha256':sha(previews/(filename+'.eml'))})
        index.append(f"<article><h2>{filename}. {html.escape(lead['company'])}</h2><p>{html.escape(lead['email'])}</p><h3>{html.escape(subject)}</h3><pre>{html.escape(body)}</pre><a href='{filename}.eml'>EML с PDF</a> · <a href='{filename}.txt'>Текст</a></article>")
    (previews/'index.html').write_text('\n'.join(index),encoding='utf-8')
    write_json(DATA/'mime-checks.json',receipt)
    write_json(SALES/'templates_ru.json',{'campaign_id':cfg['campaign_id'],'messages':[
        {'company':lead['company'],'email':lead['email'],'subject':message_for(lead,cfg)[0],'body':message_for(lead,cfg)[1]}
        for lead in leads]})
    (SALES/'recipients-for-confirmation.md').write_text(f'# Российский список Fasad Flow\n\n{len(crm_leads)} существующих лидов CRM и {len(new_leads)} новых исследованных компаний. Подтверждение должно относиться к конкретным адресам и предложению Fasad Flow. Наличие строки в этом списке не подтверждает согласие.\n\n'+ '\n'.join(f"{lead['number']}. {lead['company']} — {lead['email']}" for lead in leads)+'\n',encoding='utf-8')
    (SALES/'demo-walkthrough.md').write_text('# Сценарий демо Fasad Flow\n\nДанные тестовые, суммы условные. Открыть index.html из demo-public.\n\n1. В рабочем месте создать заявку с 2–3 позициями MDF, размерами и количеством.\n2. Открыть её «В заказ», создать заказ и проверить спецификацию и расчёт.\n3. Открыть раскрой, изменить количество деталей и увидеть пересчёт карты, листов и расхода.\n4. Передать заказ в производство; показать резервирование листов и этап распила.\n5. Продвинуть на фрезеровку и показать списание материала; обсудить грунт и покраску.\n6. Записать тестовую оплату, проверить остаток, выгрузить CSV.\n7. Показать JSON для ЧПУ и прямо объяснить, что это не управляющая программа станка.\n8. Обсудить серверное хранение, роли и доработки для ограниченного пилота.\n',encoding='utf-8')
    print(json.dumps({'companies':len(leads),'pdf_bytes':(SALES/'proposal.pdf').stat().st_size,'mime_previews':len(receipt),'demo':str(demo),'sent':0},ensure_ascii=False))

if __name__=='__main__':build()
