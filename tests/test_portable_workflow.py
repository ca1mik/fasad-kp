import json
from pathlib import Path

from tests.test_kp_demo import demo_url, page


def sample(page, url):
    page.goto(url + '/#workspace')
    page.locator('[data-action="load-cad-sample"]').click()
    page.locator('#cadPreview svg').first.wait_for()
    page.locator('[data-action="cad-back"]').click()
    page.locator('[data-action="open-cutting"]').first.click()


def test_price_unit_and_deadline_choices(demo_url, page):
    page, errors = page
    page.goto(demo_url + '/#workspace')
    card = page.locator('#leadPartsList .lead-part-card').first
    card.locator('.lead-part-options summary').click()
    for name, value in {'partName': 'Фасад', 'partHeight': '720', 'partWidth': '400', 'partQty': '2', 'partPrice': '1000'}.items():
        card.locator(f'[name={name}]').fill(value)
    card.locator('[name=partUnit]').select_option('м²')
    assert '576' in page.locator('#leadPartsTotal').inner_text()
    assert card.locator('.part-price-label').inner_text() == 'Цена за м², ₽'
    part = page.evaluate("partsFromForm(document.querySelector('#leadForm'),'TEST')[0]")
    assert part['unit'] == 'м²'
    assert part['grain'] is False
    card.locator('[name=partGrain]').check()
    assert page.evaluate("partsFromForm(document.querySelector('#leadForm'),'TEST')[0].grain") is True
    card.locator('[name=partUnit]').select_option('шт')
    assert '2\u00a0000' in page.locator('#leadPartsTotal').inner_text()
    page.locator('#leadForm [data-due-preset]').select_option('7w')
    due = page.locator('#leadForm [name=due]').input_value()
    assert due == page.evaluate('FasadDeadline.deadline(7,true)')
    assert page.evaluate("FasadDeadline.deadline(1,true,new Date(2026,9,16))") == '2026-10-19'
    page.locator('#leadForm [name=due]').fill('0045-01-04')
    assert not page.locator('#leadForm [name=due]').evaluate('(input)=>input.checkValidity()')


def test_editor_rotation_new_sheet_undo_and_persistence(demo_url, page):
    page, errors = page
    page.set_viewport_size({'width': 1500, 'height': 1000})
    sample(page, demo_url)
    assert page.locator('#cuttingMaps .sheet-svg').first.bounding_box()['width'] > 500
    page.locator('#openManualEditor').click()
    editor = page.locator('.layout-editor')
    assert editor.bounding_box()['width'] > 1400
    page.screenshot(path=str(Path(__file__).resolve().parents[1] / 'tmp/manual-editor-final.png'))
    movable = editor.locator('.layout-piece[data-layout-key*="-P2#1"]')
    movable.click()
    before = movable.get_attribute('data-rotated')
    count = editor.locator('.editor-sheet').count()
    original_sheet = int(movable.get_attribute('data-sheet-index'))
    editor.locator('[data-edit=add]').click()
    assert editor.locator('.editor-sheet').count() == count + 1
    editor.locator('#editorSheet').select_option(str(count))
    editor.locator('#editorX').fill('100')
    editor.locator('#editorY').fill('100')
    editor.locator('[data-edit=apply]').click()
    editor.locator('[data-edit=rotate]').click()
    assert editor.locator('.layout-piece[data-layout-key*="-P2#1"]').get_attribute('data-rotated') != before
    editor.locator('[data-edit=undo]').click()
    assert editor.locator('.layout-piece[data-layout-key*="-P2#1"]').get_attribute('data-rotated') == before
    editor.locator('[data-edit=redo]').click()
    editor.locator('[data-edit=save]').click()
    assert page.locator('.layout-editor').count() == 0
    saved = page.evaluate('data.orders.find(o=>o.demo).manualLayout')
    assert saved['sheets'] == [{'templateIndex': original_sheet}]
    placement = next(p for key, p in saved['positions'].items() if '-P2#1' in key)
    assert placement['sheetIndex'] == count
    page.reload()
    assert page.locator('#cuttingMaps .cut-sheet-card').count() == count + 1
    assert page.evaluate('data.orders.find(o=>o.demo).manualLayout') == saved


def test_editor_texture_bounds_and_cancel(demo_url, page):
    page, errors = page
    sample(page, demo_url)
    page.locator('#sheetFormatPreset').select_option('2440x1220')
    assert page.evaluate('data.orders.find(o=>o.demo).materialSpec.sheetWidth') == 2440
    assert page.evaluate('data.orders.find(o=>o.demo).materialSpec.margin') == 8
    page.locator('#openManualEditor').click()
    editor = page.locator('.layout-editor')
    editor.locator('.layout-piece[data-layout-key*="-P1#1"]').click()
    editor.locator('[data-edit=rotate]').click()
    assert 'Поворот запрещён' in editor.locator('.editor-status').inner_text()
    editor.locator('#editorX').fill('-1')
    editor.locator('[data-edit=apply]').click()
    assert editor.locator('.editor-status').get_attribute('class').endswith('error')
    editor.locator('[data-edit=close]').click()
    assert page.locator('.layout-editor').count() == 0
    assert page.evaluate('data.orders.find(o=>o.demo).manualLayout || null') is None


def test_drag_between_compatible_sheets_and_invalid_drop(demo_url, page):
    page, errors = page
    page.set_viewport_size({'width': 1600, 'height': 1500})
    sample(page, demo_url)
    page.locator('#openManualEditor').click()
    editor = page.locator('.layout-editor')
    piece = editor.locator('.layout-piece[data-layout-key*="-P2#1"]')
    piece.click()
    count = editor.locator('.editor-sheet').count()
    editor.locator('[data-edit=add]').click()
    editor.locator('#editorZoom').fill('40')
    editor.locator('.editor-scroll').evaluate('(el)=>el.scrollTop=0')
    source = piece.locator('rect.piece').bounding_box()
    target = editor.locator('svg[data-editor-sheet]').nth(count).bounding_box()
    pw=float(piece.locator('rect.piece').get_attribute('width'))
    ph=float(piece.locator('rect.piece').get_attribute('height'))
    x, y = source['x']+source['width']/2, source['y']+source['height']/2
    page.mouse.move(x,y)
    page.mouse.down()
    page.mouse.move(target['x']+target['width']*(100+pw/2)/2800,target['y']+target['height']*(100+ph/2)/2070,steps=12)
    assert editor.locator('.editor-ghost').count() == 1
    assert 'invalid' not in editor.locator('.editor-ghost').get_attribute('class'), editor.locator('.editor-status').inner_text()
    page.mouse.up()
    assert int(piece.get_attribute('data-sheet-index')) == count
    old_x = piece.get_attribute('data-x')
    source = piece.locator('rect.piece').bounding_box()
    page.mouse.move(source['x']+source['width']/2,source['y']+source['height']/2)
    page.mouse.down()
    page.mouse.move(target['x']+1,target['y']+1,steps=8)
    assert 'invalid' in editor.locator('.editor-ghost').get_attribute('class')
    page.mouse.up()
    assert piece.get_attribute('data-x') == old_x
    editor.locator('[data-edit=save]').click()
