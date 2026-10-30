"""Build the reviewable commercial offer; does not change outreach attachments."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / 'sales/russia/fasad-offer.html'
PDF = ROOT / 'output/pdf/fasad-commercial-offer.pdf'
CSS = '''
@page {size:A4;margin:0} *{box-sizing:border-box} body{margin:0;background:#e6e9ec;color:#182d38;font-family:Arial,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{width:210mm;height:297mm;padding:17mm 17mm 15mm;background:#fff;position:relative;overflow:hidden;page-break-after:always}.page:last-child{page-break-after:auto}
.top{display:flex;justify-content:space-between;align-items:center;font-size:10px;letter-spacing:1.6px;text-transform:uppercase}.brand{font-size:19px;font-weight:900;letter-spacing:2px}.brand b{color:#20816c}.tag{color:#69818a;font-size:9px}
h1{font-size:48px;line-height:1.03;letter-spacing:-2px;margin:37px 0 19px;font-weight:800}h1 em{font-style:normal;color:#20816c}h2{font-size:32px;line-height:1.1;letter-spacing:-1px;margin:26px 0 14px}h3{font-size:16px;margin:0 0 8px}p{font-size:13px;line-height:1.55;margin:0 0 12px}.lead{font-size:16px;line-height:1.5;color:#526a75;max-width:590px}.eyebrow{font-size:10px;font-weight:bold;letter-spacing:1.5px;color:#20816c;text-transform:uppercase}.dark{background:#182d38;color:white;border-radius:16px;padding:24px;margin:25px 0}.dark p{color:#bcd0d4}.dark .eyebrow{color:#71d6ba}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.card{background:#f1f6f5;border:1px solid #e1eae7;border-radius:12px;padding:18px}.card p{font-size:12px;color:#526a75;margin:0}.num{font-size:11px;letter-spacing:1px;color:#20816c;font-weight:bold;margin-bottom:11px}.flow{display:flex;gap:8px;margin:18px 0 0}.flow div{flex:1;padding:13px 8px;border:1px solid #46606b;border-radius:8px;font-size:11px;line-height:1.5}.flow b{display:block;color:#71d6ba;font-size:9px;margin-bottom:5px}.foot{position:absolute;bottom:13mm;left:17mm;right:17mm;display:flex;justify-content:space-between;border-top:1px solid #dae4e5;padding-top:10px;font-size:9px;color:#6b818b}.note{font-size:10px;color:#6b818b;line-height:1.5}.row{display:grid;grid-template-columns:48px 1fr;gap:14px;padding:17px 0;border-bottom:1px solid #e0e8e8}.row .n{font-size:28px;color:#20816c;font-weight:bold}.row p{margin:0;color:#526a75;font-size:12px}.row h3{margin-bottom:5px}.price{font-size:30px;letter-spacing:-1px;font-weight:bold;margin:12px 0 8px}.price small{font-size:12px;font-weight:normal;letter-spacing:0}.band{background:#e4f2ed;border-radius:10px;padding:17px 20px;margin-top:20px}.band p{margin:0;font-size:12px}.check{padding:11px 0;border-bottom:1px solid #e0e8e8;font-size:12px;line-height:1.5}.check b{display:block}.cta{font-size:23px;font-weight:bold;line-height:1.25;margin:10px 0 15px}a{color:inherit;text-decoration:none}.contact{font-size:17px;color:#71d6ba;font-weight:bold}.pill{display:inline-block;background:#e4f2ed;color:#20816c;border-radius:20px;padding:7px 11px;font-size:10px;margin-top:18px}
@media screen{.page{margin:24px auto;box-shadow:0 8px 45px #182d3820}} @media(max-width:800px){.page{margin:0;transform-origin:top left}}
'''

def shell(content, number):
    return f'<section class="page"><div class="top"><div class="brand">FASAD <b>FLOW</b></div><div class="tag">CRM для производства фасадов</div></div>{content}<div class="foot"><span>Коммерческое предложение · 15 октября 2026</span><span>FASAD FLOW / 0{number}</span></div></section>'

pages = [shell('''
<div class="pill">Для владельца производства и руководителя цеха</div>
<h1>Каждый заказ.<br>Каждая деталь.<br><em>Всё под контролем.</em></h1>
<p class="lead">От клиентского бланка до готовых фасадов: размеры, стоимость, карты раскроя, этапы и оплаты в одном рабочем процессе.</p>
<div class="dark"><div class="eyebrow">Один понятный маршрут заказа</div><div class="flow"><div><b>01 / МЕНЕДЖЕР</b>Бланк<br>и расчёт</div><div><b>02 / ТЕХНОЛОГ</b>Детали<br>и раскрой</div><div><b>03 / ЦЕХ</b>Очередь<br>и этапы</div><div><b>04 / ВЛАДЕЛЕЦ</b>Статус<br>и оплата</div></div></div>
<div class="grid"><div class="card"><div class="num">МЕНЕДЖЕРУ</div><h3>Меньше повторного ввода</h3><p>Импорт Excel-бланка и проверка размеров, количества, цвета и фрезеровки до передачи заказа дальше.</p></div><div class="card"><div class="num">ВЛАДЕЛЬЦУ</div><h3>Видно, что происходит</h3><p>Заказы, производственная очередь и оплаты доступны в понятных разделах вместо разрозненных записей.</p></div></div>
<div class="band"><p><strong>Начнём с вашего заказа.</strong> На бесплатном показе за 15 минут пройдём один обезличенный бланк и определим, что нужно именно вашему цеху.</p></div>
''',1),shell('''
<h2>Покажем весь путь.<br>На одном бланке.</h2>
<p class="lead">Вы оцениваете процесс на привычных размерах и материалах. Мы показываем, как данные проходят от заявки до производства.</p>
<div class="row"><div class="n">01</div><div><h3>Загрузить и проверить заказ</h3><p>Excel-бланк превращается в таблицу деталей. Размеры, количество, артикулы, толщина и цвет остаются перед глазами; одинаковые позиции объединяются.</p></div></div>
<div class="row"><div class="n">02</div><div><h3>Согласовать стоимость</h3><p>Справочник цен, площадь и состав заказа помогают подготовить смету и КП. Менеджер проверяет итог до согласования с клиентом.</p></div></div>
<div class="row"><div class="n">03</div><div><h3>Проверить раскрой</h3><p>Карты МДФ для одного заказа или партии, разделение материалов по цвету и толщине, ручная правка размещения и печать карт. Технолог проверяет результат.</p></div></div>
<div class="row"><div class="n">04</div><div><h3>Передать в цех и видеть этап</h3><p>Заказ попадает в производственную очередь. Материалы, текущая стадия и зарегистрированные оплаты связаны с заказом.</p></div></div>
<div class="dark"><div class="eyebrow">Отдельно покажем CAD</div><h3 style="margin-top:12px">Геометрия фасада прямо в демо</h3><p style="margin-bottom:0">Параметрические рамки и пазы, просмотр операций на деталях раскроя, экспорт SVG/DXF. Производственная подготовка для конкретного станка оценивается отдельно.</p></div>
<p class="note">Интерактивное демо хранит записи в браузере и знакомит с процессом. Рабочее внедрение, перенос данных и совместный доступ проверяются отдельно. Возможности локального демо и серверного пилота пока не объединены в один продукт.</p>
''',2),shell('''
<h2>Сначала проверяем.<br>Затем внедряем.</h2>
<p class="lead">Предлагаем 30-дневный пилот с согласованным сценарием и измеримыми критериями приёмки.</p>
<div class="grid" style="margin-top:23px"><div class="card"><div class="eyebrow">Небольшой цех</div><div class="price">4 900 ₽ <small>/ месяц</small></div><p>Ориентир для базового процесса: заявки, заказы, расчёт, карты и документы.</p></div><div class="card"><div class="eyebrow">Производство</div><div class="price">9 900 ₽ <small>/ месяц</small></div><p>Ориентир для расширенного процесса. Участки, роли и доступы фиксируем после показа.</p></div></div>
<p class="note" style="margin-top:10px">Предварительные ориентиры после приёмки. Стоимость пилота, настройки, переноса и поддержки согласуем отдельно до старта. Финальные условия фиксируем в договоре.</p>
<h3 style="margin-top:23px">Что считаем успешным результатом</h3>
<div class="check"><b>20 контрольных заказов</b>Размеры, количество, цвет, толщина, артикулы и суммы сверены с исходными бланками.</div>
<div class="check"><b>Проверка менеджером и технологом</b>Согласованный маршрут заказа проходит без потери данных; карты проверены на ваших материалах.</div>
<div class="check"><b>Доступы и восстановление</b>Права участников проверены; резервная копия восстановлена на отдельной тестовой установке.</div>
<p class="note" style="margin-top:14px">В базовый объём не входят промышленный G-код, интеграции с 1С и оборудованием, полная себестоимость и многопредприятийный SaaS. Экономию материала оцениваем на контрольных заказах.</p>
<div class="dark" style="margin-top:20px;padding:20px 24px"><div class="eyebrow">Следующий шаг / бесплатный показ</div><div class="cta">Пришлите один обезличенный<br>Excel-бланк вашего заказа.</div><p>В ответ на это письмо напишите «Показ Fasad». Согласуем 15 минут и разберём ваш рабочий сценарий.</p><a class="contact" href="mailto:koallalenivaa@gmail.com?subject=Показ%20Fasad">koallalenivaa@gmail.com</a><p style="font-size:11px;margin:8px 0 0">Калдин Лев · Fasad Flow</p></div>
<p class="note">Предложение для обсуждения пилота. Не является публичной офертой.</p>
''',3)]

def main():
    HTML.parent.mkdir(parents=True,exist_ok=True)
    PDF.parent.mkdir(parents=True,exist_ok=True)
    HTML.write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fasad Flow | Коммерческое предложение</title><style>'+CSS+'</style><body>'+''.join(pages)+'</body></html>',encoding='utf-8')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
        page=browser.new_page(viewport={'width':1000,'height':1200},device_scale_factor=1)
        page.goto(HTML.as_uri())
        page.emulate_media(media='print')
        for i, section in enumerate(page.locator('.page').all(),1):
            footer=section.locator('.foot').bounding_box()
            blocks=section.locator(':scope > *:not(.foot)').all()
            bottom=max(b.bounding_box()['y']+b.bounding_box()['height'] for b in blocks)
            assert bottom < footer['y']-8, f'Page {i} overlaps footer: {bottom} / {footer}'
        page.pdf(path=str(PDF),prefer_css_page_size=True,print_background=True)
        preview=ROOT/'tmp/pdfs';preview.mkdir(parents=True,exist_ok=True)
        for i,section in enumerate(page.locator('.page').all(),1):
            section.screenshot(path=str(preview/f'offer-{i}.png'))
        browser.close()
    print(PDF)

if __name__=='__main__': main()
