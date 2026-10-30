from __future__ import annotations
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
import threading
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from openpyxl import Workbook
from pypdf import PdfReader
from playwright.sync_api import sync_playwright
from scripts.build_public_demo import build
from tests.test_crm_portal import EDGE

OUTPUT=Path(__file__).resolve().parents[1]/'output'/'playwright'

@pytest.fixture
def public_url():
    folder=build()
    handler=functools.partial(SimpleHTTPRequestHandler,directory=str(folder))
    server=ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown();server.server_close();thread.join()

def test_public_artifact_has_only_static_allowlisted_files():
    folder=build()
    import json,hashlib
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    assert set(manifest)|{'manifest.json'}=={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    for name,digest in manifest.items():
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest
        assert not any(token in name.lower() for token in ['.env','sqlite','backup','workspace_server','crm_backend'])
    with ZipFile(folder.parent/'fasad-kp-public.zip') as archive:
        assert set(archive.namelist())==set(manifest)|{'manifest.json'}
    app=(folder/'app.js').read_text(encoding='utf-8')
    assert 'fasad-demo-data' not in app
    assert 'Анна Белова' not in app

def test_public_exports_every_mdf_and_film_map_even_after_filter(public_url,tmp_path):
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(EDGE),headless=True)
        page=browser.new_page(viewport={'width':1600,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(public_url)
        page.locator('#publicExample').select_option('1003-П')
        page.locator('[data-action=open-cutting]').first.click()
        for mode in ['mdf','film']:
            page.locator('#cuttingMaterialMode').select_option(mode)
            page.wait_for_function('(mode)=>currentCuttingOrder().materialSpec.mode===mode || mode==="mdf"&&currentCuttingOrder().materialSpec.mode!=="film"',arg=mode)
            expected=page.evaluate('calculateOrderNesting(currentCuttingOrder()).sheets.length')
            pieces=page.evaluate('calculateOrderNesting(currentCuttingOrder()).sheets.reduce((n,s)=>n+s.placements.length,0)')
            assert expected==5
            assert pieces==page.evaluate('orderPartCount(data.orders.find(o=>o.id==="1003-П"))')==5
            if mode=='film':page.locator('#filmColorFilter').select_option('Демо: графит')
            with page.expect_download() as info:page.locator('[data-cut-export=svg]').click()
            svg=ET.fromstring(info.value.path().read_bytes())
            assert sum('layout-piece' in n.attrib.get('class','').split() for n in svg.iter())==pieces
            text=' '.join(n.text or '' for n in svg.iter())
            for i in range(1,expected+1):assert f'Лист {i} из {expected}' in text
            with page.expect_download() as info:page.locator('[data-cut-export=pdf]').click()
            path=tmp_path/(mode+'.pdf');info.value.save_as(path)
            pdf=PdfReader(path);assert len(pdf.pages)==expected
            assert all(len(sheet.images)==1 for sheet in pdf.pages)
            printed=PdfReader(BytesIO(page.pdf(print_background=True)))
            assert len(printed.pages)==expected
            for i,sheet in enumerate(printed.pages,1):assert f'Лист {i}' in sheet.extract_text()
        OUTPUT.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(OUTPUT/'public-film.png'),full_page=True)
        assert not errors,errors
        browser.close()

def test_public_mobile_import_inheritance_edit_reload_reset_and_isolation(public_url):
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(EDGE),headless=True)
        context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=2)
        page=context.new_page();page.set_default_timeout(7000)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(public_url)
        assert page.locator('#ordersBadge').inner_text()=='5'
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert page.locator('.topbar').bounding_box()['y']>=page.locator('.demo-ribbon').bounding_box()['height']-1
        form=page.locator('#leadForm')
        for name,value in {'client':'Посетитель А','subject':'Проверка','leadNumber':'0088'}.items():form.locator(f'[name={name}]').fill(value)
        book=Workbook();ws=book.active;ws.append(['Длина','Ширина','Количество','Толщина','Артикул','Фрезеровка','Цвет'])
        ws.append([700,400,2,19,'110','Рамка','Белый'])
        for i in range(130):ws.append([200+i,180,1,None,None,None,None])
        ws.append([700,400,3,None,None,None,None]);ws.append([700,400,1,None,None,'—','Серый'])
        stream=BytesIO();book.save(stream)
        page.locator('#importExcelFile').set_input_files({'name':'demo.xlsx','mimeType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','buffer':stream.getvalue()})
        page.wait_for_function('document.querySelectorAll("#leadPartsList .lead-part-card").length===132')
        cards=form.locator('.lead-part-card')
        assert cards.first.locator('[name=partQty]').input_value()=='5'
        assert cards.nth(1).locator('[name=partArticle]').input_value()=='110'
        assert cards.nth(1).locator('[name=partMilling]').input_value()=='Рамка'
        assert cards.last.locator('[name=partColor]').input_value()=='Серый'
        assert cards.last.locator('[name=partMilling]').input_value()==''
        page.reload();form=page.locator('#leadForm');assert form.locator('[name=leadNumber]').input_value()=='0088'
        form.locator('[data-submit-mode=lead]').click()
        assert page.evaluate('data.leads[0].id')=='0088-Э'
        assert page.evaluate('orderPartCount(data.leads[0])')==136
        page.goto(public_url+'/#leads/0088-%D0%AD');page.locator('[data-action=edit-lead]').click()
        page.locator('#editLeadForm [name=subject]').fill('Изменённый пример')
        page.locator('[data-modal-save]').click();page.reload()
        assert page.get_by_role('heading',name='Изменённый пример').count()==1
        second=browser.new_context().new_page();second.goto(public_url)
        assert second.evaluate('data.leads.length')==0
        assert second.locator('#ordersBadge').inner_text()=='5'
        page.on('dialog',lambda d:d.accept());page.locator('#publicReset').click();page.locator('#publicExample').wait_for()
        assert page.evaluate('data.leads.length')==0
        assert page.locator('#ordersBadge').inner_text()=='5'
        page.goto(public_url+'/#workspace')
        page.locator('#leadForm [name=client]').fill('Незавершённый ввод перед сбросом')
        page.locator('#publicReset').click();page.locator('#publicExample').wait_for()
        page.goto(public_url+'/#workspace')
        assert page.locator('#leadForm [name=client]').input_value()==''
        OUTPUT.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(OUTPUT/'public-mobile.png'),full_page=True)
        assert not errors,errors
        browser.close()

