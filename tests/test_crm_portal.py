from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from crm_backend.api import create_app
from crm_backend.store import Store


sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
PASSWORD = "correct horse battery staple"


@pytest.fixture
def portal(tmp_path):
    store = Store(tmp_path / "crm")
    store.create_user("owner", PASSWORD, "admin")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(tmp_path / "crm"), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(.05)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_admin_to_dealer_to_confirmed_order_in_browser(portal):
    if not EDGE.exists():
        pytest.skip("Microsoft Edge not found")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(EDGE), headless=True)
        page = browser.new_page()
        page.set_default_timeout(7000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(portal)
        page.locator('#login [name="username"]').fill("owner")
        page.locator('#login [name="password"]').fill(PASSWORD)
        page.locator('#login button').click()
        page.get_by_role("heading", name="Фасад Профи").wait_for()

        page.get_by_role("button", name="Прайс").click()
        price = page.locator('#priceForm')
        for field, value in {"article":"Арт.110","name":"Фасад","kind":"Фрезеровка","rub":"1200"}.items():
            price.locator(f'[name="{field}"]').fill(value)
        price.locator('[name="unit"]').select_option("м²")
        price.get_by_role("button", name="Сохранить").click()
        page.get_by_text("110", exact=True).wait_for()

        page.get_by_role("button", name="Дилеры").click()
        page.locator('#dealerForm [name="name"]').fill("Дилер А")
        page.locator('#dealerForm [name="discount"]').fill("10")
        with page.expect_response(lambda response: response.url.endswith('/api/dealers') and response.request.method == 'POST') as dealer_response:
            page.locator('#dealerForm button').click()
        assert dealer_response.value.status == 201
        page.locator('#dealerForm [name="name"]').wait_for()
        page.get_by_text("Дилер А", exact=True).first.wait_for()
        page.locator('#userForm [name="username"]').fill("dealer_a")
        page.locator('#userForm [name="password"]').fill(PASSWORD)
        page.locator('#userForm [name="dealer"]').select_option(label="Дилер А")
        with page.expect_response(lambda response: response.url.endswith('/api/users') and response.request.method == 'POST') as user_response:
            page.locator('#userForm button').click()
        assert user_response.value.status == 201
        page.wait_for_function("document.querySelector('#userForm [name=username]')?.value === ''")
        page.locator('#userForm [name="username"]').fill("worker")
        page.locator('#userForm [name="password"]').fill(PASSWORD)
        page.locator('#userForm [name="role"]').select_option("worker")
        with page.expect_response(lambda response: response.url.endswith('/api/users') and response.request.method == 'POST') as worker_response:
            page.locator('#userForm button').click()
        assert worker_response.value.status == 201
        page.wait_for_function("document.querySelector('#userForm [name=username]')?.value === ''")
        page.locator('#logout').click()

        page.locator('#login [name="username"]').fill("dealer_a")
        page.locator('#login [name="password"]').fill(PASSWORD)
        page.locator('#login button').click()
        page.get_by_role("heading", name="Фасад Профи").wait_for()
        page.get_by_role("button", name="Новый заказ").click()
        form = page.locator('#orderForm')
        form.locator('[name="client"]').fill("Кухня 1")
        first=form.locator('.part-grid').first
        first.locator('[name="item"]').select_option(index=1)
        first.locator('[name="length"]').fill("1000")
        first.locator('[name="width"]').fill("500")
        first.locator('[name="color"]').fill("Белый софт")
        first.locator('[name="milling"]').fill("110")
        form.get_by_role("button", name="Добавить строку").click()
        second=form.locator('.part-grid').nth(1)
        second.locator('[name="item"]').select_option(index=1)
        second.locator('[name="length"]').fill("1000")
        second.locator('[name="width"]').fill("500")
        form.get_by_role("button", name="Добавить строку").click()
        third=form.locator('.part-grid').nth(2)
        third.locator('[name="item"]').select_option(index=1)
        third.locator('[name="length"]').fill("800")
        third.locator('[name="width"]').fill("400")
        third.locator('[name="color"]').fill("Чёрный")
        form.get_by_role("button", name="Проверить расчёт").click()
        page.get_by_text("2 групп одинаковых").wait_for()
        form.get_by_role("button", name="Сохранить черновик").click()
        page.get_by_role("heading", name="F-000001 · Кухня 1").wait_for()
        assert page.locator('#orderDetail tbody tr').count()==3
        assert page.locator('#orderDetail tbody tr').nth(1).locator('td').nth(3).inner_text()=="Белый софт"
        assert page.locator('#orderDetail tbody tr').nth(2).locator('td').nth(3).inner_text()=="Чёрный"
        page.locator('[data-submit="F-000001"]').click()
        page.get_by_text("На проверке", exact=True).first.wait_for()
        page.locator('#logout').click()
        page.locator('#login [name="username"]').fill("owner")
        page.locator('#login [name="password"]').fill(PASSWORD)
        page.locator('#login button').click()
        page.locator('[data-confirm="F-000001"]').click()
        page.get_by_text("В производстве", exact=True).first.wait_for()
        page.locator('[data-view-order="F-000001"]').click()
        page.get_by_role("heading", name="Комплектность").wait_for()
        physical_id = page.locator('#productionDetail tbody tr').first.locator('td').first.inner_text()
        assert physical_id.startswith("F-000001-P")
        page.locator('#logout').click()
        page.locator('#login [name="username"]').fill("worker")
        page.locator('#login [name="password"]').fill(PASSWORD)
        page.locator('#login button').click()
        page.get_by_role("button", name="Детали / сканер").click()
        page.locator('#partLookup [name="partId"]').fill(physical_id)
        with page.expect_response(lambda response: response.url.endswith('/api/parts/' + physical_id)) as part_response:
            page.locator('#partLookup button').click()
        assert part_response.value.status == 200, part_response.value.text()
        page.locator('#partDetail h2').get_by_text(physical_id).wait_for()
        page.locator('[data-part-action="start"]').click()
        page.get_by_text("in_progress", exact=True).first.wait_for()
        page.locator('[data-part-action="complete"]').click()
        page.get_by_text("Фрезеровка ЧПУ", exact=True).first.wait_for()
        with page.expect_popup() as popup:
            page.locator('#partDetail a').click()
        qr_page = popup.value
        qr_page.wait_for_load_state()
        assert qr_page.locator('svg').count() == 1
        qr_page.close()
        assert not errors, errors
        browser.close()
