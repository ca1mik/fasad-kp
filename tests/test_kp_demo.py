from __future__ import annotations

import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright


DEMO = Path(__file__).resolve().parents[1] / "demo"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


@pytest.fixture
def demo_url():
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(DEMO))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def page():
    if not EDGE.exists():
        pytest.skip("Browser UI tests require Microsoft Edge at the configured path")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(EDGE), headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(5000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page, errors
        assert not errors, errors
        browser.close()


def test_catalog_quote_and_deposit_ui(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#price-book")
    assert page.locator("#ordersBadge").inner_text() == "0"
    page.get_by_role("button", name="Добавить запись").click()
    form = page.locator("#priceItemForm")
    for name, value in {"article": "арт. 101", "name": "Фасад новый", "kind": "Эмаль", "unit": "шт", "price": "1200"}.items():
        form.locator(f'[name="{name}"]').fill(value)
    page.get_by_role("button", name="Сохранить запись").click()
    assert page.get_by_text("101", exact=True).count() >= 1
    page.get_by_role("button", name="Изменить запись").click()
    form.locator('[name="article"]').fill("арт. 102")
    form.locator('[name="price"]').fill("1500")
    page.get_by_role("button", name="Сохранить запись").click()
    assert page.get_by_text("102", exact=True).count() >= 1

    page.goto(f"{demo_url}/#clients")
    page.locator('[data-action="new-client"]').click()
    page.locator('#newClientForm [name="name"]').fill("Рабочий клиент")
    page.locator("[data-modal-save]").click()
    assert page.get_by_role("heading", name="Рабочий клиент").count() >= 1
    client_id = page.url.split("/")[-1]
    page.get_by_role("button", name="Пополнить депозит").click()
    page.locator('#depositForm [name="amount"]').fill("1000")
    page.locator("[data-modal-save]").click()
    assert page.get_by_text("1 000 ₽").count() >= 1
    page.get_by_role("button", name="Уменьшить депозит").click()
    page.locator('#depositForm [name="amount"]').fill("1100")
    page.locator('#depositForm [name="reason"]').fill("Ошибка")
    page.locator("[data-modal-save]").click()
    assert page.locator("#depositForm").count() == 1
    page.locator("[data-close]").first.click()

    page.get_by_role("button", name="Новый заказ", exact=False).last.click()
    row = page.locator("#newOrderForm .lead-part-card").first
    page.locator('#newOrderForm [name="orderNumber"]').fill("0015")
    page.locator('#newOrderForm [name="product"]').fill("Новый комплект")
    row.locator('[name="partHeight"]').fill("700")
    row.locator('[name="partWidth"]').fill("400")
    row.locator(".lead-part-options summary").click()
    row.locator('[name="catalogChoice"]').select_option(label="102 · Фасад новый")
    row.locator('[name="partColor"]').fill("Красный")
    row.locator('[name="partMilling"]').fill("Своя фрезеровка")
    row.get_by_role("button", name="Очистить всё").first.click()
    assert row.locator('[name="partColor"]').input_value() == ""
    row.locator('[name="partMilling"]').press("Enter")
    assert row.locator('[name="partMilling"]').input_value() == "Своя фрезеровка"
    assert row.locator('[name="partArticle"]').input_value() == "102"
    page.get_by_role("button", name="Нет оплаты").click()
    page.get_by_role("button", name="Создать заказ", exact=True).last.click()
    assert page.get_by_text("Оплат нет").count() >= 1
    order_id = page.locator(".order-id h1").inner_text()
    assert page.get_by_text("1 500 ₽").count() >= 1
    page.goto(f"{demo_url}/#price-book")
    page.get_by_role("button", name="Изменить запись").click()
    page.locator('#priceItemForm [name="price"]').fill("1700")
    page.locator('#priceItemForm [name="unit"]').fill("м²")
    page.get_by_role("button", name="Сохранить запись").click()
    page.goto(f"{demo_url}/#orders/{order_id}")
    assert page.get_by_text("1 500 ₽").count() >= 1
    page.get_by_role("button", name="Коммерческое предложение").click()
    assert page.get_by_text("1 500 ₽").count() >= 1
    assert "0 ₽" in page.get_by_text("Оплачено по заказу:").locator("..").inner_text()

    page.goto(f"{demo_url}/#orders/{order_id}")
    page.get_by_role("button", name="Добавить оплату").click()
    page.locator('#kpPaymentForm [name="amount"]').fill("400")
    page.locator('#kpPaymentForm [name="method"]').select_option("deposit")
    page.locator("[data-modal-save]").click()
    page.get_by_role("button", name="Удалить оплату").click()
    page.goto(f"{demo_url}/#clients/{client_id}")
    assert page.get_by_text("1 000 ₽").count() >= 1
    page.get_by_role("button", name="Уменьшить депозит").click()
    page.locator('#depositForm [name="amount"]').fill("100")
    page.locator('#depositForm [name="reason"]').fill("Исправление ошибки")
    page.locator("[data-modal-save]").click()
    assert page.get_by_text("900 ₽").count() >= 1


def test_browser_migration_backs_up_and_keeps_working_records(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#clients")
    page.evaluate("""() => {
      localStorage.removeItem('fasad-demo-clean-v2');
      localStorage.setItem('fasad-demo-data', JSON.stringify({
        clients:[{id:'C-101',name:'Мария Крылова',phone:'+7 920 000-24-18'}, {id:'C-999',name:'Рабочий клиент'}],
        leads:[], orders:[{id:'F-2000',clientId:'C-999',client:'Рабочий клиент',product:'Рабочий заказ',direction:'Эмаль',stage:'Расчёт',status:'Новый',amount:100,paid:0,due:'30.09.2026',parts:[{id:'p1',name:'Реальная деталь',height:700,width:400,qty:1,price:100}]}],
        stock:[], workers:[], priceItems:[], depositMovements:[]
      }));
    }""")
    page.reload()
    assert page.get_by_text("Рабочий клиент").count() >= 1
    assert page.get_by_text("Мария Крылова").count() == 0
    assert page.locator("#ordersBadge").inner_text() == "1"
    assert page.evaluate("Object.keys(localStorage).some(key => key.startsWith('fasad-demo-backup-'))")
    page.locator("#resetDemo").click()
    assert page.get_by_text("Рабочий клиент").count() >= 1


def test_new_row_inherits_machining_but_not_size_and_clear_buttons_work(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    first = page.locator("#leadForm .lead-part-card").first
    first.locator('[name="partColor"]').fill("Свой цвет")
    first.locator('[name="partMilling"]').fill("Свой рисунок")
    first.get_by_role("button", name="Очистить всё").first.click()
    first.get_by_role("button", name="Очистить всё").last.click()
    assert first.locator('[name="partColor"]').input_value() == ""
    assert first.locator('[name="partMilling"]').input_value() == ""
    first.locator('[name="partArticle"]').fill("МОЙ-АРТИКУЛ")
    first.locator('[name="partColor"]').fill("Белый софт")
    first.locator('[name="partMilling"]').fill("Рамка")
    first.locator('[name="partThickness"]').fill("19")
    first.locator('[name="partName"]').fill("Дверца")
    first.locator('[name="partHeight"]').fill("720")
    first.locator('[name="partWidth"]').fill("400")
    first.locator('[name="partArticle"]').press("Enter")
    assert first.locator('[name="partArticle"]').input_value() == "МОЙ-АРТИКУЛ"
    page.locator("#addLeadPart").click()
    second = page.locator("#leadForm .lead-part-card").last
    for name in ("partName", "partHeight", "partWidth", "partPrice"):
        assert second.locator(f'[name="{name}"]').input_value() == ""
    for name, value in {"partArticle":"МОЙ-АРТИКУЛ", "partColor":"Белый софт", "partMilling":"Рамка", "partThickness":"19"}.items():
        assert second.locator(f'[name="{name}"]').input_value() == value


def test_mobile_positions_do_not_multiply_and_details_expand(demo_url, page):
    page, _ = page
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{demo_url}/#workspace")
    cards = page.locator("#leadForm .lead-part-card")
    add = page.locator("#addLeadPart")
    assert cards.count() == 1
    assert cards.first.locator('[name="partArticle"]').is_visible()
    assert not cards.first.locator('[name="partPrice"]').is_visible()
    for _ in range(4):
        add.click()
    assert cards.count() == 1
    cards.first.locator('[name="partName"]').fill("Фасад")
    cards.first.locator('[name="partHeight"]').fill("720")
    cards.first.locator('[name="partWidth"]').fill("400")
    add.click()
    assert cards.count() == 2
    for _ in range(3):
        add.click()
    assert cards.count() == 2
    cards.last.locator(".lead-part-options summary").click()
    assert cards.last.locator('[name="partPrice"]').is_visible()


def test_manager_workspace_is_full_width_and_previous_position_collapses(demo_url, page):
    page, _ = page
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{demo_url}/#workspace")
    assert page.locator(".manager-workspace > .manager-form-panel").count() == 1
    assert page.locator(".manager-workspace > .manager-recent-panel").count() == 1
    assert page.locator("#app > .stats").count() == 0
    form_width = page.locator(".manager-form-panel").evaluate("el => el.getBoundingClientRect().width")
    workspace_width = page.locator(".manager-workspace").evaluate("el => el.getBoundingClientRect().width")
    assert form_width >= workspace_width - 2
    first = page.locator("#leadForm .lead-part-card").first
    first.locator('[name="partName"]').fill("Фасад")
    first.locator('[name="partHeight"]').fill("720")
    first.locator('[name="partWidth"]').fill("400")
    first.locator('[name="partColor"]').fill("Белый софт")
    page.locator("#addLeadPart").click()
    assert first.locator(".lead-part-summary").inner_text() == "Фасад · 720 × 400 мм · 1 шт. · Белый софт"
    assert not first.locator('[name="partHeight"]').is_visible()
    first.locator(".lead-part-collapse").click()
    assert first.locator('[name="partHeight"]').is_visible()


def test_new_request_opens_its_facade_drawing_and_machine_preview(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    form = page.locator("#leadForm")
    form.locator('[name="client"]').fill("Тестовый заказчик")
    form.locator('[name="subject"]').fill("Фасады для кухни")
    form.locator('[name="leadNumber"]').fill("0001")
    card = form.locator(".lead-part-card").first
    for name, value in {
        "partName": "Дверца", "partHeight": "720", "partWidth": "400",
        "partArticle": "Арт.110", "partColor": "Белый софт", "partMilling": "Рамка",
    }.items():
        card.locator(f'[name="{name}"]').fill(value)
    form.locator('[data-submit-mode="cad"]').click()
    assert "#cad/" in page.url
    page.locator("#cadPreview svg").first.wait_for()
    assert page.locator("#cadPreview svg").count() == 1
    assert page.locator("#cadMachine option").count() >= 2
    saved = page.evaluate("() => JSON.parse(localStorage.getItem('fasad-demo-data')).leads[0].parts[0]")
    assert (saved["article"], saved["color"], saved["milling"], saved["thickness"]) == (
        "Арт.110", "Белый софт", "Рамка", 16
    )
    assert page.evaluate("data.leads[0].id") == "0001-Э"


def test_dark_theme_and_example_orders_are_persistent_and_idempotent(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    page.locator("#themeToggle").click()
    assert page.locator("html").get_attribute("data-theme") == "dark"
    page.locator("#exampleOrders").click()
    page.locator("#ordersBody tr").first.wait_for()
    assert page.locator("#ordersBody tr").count() == 3
    page.locator("#exampleOrders").click()
    assert page.locator("#ordersBody tr").count() == 3
    records = page.evaluate("() => JSON.parse(localStorage.getItem('fasad-demo-data')).orders")
    assert len(records) == 3
    assert len(records[0]["parts"]) >= 3
    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "dark"
    assert page.locator("#ordersBody tr").count() == 3


def test_empty_stock_can_be_filled_for_cutting(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#stock")
    assert page.locator("#stockBody tr").count() == 0
    page.get_by_role("button", name="Добавить материал").click()
    page.locator('#kpStockForm [name="qty"]').fill("12")
    page.locator("[data-modal-save]").click()
    assert page.get_by_text("МДФ 16 мм").count() >= 1
    assert page.locator("#stockBody tr").count() == 1


def test_cnc_preview_requires_machine_and_keeps_selection(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    page.evaluate("""() => {
      localStorage.setItem('fasad-demo-clean-v2', '1');
      localStorage.setItem('fasad-demo-data', JSON.stringify({
        clients:[], leads:[], quotes:[], priceItems:[], depositMovements:[], stock:[], stockMovements:[],
        workers:[], orders:[{
          id:'F-TEST', client:'Test', product:'Facade', stage:PRODUCTION_STAGES[0], amount:0, paid:0,
          parts:[{id:'P-1',name:'Facade',height:700,width:400,qty:1,price:0}],
          materialSpec:{...MATERIAL_PRESETS[Object.keys(MATERIAL_PRESETS)[0]],kerf:4,margin:10}
        }]
      }));
    }""")
    page.reload()
    page.goto(f"{demo_url}/#cutting/F-TEST")
    page.locator('[data-action="download-cnc"]').last.click()
    assert page.get_by_text("Выберите станок для задания ЧПУ").count() >= 1

    page.locator("#cncMachineSelect").select_option("M-2")
    page.reload()
    assert page.locator("#cncMachineSelect").input_value() == "M-2"
    with page.expect_download() as download_info:
        page.locator('[data-action="download-cnc"]').last.click()
    download = download_info.value
    import json
    preview = json.loads(download.path().read_text(encoding="utf-8"))
    assert download.suggested_filename.endswith(".preview.json")
    assert preview["previewOnly"] is True
    assert preview["machine"]["id"] == "M-2"
    assert len(preview["sheets"]) == 1

    dialog_answers = iter(("Custom CNC", "Controller X"))
    page.on("dialog", lambda dialog: dialog.accept(next(dialog_answers)))
    page.locator('[data-action="add-cnc-machine"]').click()
    custom_id = page.locator("#cncMachineSelect").input_value()
    assert custom_id.startswith("M-")
    assert page.locator("#cncMachineSelect option:checked").inner_text() == "Custom CNC · Controller X"
    page.reload()
    assert page.locator("#cncMachineSelect").input_value() == custom_id


def test_factory_sheet_settings_apply_only_to_new_orders(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    page.evaluate("""() => {
      data.orders.push({
        id:'F-OLD', client:'Old client', product:'Old facade', stage:PRODUCTION_STAGES[0],
        status:'New', amount:0, paid:0, paidAmount:0,
        parts:[{id:'P-OLD',name:'Panel',height:700,width:400,qty:1,price:0}],
        materialSpec:FasadFactorySettings.snapshot(data.factorySettings, Object.keys(MATERIAL_PRESETS)[0])
      });
      saveData();
    }""")
    page.goto(f"{demo_url}/#settings")
    settings_form = page.locator("#factorySettingsForm")
    settings_form.locator('[name="companyName"]').fill("Factory A")
    settings_form.locator('[name="sheetWidth16"]').fill("2440")
    settings_form.locator('[name="sheetHeight16"]').fill("1220")
    settings_form.locator('[name="margin16"]').fill("8")
    settings_form.locator('[name="sheetWidth19"]').fill("1830")
    settings_form.get_by_role("button", name="Сохранить настройки").click()
    assert page.locator("#factoryName").inner_text() == "Factory A"
    page.reload()
    assert settings_form.locator('[name="sheetWidth16"]').input_value() == "2440"

    page.locator("#quickCreate").click()
    order_form = page.locator("#newOrderForm")
    order_form.locator('[name="client"]').fill("New client")
    order_form.locator('[name="orderNumber"]').fill("0016")
    order_form.locator('[name="product"]').fill("New facade")
    order_form.locator('[name="partName"]').first.fill("Panel")
    order_form.locator('[name="partHeight"]').first.fill("700")
    order_form.locator('[name="partWidth"]').first.fill("400")
    page.locator("#modalLayer [data-modal-save]").click()
    records = page.evaluate("JSON.parse(localStorage.getItem('fasad-demo-data')).orders")
    old = next(order for order in records if order["id"] == "F-OLD")
    new = next(order for order in records if order["product"] == "New facade")
    assert old["materialSpec"]["sheetWidth"] == 2800
    assert old["materialSpec"]["settingsVersion"] == 1
    assert new["materialSpec"]["sheetWidth"] == 2440
    assert new["materialSpec"]["sheetHeight"] == 1220
    assert new["materialSpec"]["settingsVersion"] == 2
    assert new["materialSpecs"]["19"]["sheetWidth"] == 1830
    assert new["materialSpecs"]["19"]["settingsVersion"] == 2


def test_worker_metrics_are_zero_without_production_reports(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#workers")
    cards = page.locator(".stats .stat")
    assert cards.nth(0).locator("strong").inner_text() == "6"
    for index in (1, 2, 3, 4):
        assert cards.nth(index).locator("strong").inner_text() == "0"
    page.locator('[data-action="worker-details"]').first.click()
    assert "0" in page.locator("#modalLayer").inner_text()


def test_standalone_quote_without_order_uses_catalog_snapshot(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#price-book")
    page.get_by_role("button", name="Добавить запись").click()
    form = page.locator("#priceItemForm")
    for name, value in {"article":"Q-1", "name":"Фасад для КП", "kind":"Эмаль", "unit":"м²", "price":"2000"}.items():
        form.locator(f'[name="{name}"]').fill(value)
    page.locator("[data-modal-save]").click()

    page.goto(f"{demo_url}/#quotes")
    page.locator('[data-quote="new"]').click()
    quote_form = page.locator("#newQuoteForm")
    quote_form.locator('[name="clientName"]').fill("Новый заказчик КП")
    quote_form.locator('[name="title"]').fill("Комплект фасадов")
    line = quote_form.locator(".quote-line-card").first
    line.locator('[name="priceItemId"]').select_option(label="Q-1 · Фасад для КП · 2 000 ₽/м²")
    line.locator('[name="qty"]').fill("2")
    line.locator('[name="height"]').fill("700")
    line.locator('[name="width"]').fill("400")
    assert "1 120 ₽" in quote_form.locator("#quoteDraftTotal").inner_text().replace("\u00a0", " ")
    page.locator("[data-modal-save]").click()
    quote_id = page.locator(".page-head h1").inner_text().split()[-1]
    assert page.locator("#ordersBadge").inner_text() == "0"
    assert page.get_by_text("1 120 ₽").count() >= 1
    assert page.evaluate("JSON.parse(localStorage.getItem('fasad-demo-data')).quotes.length") == 1

    page.goto(f"{demo_url}/#price-book")
    page.get_by_role("button", name="Изменить запись").click()
    page.locator('#priceItemForm [name="price"]').fill("2500")
    page.locator("[data-modal-save]").click()
    page.goto(f"{demo_url}/#quotes/{quote_id}")
    assert page.get_by_text("1 120 ₽").count() >= 1
    assert page.get_by_text("2 500 ₽").count() == 0


def test_cad_model_survives_reload_and_projects_on_cutting_sheet(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    page.evaluate("""() => {
      data.orders.push({
        id:'F-CAD', client:'CAD customer', product:'Facade', direction:'Эмаль',
        stage:'Расчёт', status:'Новый', amount:0, paid:0, paidAmount:0,
        parts:[{id:'P-CAD',name:'Door',height:700,width:400,thickness:16,qty:2,price:0,grain:false}],
        materialSpec:FasadFactorySettings.snapshot(data.factorySettings,Object.keys(MATERIAL_PRESETS)[0])
      });
      saveData();
    }""")
    page.goto(f"{demo_url}/#orders/F-CAD")
    page.locator('[data-action="open-cad"]').click()
    page.locator("#cadPreview .cad-outer").wait_for()
    page.locator("#cadTemplate").select_option("rounded_frame")
    page.locator("#cad-radius").fill("24")
    page.locator(".cad-toolbar-more summary").click()
    page.locator('[data-action="cad-undo"]').click()
    assert page.locator("#cad-radius").input_value() == "20"
    page.locator('[data-action="cad-redo"]').click()
    assert page.locator("#cad-radius").input_value() == "24"
    page.locator('[data-action="cad-grid"]').click()
    assert page.locator("#cadPreview #cadGrid").count() == 1
    page.locator('[data-action="cad-zoom-in"]').click()
    assert page.locator("#cadPreview svg").evaluate("node => node.style.width") == "125%"
    page.locator(".cad-advanced summary").click()
    page.locator("#cadHoles").fill('[{"x":100,"y":50,"radius":3,"depth":9}]')
    page.locator("#cadSave").click()
    page.reload()
    assert page.locator("#cadTemplate").input_value() == "rounded_frame"
    assert page.locator("#cadPreview .cad-milling").count() == 2
    assert page.evaluate("data.orders.find(o=>o.id==='F-CAD').parts[0].cadModel.params.radius") == 24
    page.locator("#cadMachine").select_option("M-1")
    page.locator(".cad-machine-more summary").click()
    for field, value in {"cadToolId":"T3", "cadToolDiameter":"6", "cadToolLength":"20", "cadToolStep":"4", "cadWorkLength":"1000", "cadWorkWidth":"600", "cadWorkZ":"100", "cadSafeZ":"10"}.items():
        page.locator(f"#{field}").fill(value)
    page.locator('[data-action="cad-cam-preview"]').click()
    page.locator(".cad-raw-result summary").click()
    assert "3" in page.locator("#cadCamResult").inner_text()
    assert "previewOnly" in page.locator("#cadCamResult").inner_text()
    page.locator(".cad-toolbar-more summary").click()
    with page.expect_download() as download_info:
        page.locator('[data-action="cad-dxf"]').click()
    dxf = download_info.value.path().read_text(encoding="utf-8")
    assert "$INSUNITS\n70\n4" in dxf
    assert "MILLING" in dxf
    page.locator('[data-action="cad-back"]').click()
    page.locator('[data-action="open-cutting"]').first.click()
    assert page.locator("#cuttingMaps .cad-overlay .cad-milling").count() == 4
    page.locator("#cutOverlayMode").select_option("operations")
    assert page.locator("#cuttingMaps .cad-overlay").count() == 2
    page.locator("#cutOverlayMode").select_option("none")
    assert page.locator("#cuttingMaps .cad-overlay").count() == 0


def test_two_different_cad_facades_keep_kerf_gap_on_one_sheet(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    page.evaluate("""() => {
      data.orders.push({id:'F-MIX',client:'Mixed',product:'Facades',direction:'Enamel',
        stage:PRODUCTION_STAGES[0],status:'New',amount:0,paid:0,
        parts:[
          {id:'P-1',name:'Frame',height:700,width:400,thickness:16,qty:1,grain:false,cadModel:{template:'frame'}},
          {id:'P-2',name:'Grooves',height:500,width:300,thickness:16,qty:1,grain:false,cadModel:{template:'vertical_grooves',params:{grooveCount:2,grooveSpacing:80}}}
        ],materialSpec:FasadFactorySettings.snapshot(data.factorySettings,Object.keys(MATERIAL_PRESETS)[0])});saveData();
    }""")
    page.goto(f"{demo_url}/#cutting/F-MIX")
    page.locator("#cuttingMaps .cad-overlay").first.wait_for()
    assert page.locator("#cuttingMaps .cad-overlay").count() == 2
    assert page.locator("#cuttingMaps .cad-milling").count() == 4
    placements = page.evaluate("""() => {
      const o=data.orders.find(item=>item.id==='F-MIX');
      const result=calculateNesting(o.parts,o.materialSpec);
      return {kerf:o.materialSpec.kerf,sheets:result.sheets.map(sheet=>sheet.placements)};
    }""")
    assert len(placements["sheets"]) == 1
    a, b = placements["sheets"][0]
    gap = placements["kerf"]
    assert (a["x"] + a["placedWidth"] + gap <= b["x"] or
            b["x"] + b["placedWidth"] + gap <= a["x"] or
            a["y"] + a["placedHeight"] + gap <= b["y"] or
            b["y"] + b["placedHeight"] + gap <= a["y"])


def test_public_demo_can_load_and_remove_cad_sample(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    page.locator('[data-action="load-cad-sample"]').click()
    page.locator("#cadPreview svg").first.wait_for()
    assert page.locator("#cadMachine option").count() >= 2
    page.locator('[data-action="cad-back"]').click()
    page.locator('[data-action="open-cad"]').first.wait_for()
    assert "Образец фасадов для CAD" in page.locator(".order-hero").inner_text()
    page.locator('[data-action="open-cutting"]').first.click()
    page.locator("#cuttingMaps .cad-overlay").first.wait_for()
    assert page.locator("#cuttingMaps .cad-overlay").count() == 3
    page.evaluate("""() => {data=normalizeData(FasadKP.cleanDemo(data));saveData()}""")
    assert page.evaluate("data.orders.length") == 0


def test_cad_demo_link_opens_drawing_without_prior_data(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#cad-demo")
    page.locator("#cadPreview svg").first.wait_for()
    assert "#cad/" in page.url
    assert page.locator("#cadMachine option").count() >= 2
    page.reload()
    page.locator("#cadPreview svg").first.wait_for()
    assert page.evaluate("data.orders.filter(order => order.sampleKey === 'cad-v1').length") == 1
    page.goto(f"{demo_url}/#workspace")
    page.goto(f"{demo_url}/#cad-demo")
    page.locator("#cadPreview svg").first.wait_for()
    assert page.evaluate("data.orders.filter(order => order.sampleKey === 'cad-v1').length") == 1


def test_cad_simple_hole_and_demo_machine_preview(demo_url, page):
    page, _ = page
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{demo_url}/#cad-demo")
    page.locator("#cadPreview svg").first.wait_for()
    assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
    assert not page.locator("#cadBackPreview").is_visible()
    page.locator('[data-action="cad-add-hole"]').click()
    assert page.locator("#cadHoleList .cad-hole-row").count() == 1
    page.locator('[data-action="cad-demo-settings"]').click()
    page.locator('[data-action="cad-cam-preview"]').click()
    assert "Проверено: 1 отверстий" in page.locator("#cadCamStatus").inner_text()
    assert '"previewOnly": true' in page.locator("#cadCamResult").text_content()
    page.locator("#cadSave").click()
    page.reload()
    assert page.locator("#cadHoleList .cad-hole-row").count() == 1


def test_manual_rotation_persists_and_cnc_preview_uses_same_coordinates(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    page.locator('[data-action="load-cad-sample"]').click()
    page.locator("#cadPreview svg").first.wait_for()
    page.locator('[data-action="cad-back"]').click()
    page.locator('[data-action="open-cutting"]').first.click()
    piece = page.locator('#cuttingMaps .layout-piece[data-layout-key*="-P2#1"]')
    piece.click()
    original_rotation = piece.get_attribute("data-rotated")
    page.locator('[data-action="rotate-piece"]').click()
    assert piece.get_attribute("data-rotated") != original_rotation
    state = page.evaluate("""() => data.orders.find(order=>order.demo).manualLayout""")
    assert state["positions"]
    page.reload()
    assert page.locator('#cuttingMaps .layout-piece[data-layout-key*="-P2#1"]').get_attribute("data-rotated") != original_rotation
    old_y = float(piece.get_attribute("data-y"))
    piece.scroll_into_view_if_needed()
    box = piece.locator("rect.piece").bounding_box()
    svg_box = page.locator("#cuttingMaps .sheet-svg").first.bounding_box()
    pixels = 100 * svg_box["width"] / 2800
    start_x, start_y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x, start_y + pixels, steps=5)
    page.mouse.up()
    assert float(piece.get_attribute("data-y")) >= old_y + 80
    page.locator("#cncMachineSelect").select_option("M-1")
    with page.expect_download() as download_info:
        page.locator('[data-action="download-cnc"]').last.click()
    import json
    preview = json.loads(download_info.value.path().read_text(encoding="utf-8"))
    rotated = [part for sheet in preview["sheets"] for part in sheet["parts"] if part["id"].endswith("-P2")]
    assert len(rotated) == 1
    assert rotated[0]["rotation"] == (90 if original_rotation == "false" else 0)
    assert rotated[0]["x"] == float(piece.get_attribute("data-x"))


def test_manual_lead_number_and_position_arrows(demo_url, page):
    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    form = page.locator("#leadForm")
    assert form.locator('[name="leadNumber"]').is_visible()
    assert form.locator('[name="leadNumber"]').get_attribute("required") is not None
    form.locator('[name="client"]').fill("Проверка")
    form.locator('[name="subject"]').fill("Фасады")
    form.locator('[name="direction"]').select_option("ПВХ")
    first = form.locator(".lead-part-card").first
    first.locator('[name="partName"]').fill("Дверца")
    first.locator('[name="partHeight"]').fill("700")
    first.locator('[name="partWidth"]').fill("400")
    first.locator('[name="partColor"]').fill("Белый софт")
    page.locator("#addLeadPart").click()
    first.locator(".lead-part-collapse").click()
    first.locator('[name="partColor"]').press("End")
    first.locator('[name="partColor"]').press("ArrowRight")
    assert page.evaluate("document.activeElement.name") == "partMilling"
    first.locator('[name="partHeight"]').press("ArrowDown")
    assert form.locator(".lead-part-card").last.locator('[name="partHeight"]').evaluate(
        "element => document.activeElement === element"
    )
    second = form.locator(".lead-part-card").last
    second.locator('[name="partName"]').fill("Вторая дверца")
    second.locator('[name="partHeight"]').fill("600")
    second.locator('[name="partWidth"]').fill("300")
    form.locator('[name="leadNumber"]').fill("0042")
    form.locator('[data-submit-mode="lead"]').click()
    assert page.evaluate("data.leads[0].id") == "0042-П"


def test_printed_cutting_pdf_contains_every_sheet(demo_url, page):
    from io import BytesIO
    from pypdf import PdfReader

    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    page.evaluate("""() => {
      const parts = Array.from({length:3}, (_, index) => ({
        id:`F-PRINT-P${index+1}`,name:`Большой фасад ${index+1}`,
        height:2700,width:1900,qty:1,grain:true,article:'110',color:'Белый софт',
        milling:'Рамка',thickness:16,price:0,unit:'шт'
      }));
      data.orders.push({id:'F-PRINT',client:'Тест',clientId:'C-PRINT',direction:'Эмаль',
        product:'Проверка карт',stage:'Расчёт',status:'Новый',parts,
        materialSpec:{name:'МДФ 16 мм',sheetWidth:2800,sheetHeight:2070,margin:10,kerf:4,price:0},
        amount:0,paid:0,paidAmount:0,payments:[],cuttingStatus:'draft'});
      saveData();
    }""")
    page.goto(f"{demo_url}/#cutting/F-PRINT")
    assert page.locator("#cuttingMaps .cut-sheet-card").count() == 3
    pdf = PdfReader(BytesIO(page.pdf(print_background=True)))
    assert len(pdf.pages) == 3
    for index, sheet in enumerate(pdf.pages, 1):
        assert f"Лист {index}" in sheet.extract_text()


def test_mixed_thickness_and_color_get_separate_maps_and_stock_reservations(demo_url, page):
    from io import BytesIO
    from pypdf import PdfReader

    page, _ = page
    page.goto(f"{demo_url}/#workspace")
    page.evaluate("""() => {
      const rows=[
        ['16','Белый софт'],['19','Белый софт'],['16','Эвкалипт'],['16','Белый софт']
      ];
      const parts=rows.map(([thickness,color],index)=>({id:`F-MIX-P${index+1}`,
        name:`Фасад ${index+1}`,height:700,width:400,qty:1,grain:true,
        thickness:Number(thickness),color,article:'110',milling:'Рамка',price:0,unit:'шт'}));
      data.orders.push({id:'F-MIX',client:'Тест',clientId:'C-MIX',direction:'Эмаль',
        product:'Смешанные материалы',stage:'Расчёт',status:'Новый',parts,
        materialSpec:{name:'МДФ 16 мм',stockName:'МДФ 16 мм',thickness:16,
          sheetWidth:2800,sheetHeight:2070,margin:10,kerf:4,price:0},
         materialSpecs:{19:{name:'МДФ 19 мм',stockName:'МДФ 19 мм',thickness:19,
           sheetWidth:1200,sheetHeight:1000,margin:10,kerf:4,price:0}},
        amount:0,paid:0,paidAmount:0,payments:[],cuttingStatus:'draft'});
      data.stock.push({name:'МДФ 16 мм',qty:10,reserved:0},{name:'МДФ 19 мм',qty:10,reserved:0});
      saveData();
    }""")
    page.goto(f"{demo_url}/#cutting/F-MIX")
    groups = page.evaluate("""() => calculateOrderNesting(data.orders[0]).sheets.map(sheet => ({
       key:sheet.materialKey,material:sheet.materialName,pieces:sheet.placements.length,
       width:sheet.spec.sheetWidth
    }))""")
    assert len(groups) == 3
    assert page.locator("#groupedParts summary").inner_text().endswith("3 групп")
    page.locator("#groupedParts summary").click()
    assert page.locator("#groupedParts tbody tr").count() == 3
    assert sorted(item["pieces"] for item in groups) == [1, 1, 2]
    assert next(item["width"] for item in groups if item["key"].startswith("19|")) == 1200
    assert "1200 × 1000" in page.locator("#cuttingMaps").inner_text()
    assert len(PdfReader(BytesIO(page.pdf(print_background=True))).pages) == 3
    page.locator("#releaseCutting").click()
    reserved = page.evaluate("""() => ({stock:data.stock.map(item=>[item.name,item.reserved]),
      plan:data.orders[0].reservedMaterials})""")
    assert reserved["stock"] == [["МДФ 16 мм", 2], ["МДФ 19 мм", 1]]
    assert sorted((item["materialName"], item["count"]) for item in reserved["plan"]) == [
        ("МДФ 16 мм", 2), ("МДФ 19 мм", 1)
    ]
    page.goto(f"{demo_url}/#cutting-batch")
    page.locator('.batch-order-check[value="F-MIX"]').check()
    assert page.locator(".batch-map-group .cut-sheet-card").count() == 3
    assert len(PdfReader(BytesIO(page.pdf(print_background=True))).pages) == 3


def test_excel_blank_import_fills_color_and_merges_distant_rows(demo_url, page):
    from io import BytesIO
    from openpyxl import Workbook

    page, _ = page
    book = Workbook()
    sheet = book.active
    sheet.append(["№", "Длина", "Ширина", "", "М2", "Мм", "Фрезеровка", "Цвет"])
    sheet.append([1, 700, 400, 2, None, 16, "Арт.110", "Белый софт"])
    for index in range(123):
        sheet.append([index + 2, 300 + index, 200, 1, None, 16, "Арт.128", None])
    sheet.append([125, 700, 400, 3, None, 16, "Арт.110", None])
    sheet.append([126, 700, 400, 1, None, 19, "Арт.110", "Эвкалипт"])
    buffer = BytesIO()
    book.save(buffer)
    page.goto(f"{demo_url}/#workspace")
    page.locator("#importExcelFile").set_input_files({
        "name": "blank.xlsx",
        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "buffer": buffer.getvalue(),
    })
    page.wait_for_function("document.querySelectorAll('#leadPartsList .lead-part-card').length === 125")
    cards = page.locator("#leadPartsList .lead-part-card")
    assert cards.first.locator('[name="partQty"]').input_value() == "5"
    assert cards.first.locator('[name="partColor"]').input_value() == "Белый софт"
    assert cards.first.locator('[name="partArticle"]').input_value() == "110"
    assert cards.last.locator('[name="partThickness"]').input_value() == "19"
    assert cards.last.locator('[name="partColor"]').input_value() == "Эвкалипт"
    page.locator('#leadForm [name="client"]').fill("Тестовый заказчик")
    page.locator('#leadForm [name="subject"]').fill("Фасады из бланка")
    page.locator('#leadForm [name="leadNumber"]').fill("0046")
    page.locator('#leadForm [data-submit-mode="lead"]').click()
    saved = page.evaluate("data.leads.find(item=>item.id==='0046-Э')")
    assert len(saved["parts"]) == 125
    assert saved["parts"][0]["qty"] == 5
    assert saved["parts"][-1]["color"] == "Эвкалипт"


def test_public_demo_package_loads_current_features_without_live_contacts(page):
    import hashlib
    import json
    from zipfile import ZipFile

    page, _ = page
    root = Path(__file__).resolve().parents[1] / "sales" / "russia"
    public = root / "demo-public"
    manifest = json.loads((public / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest.items():
        assert hashlib.sha256((public / name).read_bytes()).hexdigest() == digest
    with ZipFile(root / "demo-public.zip") as archive:
        assert set(archive.namelist()) == {*manifest, "manifest.json"}
    page.goto((public / "index.html").as_uri())
    assert page.locator("#importExcelFile").count() == 1
    assert page.locator("#themeToggle").count() == 1
    contacts = page.evaluate("data.clients.map(c=>({name:c.name,email:c.email,phone:c.phone}))")
    assert all(item["name"].startswith("Тестовый") for item in contacts)
    assert all(item["email"].endswith("@example.invalid") or item["email"] == "—" for item in contacts)