def test_public_cnc_example_is_explicitly_a_preview(public_url):
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(EDGE),headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(public_url)
        page.locator('[data-action=load-cad-sample]').click()
        page.locator('#cadPreview svg').first.wait_for()
        page.locator('[data-action=cad-demo-settings]').click()
        page.locator('[data-action=cad-cam-preview]').click()
        assert 'Программа станка не создана' in page.locator('#cadCamStatus').inner_text()
        page.locator('.cad-raw-result summary').click()
        import json
        preview=json.loads(page.locator('#cadCamResult').inner_text())
        assert preview['previewOnly'] is True
        assert len(preview['operations'])==1
        assert 'не проверены' in preview['warnings'][0]
        page.locator('[data-action=cad-save]').click();page.reload()
        assert page.locator('#cadPreview svg').count()>0
        OUTPUT.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(OUTPUT/'public-cnc.png'),full_page=True)
        assert not errors,errors
        browser.close()

def test_editing_cutting_updates_price_and_deleting_film_updates_source(public_url):
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(EDGE),headless=True)
        page=browser.new_page();page.goto(public_url+'/#cutting/1001-%D0%AD')
        page.locator('[data-part-field=qty]').first.fill('7')
        state=page.evaluate('({amount:data.orders[0].amount,estimate:partsEstimate(data.orders[0].parts)})')
        assert state['amount']==state['estimate']==6912
        page.locator('#cuttingMaterialMode').select_option('film')
        page.locator('#partsList .part-row button').last.click()
        page.reload()
        assert page.locator('#partsList .part-row').count()==1
        assert page.evaluate('data.orders[0].parts.length')==1
        assert page.evaluate('data.orders[0].amount')==6048
        assert page.evaluate('calculateOrderNesting(currentCuttingOrder()).parts')==7
        browser.close()
