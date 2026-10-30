"""Build a new static release from an explicit allowlist; never read databases."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'demo'
TARGET=ROOT/'release'/'fasad-kp-public'

def build():
    index=(SOURCE/'index.html').read_text(encoding='utf-8')
    index=index.replace('<script src="app.js">','<script src="public_boot.js"></script>\n  <script src="app.js">').replace('</body>','<script src="public_demo.js"></script>\n</body>')
    index=index.replace('Алексей Ковалёв','Тестовый пользователь').replace('Фасад Профи','Демонстрационный цех')
    csp="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    index=index.replace('<meta charset="utf-8">','<meta charset="utf-8">\n<meta name="description" content="Интерактивное демо FASAD КП: заявки, раскрой, карты PDF, смета и просмотр ЧПУ на вымышленных данных.">\n<meta http-equiv="Content-Security-Policy" content="'+csp+'">')
    names=['index.html','styles.css','favicon.svg',*re.findall(r'<script src="([^"]+)"',index),'vendor/README.md','vendor/LICENSE.sheetjs.txt']
    allowed=set(names)|{'manifest.json','README.txt','start-demo.cmd','_headers'}
    TARGET.mkdir(parents=True,exist_ok=True)
    unexpected=[str(p.relative_to(TARGET)) for p in TARGET.rglob('*') if p.is_file() and p.relative_to(TARGET).as_posix() not in allowed]
    if unexpected:raise ValueError('Unexpected files in public output; refusing publication: '+str(unexpected))
    for name in names:
        if name=='index.html':content=index.encode('utf-8')
        else:
            path=(SOURCE/name).resolve()
            if not path.is_relative_to(SOURCE.resolve()):raise ValueError('Unsafe asset path')
            content=path.read_bytes()
            if path.suffix in {'.js','.css'}:
                text=content.decode('utf-8')
                text=text.replace('fasad-demo-data','fasad-public-test-v2').replace('fasad-demo-clean-v2','fasad-public-clean-v2').replace('fasad-demo-backup-','fasad-public-backup-').replace('fasad:lead-draft:v1:','fasad:public-lead-draft:v1:').replace('mail@example.ru','demo@example.invalid')
                if name=='app.js':
                    text=re.sub(r'name:"(?:Сергей Мельников|Роман Ильин|Павел Егоров|Ирина Лебедева|Денис Котов|Артём Волков)"','name:"Тестовый сотрудник"',text)
                    text=text.replace('Анна Белова','Тестовый менеджер 1').replace('Ольга Миронова','Тестовый менеджер 2')
                if name=='kp_core.js':text=re.sub(r'const DEMO_(CLIENTS|LEADS|ORDERS|STOCK) = .*?;',r'const DEMO_\1 = {};',text)
                content=text.encode('utf-8')
        output=TARGET/name;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(content)
    (TARGET/'README.txt').write_text('FASAD КП — публичное статическое демо\n\nВсе примеры вымышлены. Ввод изолирован в браузере посетителя; серверной базы нет.\nНе вводите реальные контакты. Черновики остаются в текущем браузере.\n\nЛокально: start-demo.cmd или python -m http.server 8790 --bind 127.0.0.1\nОткрыть http://127.0.0.1:8790/ (не открывать index.html через file://).\n\nПубликация: загрузить содержимое этой папки на статический HTTPS-хостинг.\nКорневой документ index.html; маршруты через # не требуют серверного роутинга.\nНужны все JS, CSS и папка vendor. Сервер Python/CRM, базы, .env не публиковать.\n_headers — готовые заголовки для совместимых статических хостингов.\n\nPDF скачивается со всеми картами; SVG содержит все карты одним документом.\nЧПУ: только просмотр и черновой JSON, не программа станка.\nСброс демо удаляет только данные этого публичного демо.\n',encoding='utf-8')
    (TARGET/'start-demo.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\necho Open http://127.0.0.1:8790/\r\npython -m http.server 8790 --bind 127.0.0.1\r\n',encoding='ascii')
    (TARGET/'_headers').write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n  Cache-Control: no-cache\n',encoding='utf-8')
    files=sorted(p for p in TARGET.rglob('*') if p.is_file() and p.name!='manifest.json')
    manifest={p.relative_to(TARGET).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (TARGET/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with ZipFile(TARGET.parent/'fasad-kp-public.zip','w',ZIP_DEFLATED) as archive:
        for p in sorted(TARGET.rglob('*')):
            if p.is_file():archive.write(p,p.relative_to(TARGET).as_posix())
    return TARGET

if __name__=='__main__':print(build())
