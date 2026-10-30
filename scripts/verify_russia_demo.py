"""Exercise the sanitized browser demo locally; no publication or messaging."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
demo=ROOT/'sales/russia/demo-public'
data_dir=ROOT/'data/russia-outreach'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];outbound=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:outbound.append(r.url) if r.url.startswith(('http:','https:')) else None)
    page.goto((demo/'index.html').as_uri())
    page.wait_for_selector('#app h1')
    assert page.locator('body').inner_text().casefold().find('тестовые данные')>=0
    contacts=page.evaluate('data.clients.map(c => ({name:c.name,email:c.email,phone:c.phone,address:c.address}))')
    assert all(c['email'].endswith('@example.invalid') or c['email']=='—' for c in contacts)
    assert all(c['phone']=='Тестовый контакт' or c['phone']=='—' for c in contacts)
    for route in ['clients','orders','cutting','production','stock','reports']:
        page.locator(f'#nav button[data-route="{route}"]').click()
        page.wait_for_timeout(80)
        assert page.locator('#app').inner_text().strip()
        if route=='cutting':page.screenshot(path=str(data_dir/'demo-cutting-preview.png'),full_page=True)
    assert not errors and not outbound
    result={'routes_checked':['workspace','clients','orders','cutting','production','stock','reports'],
            'contacts_checked':len(contacts),'browser_errors':errors,'external_requests':outbound,'publication_performed':False}
    (data_dir/'demo-browser-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
    print(json.dumps(result,ensure_ascii=False))
