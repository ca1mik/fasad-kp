from pathlib import Path
import json

import pytest

from tests.test_crm_portal import portal, PASSWORD, EDGE

sync_playwright = pytest.importorskip('playwright.sync_api').sync_playwright


def sign_in(page, url):
    page.goto(url + '/work/#clients')
    page.locator('#workspaceLogin [name=username]').fill('owner')
    page.locator('#workspaceLogin [name=password]').fill(PASSWORD)
    page.locator('#workspaceLogin button').click()
    page.locator('#workspaceExport').wait_for()


def add_client(page, name):
    page.locator('[data-action="new-client"]').click()
    page.locator('#newClientForm [name=name]').fill(name)
    page.locator('[data-modal-save]').click()


def test_two_sessions_shared_clients_cad_and_conflict(portal):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(EDGE), headless=True)
        ca, cb = browser.new_context(), browser.new_context()
        a, b = ca.new_page(), cb.new_page()
        errors = []
        a.on('pageerror', lambda error: errors.append(str(error)))
        b.on('pageerror', lambda error: errors.append(str(error)))
        sign_in(a, portal)
        sign_in(b, portal)
        add_client(a, 'Общий заказчик')
        a.wait_for_function("document.querySelector('#serverStatus').textContent.includes('версия 1')")
        b.reload()
        b.get_by_text('Общий заказчик', exact=True).first.wait_for()
        b.locator('#workspaceExport').wait_for()
        # CAD sample exercises a full order, model geometry, and cross-session persistence.
        a.evaluate('loadCadSample()')
        a.wait_for_function("document.querySelector('#serverStatus').textContent.includes('версия 2')")
        saved = a.evaluate('JSON.parse(JSON.stringify(data))')
        assert saved['orders'][0]['parts'][0]['cadModel']
        # B still has revision 1: its write must never erase A's CAD order.
        add_client(b, 'Конфликтующий заказчик')
        b.get_by_role('heading', name='Сохранение остановлено').wait_for()
        with b.expect_download() as download:
            b.locator('#saveCopy').click()
        assert download.value.suggested_filename.endswith('.json')
        current = a.evaluate("fetch('/api/workspace').then(r=>r.json())")
        assert current['revision'] == 2
        assert current['data'] == saved
        assert len(current['data']['clients']) == 2  # shared client + sample client
        a.reload()
        a.locator('#workspaceExport').wait_for()
        assert a.evaluate('data.orders[0].parts[0].cadModel') == saved['orders'][0]['parts'][0]['cadModel']
        assert not errors, errors
        browser.close()


def test_browser_import_and_failed_save_keep_source(portal):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(EDGE), headless=True)
        page = browser.new_page()
        sign_in(page, portal)
        payload = page.evaluate('JSON.parse(JSON.stringify(data))')
        payload['clients'] = [{'id': 'C-7', 'name': 'Перенесённый клиент', 'initials': 'ПК'}]
        page.on('dialog', lambda dialog: dialog.accept())
        with page.expect_file_chooser() as chooser:
            page.locator('#workspaceImport').click()
        chooser.value.set_files({'name': 'source.json', 'mimeType': 'application/json',
                                 'buffer': json.dumps(payload, ensure_ascii=False).encode('utf-8')})
        page.get_by_text('Перенесённый клиент', exact=True).first.wait_for()
        assert page.locator('#workspaceImport').count() == 0
        page.route('**/api/workspace', lambda route: route.abort() if route.request.method == 'PUT' else route.continue_())
        add_client(page, 'Не потерять при обрыве')
        page.get_by_role('heading', name='Сохранение остановлено').wait_for()
        assert page.evaluate('data.clients.some(c=>c.name==="Не потерять при обрыве")')
        current = page.evaluate("fetch('/api/workspace').then(r=>r.json())")
        assert current['revision'] == 1
        assert len(current['data']['clients']) == 1
        with page.expect_download() as downloaded:
            page.locator('#saveCopy').click()
        assert downloaded.value.failure() is None
        browser.close()


def test_new_installation_can_add_real_production_worker(portal):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(EDGE), headless=True)
        page = browser.new_page()
        sign_in(page, portal)
        page.locator('#nav [data-route=workers]').click()
        assert page.locator('.worker-card').count() == 0
        page.get_by_role('button', name='Добавить работника').click()
        page.locator('#workerForm [name=name]').fill('Иван Технолог')
        page.locator('#workerForm [name=role]').fill('Технолог')
        page.locator('[data-modal-save]').click()
        page.wait_for_function("document.querySelector('#serverStatus').textContent.includes('версия 1')")
        page.reload()
        page.get_by_text('Иван Технолог', exact=True).wait_for()
        assert page.evaluate('data.workers.length') == 1
        browser.close()


def test_order_reopens_when_url_already_contains_its_id(portal):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(EDGE), headless=True)
        page = browser.new_page()
        page.set_default_timeout(7000)
        errors=[]
        page.on('pageerror',lambda error: errors.append(str(error)))
        sign_in(page,portal)
        page.evaluate('loadCadSample()')
        page.wait_for_function("document.querySelector('#serverStatus').textContent.includes('версия 1')")
        order_id=page.evaluate('data.orders[0].id')
        page.locator('#nav [data-route=orders]').click()
        # Same state as the reported screenshot: list visible, detail URL set.
        page.evaluate('(id)=>history.replaceState(null,"",location.pathname+location.search+"#orders/"+id)',order_id)
        page.locator('#ordersBody [data-order]').first.get_by_role('button',name='Открыть').click()
        page.locator('.order-hero').wait_for()
        assert page.locator('.order-hero h1').inner_text()==order_id
        page.reload()
        page.locator('.order-hero').wait_for()
        page.locator('[data-action=open-cutting]').first.click()
        page.locator('#openManualEditor').click()
        page.locator('.layout-editor').wait_for()
        page.locator('[data-edit=close]').click()
        page.go_back()
        page.locator('.order-hero').wait_for()
        assert not errors,errors
        browser.close()
