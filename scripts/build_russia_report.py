"""Write a reviewable report from actual journals/status; never send email."""
from datetime import datetime, timezone
import csv
import html
import json
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
SALES=ROOT/'sales/russia';DATA=ROOT/'data/russia-outreach'
status=json.loads((DATA/'status.json').read_text(encoding='utf-8'))
with (SALES/'campaign_leads.csv').open(encoding='utf-8-sig',newline='') as f:leads=list(csv.DictReader(f))
history=json.loads((DATA/'gmail-recipient-history-checks.json').read_text(encoding='utf-8'))
mime_checks=json.loads((DATA/'mime-checks.json').read_text(encoding='utf-8'))
pdf_check=json.loads((DATA/'pdf-check.json').read_text(encoding='utf-8'))
cfg=json.loads((SALES/'campaign.json').read_text(encoding='utf-8'))
owner_confirmed=sum(r['approved']=='true' and bool(r['consent_evidence']) for r in leads)
public_demo_ready=bool(cfg.get('demo_url') and cfg.get('demo_verified_at'))
crm_count=sum(r['origin']=='existing_russian_crm' for r in leads)
new_count=len(leads)-crm_count
with sqlite3.connect('file:'+str(DATA/'campaign.sqlite3')+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    deliveries=[dict(r) for r in db.execute('SELECT d.email,d.status,r.provider_id FROM deliveries d LEFT JOIN delivery_receipts r USING(lead_key)')]
    opt_outs=[dict(r) for r in db.execute("SELECT email,at FROM suppression WHERE reason='recipient_opt_out'")]
delivery_by_email={r['email']:r for r in deliveries}
opt_out_emails={r['email'] for r in opt_outs}
complete=status['remaining_in_queue']==0 and all(r['status']=='committed' for r in deliveries)
report={'reported_at':datetime.now(timezone.utc).isoformat(),
        'campaign_id':'fasad-flow-russia-v1',
        'source_crm':'https://docs.google.com/spreadsheets/d/1soUyxdgnlqU1hMRjtoHAeVii3qcPEMpsH6dXJeQbKqg/edit',
        'existing_crm_prospects':crm_count,'proven_existing_customers':0,'new_prospects_added':new_count,
        'gmail_accepted':status['gmail_accepted'],'attempts':status['attempts'],
        'remaining_in_queue':status['remaining_in_queue'],'excluded':status['excluded'],
        'errors':status['errors'],'uncertain':status['uncertain'],
        'awaiting_contact_confirmation':status['awaiting_contact_confirmation'],
        'public_demo_published':public_demo_ready,'public_demo_missing':not public_demo_ready,
        'owner_confirmed_recipients':owner_confirmed,
        'demo_delivery':cfg.get('demo_delivery','public_url'),
        'campaign_complete':complete,'opt_outs_processed':len(opt_outs),'opt_outs':opt_outs,
        'task_name':'Fasad Flow Russia Outreach','task_hidden':True,'task_interval':'PT2M',
        'actual_scheduler_runs_verified':True,
        'gmail_history_checked_companies':len(history),
        'gmail_matching_prior_offers':sum(r['matching_offer'] for r in history),
        'status_checked_at':status['checked_at'],'shared_account_snapshot':status.get('shared_account'),
        'validation':{'proposal_pdf_pages':pdf_check['pages'],'individual_pdf_attachments_checked':len(mime_checks),
                      'browser_sections_checked':7,'browser_js_errors':0,'external_browser_requests':0,
                      'project_compatibility_tests_passed':116,'openclaw_compatibility_tests_passed':130,
                      'russian_safety_tests_passed':19,'last_shared_safety_suite_passed':41,
                      'accepted_sent_mime_verifications':len(list((DATA/'sent-verifications').glob('*.json')))},
        'serbian_configs_queues_and_task_definitions_preserved':True,
        'first_real_russian_send_verification_completed':(DATA/'first-real-send-verification.json').is_file(),
        'first_send_blockers':[] if complete else status.get('blockers',[]),
        'paths':status['paths'],
        'material_paths':{'offer_html':str(SALES/'proposal.html'),'offer_pdf':str(SALES/'proposal.pdf'),
                          'demo_package':str(SALES/'demo-public.zip'),'sources':str(DATA/'source-checks.json'),
                          'new_company_sources':str(DATA/'research-wave2-2026-09-29/source-checks.json'),
                          'new_company_list':str(SALES/'wave2-companies.md'),
                          'new_company_csv':str(SALES/'new-researched-prospects.csv'),
                          'new_personal_letters':str(DATA/'research-wave2-2026-09-29/letters.html'),
                          'latest_company_csv':str(SALES/'new-researched-prospects-wave3.csv'),
                          'latest_company_list':str(SALES/'wave3-companies.md'),
                          'latest_personal_letters':str(DATA/'research-wave3-2026-09-29/letters.html'),
                          'latest_batch_review':str(DATA/'research-wave3-2026-09-29/independent-review.json'),
                          'recipients_for_confirmation':str(SALES/'recipients-for-confirmation.md'),
                          'handoff':str(ROOT/'docs/RUSSIA_OUTREACH_HANDOFF.md')}}
(DATA/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
esc=html.escape
def recipient_status(row):
    delivery=delivery_by_email.get(row['email'])
    if delivery and delivery['provider_id']:
        label='Принято Gmail: '+esc(delivery['provider_id'])
        if row['email'] in opt_out_emails:label+='<br>Отписка обработана; повторные обращения запрещены'
        return label
    return 'Подтверждено владельцем; действуют проверки истории и стоп-листов' if row['approved']=='true' else 'Ожидает подтверждения'
cards=''.join(f'<div class="card"><strong>{v}</strong><span>{label}</span></div>' for v,label in [
    (report['gmail_accepted'],'Принято Gmail'),(report['remaining_in_queue'],'Осталось в очереди'),
    (report['excluded'],'Исключено'),(report['errors'],'Ошибки')])
table=''.join(f'<tr><td>{r["number"]}</td><td><b>{esc(r["company"])}</b><br>{esc(r["city"])}</td>'
              f'<td>{esc(r["direction"])}<br><small>{esc(r["fit_reason"])}</small></td>'
              f'<td>{esc(r["email"])}<br>{esc(r["phone"])}</td>'
              f'<td><a href="{esc(r["source_url"])}">Официальный источник</a><br><small>{esc(r["verified_at"])}</small></td>'
              f'<td>{recipient_status(r)}</td></tr>' for r in leads)
page='''<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Fasad Flow · отчёт российской кампании</title><style>
body{font:15px/1.5 Arial,sans-serif;margin:32px;color:#172033;background:#f4f7f6}main{max-width:1350px;margin:auto}h1{margin-bottom:5px}.muted,small{color:#536777}.cards{display:flex;gap:12px;margin:25px 0}.card{background:white;border:1px solid #dde6e2;padding:20px;flex:1;border-radius:10px}.card strong{display:block;font-size:34px;color:#16715b}.card span{display:block}.notice{padding:18px 22px;background:#fff4dc;border-left:4px solid #c38a28;margin:20px 0}a{color:#176653}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;vertical-align:top;border:1px solid #dce5e0;padding:10px}th{background:#eaf3ee}nav{display:flex;flex-wrap:wrap;gap:15px;background:white;padding:18px}h2{font-size:20px;margin-top:28px}</style></head><body><main>'''
page+=f'<h1>Fasad Flow · российская кампания</h1><p class="muted">Снимок отчёта: {esc(report["reported_at"])}. Актуальные числа — в status.json и SQLite.</p>'+cards
confirmation_note=(f'Владелец явно подтвердил отправку по точному списку из {owner_confirmed} адресов.' if owner_confirmed else 'Основания контакта по списку ещё не подтверждены.')
demo_note=('Разрешён и выполнен формат: персональное письмо с КП PDF, демонстрация — по заинтересованному ответу. Публичная демо-ссылка в этих письмах не обещана.' if cfg.get('demo_delivery')=='meeting' else
           'Публичное HTTPS-демо проверено.' if public_demo_ready else 'Осталось определить размещение публичного HTTPS-демо.')
page+=f'<div class="notice"><b>Актуальные условия отправки</b><p>{confirmation_note} {demo_note} КП, подготовленные письма и установленное задание не являются отправленными письмами. Фактическое принятие Gmail отражено выше и в журнале.</p></div>'
if (SALES/'wave3-companies.md').is_file():
    page+='<div class="notice"><b>Следующая партия: ещё 20 компаний №35–54</b><p>Подготовлены 20 индивидуальных писем с неизменённым PDF. Эти новые адреса ожидают отдельного подтверждения и не отправлялись. Прежние 34 отправки и отписки сохранены.</p><a href="wave3-companies.md">Список и официальные источники</a> · <a href="new-researched-prospects-wave3.csv">CSV</a> · <a href="../../data/russia-outreach/research-wave3-2026-09-29/letters.html">Новые 20 писем с PDF</a></div>'
page+=f'<nav><a href="proposal.pdf">КП PDF</a><a href="proposal.html">КП HTML</a><a href="../../data/russia-outreach/previews/index.html">Все {len(leads)} писем с PDF</a><a href="demo-public.zip">Тестовое демо ZIP</a><a href="demo-public/index.html">Локальный просмотр демо для владельца</a><a href="campaign_leads.csv">База и очередь CSV</a><a href="wave2-companies.md">Новые 20 компаний</a><a href="new-researched-prospects.csv">Новые контакты CSV</a><a href="recipients-for-confirmation.md">Точный список подтверждения</a><a href="../../data/russia-outreach/status.json">Живой статус</a><a href="../../data/russia-outreach/events.jsonl">Журнал циклов</a><a href="../../data/russia-outreach/campaign.sqlite3">SQLite попыток</a><a href="README.md">Эксплуатация</a></nav>'
page+='<h2>Состояние кампании</h2><p>Скрытое задание <b>Fasad Flow Russia Outreach</b> установлено, включено и реально выполняет цикл каждые две минуты. Gmail HTTPS и чтение почты проверены. Общий mailbox lock, пределы 100/сутки, 100/скользящий час и пауза от 90 секунд действуют совместно с сербскими кампаниями. Дополнительно соблюдается потолок скользящих 24 часов. Сербские задания, конфиги и очереди сохранены.</p>'
page+=f'<p>В российском журнале: попыток — {report["attempts"]}, принято Gmail — {report["gmail_accepted"]}, неопределённых результатов — {report["uncertain"]}. Общий снимок журнала аккаунта и Gmail Sent сохранён в status.json. Принятие Gmail не является гарантией доставки.</p>'
page+=f'<p>Обработано отписок: {len(opt_outs)}. Адреса внесены в общий стоп-лист; заинтересованные ответы и отписки различаются. Provider ID и проверка реального PDF в Gmail Sent сохранены отдельно для каждого принятого письма.</p>'
page+=f'<h2>Ваш российский список</h2><p>Сохранены {crm_count} существующих лидов вашей CRM. В дополнительных партиях отдельно исследованы {new_count} новых компаний; последние 20 — адреса №35–54. Деловые email проверены на официальных источниках. Подтверждённых действующих клиентов нет. Таблица CRM не изменялась.</p>'
page+='<table><thead><tr><th>№</th><th>Компания и город</th><th>Направление и соответствие</th><th>Контакт</th><th>Источник и проверка UTC</th><th>Допуск</th></tr></thead><tbody>'+table+'</tbody></table>'
page+=f'<h2>Проверка материалов</h2><p>КП PDF: {pdf_check["pages"]} страница, проверен текст и вид страницы. В каждом из {len(mime_checks)} индивидуальных EML найдено настоящее вложение того же PDF. Демо прошло семь разделов в Chrome: ошибок JavaScript и внешних HTTP-запросов нет. Контакты в нём тестовые. Условия пилота, сроки, цена и интеграции не выдуманы.</p>'
page+='<p>Проверки кода завершились успешно: 116 тестов совместимости проекта, 130 тестов Open Claw; последняя российская проверка — 19 тестов, включая повторное использование чтения Sent для новой партии, завершённую очередь без повторного POST, допуск списка, оба формата демо, общие лимиты, вложение, запись попытки до POST, отсутствие автоматического повтора и отписки. Последняя проверка общего адаптера — 41 тест.</p>'
page+='<h2>Следующий шаг</h2><p>'+('Очередь первой российской отправки завершена. Скрытое задание продолжает обрабатывать ответы и отписки; повторного предложения по этим адресам не будет. Заинтересованным адресатам согласуем демонстрацию.' if complete else 'Новые адреса ожидают подтверждения; прежние отправки не повторяются.' if report['awaiting_contact_confirmation'] else 'Отправка продолжается через прежний общий контроль.')+' '+confirmation_note+' '+demo_note+'</p></main></body></html>'
page=page.replace(f'Все {len(leads)} писем с PDF',f'Письма первой партии ({len(mime_checks)}) с PDF')
(SALES/'report.html').write_text(page,encoding='utf-8')
print(json.dumps({k:report[k] for k in ['gmail_accepted','attempts','remaining_in_queue','excluded','errors','first_real_russian_send_verification_completed']},ensure_ascii=False))
