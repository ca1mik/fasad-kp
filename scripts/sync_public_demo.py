"""Refresh the sanitized, offline sales demo without touching outreach data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "demo"
TARGET = ROOT / "sales" / "russia" / "demo-public"
ARCHIVE = ROOT / "sales" / "russia" / "demo-public.zip"


def sanitize_app(source: str) -> str:
    start, marker, end = source.partition("const PRODUCTION_STAGES=")
    if not marker:
        raise ValueError("Seed data boundary not found; review anonymization")
    contacts = {}
    names = re.findall(r'(?:client|name):"([^"]+)"', start.split("workers:")[0])
    for name in dict.fromkeys(names):
        contacts[name] = f"Тестовый заказчик {len(contacts)+1:02d}"
    for name, replacement in contacts.items():
        start = start.replace('"' + name + '"', '"' + replacement + '"')
    start = re.sub(r'phone:"[^"]*"', 'phone:"Тестовый контакт"', start)
    counter = [0]

    def email_repl(_match):
        counter[0] += 1
        return f'email:"demo-{counter[0]:02d}@example.invalid"'

    start = re.sub(r'email:"[^"]*"', email_repl, start)
    start = re.sub(r'address:"[^"]*"', 'address:"Тестовый адрес"', start)
    workers = start.split("workers:")[1].split("stock:")[0]
    for index, name in enumerate(re.findall(r'name:"([^"]+)"', workers), 1):
        start = start.replace('"' + name + '"', f'"Тестовый сотрудник {index:02d}"')
    for index, name in enumerate(dict.fromkeys(re.findall(r'manager:"([^"]+)"', start)), 1):
        start = start.replace('"' + name + '"', f'"Тестовый менеджер {index:02d}"')
    result = (start + marker + end).replace("fasad-demo-data", "fasad-public-test-v1")
    return result


def sanitize_index(source: str) -> str:
    result = source.replace("Интерактивная демо-версия", "Демо · только тестовые данные · суммы условные")
    result = result.replace("Фасад Профи", "Тестовый цех").replace("Алексей Ковалёв", "Тестовый пользователь")
    csp = ("<meta name=\"robots\" content=\"noindex,nofollow\">\n"
           "  <meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self'; "
           "script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
           "connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'\">")
    return result.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n  ' + csp, 1)


def sync_public_demo() -> Path:
    TARGET.mkdir(parents=True, exist_ok=True)
    index = sanitize_index((SOURCE / "index.html").read_text(encoding="utf-8"))
    app = sanitize_app((SOURCE / "app.js").read_text(encoding="utf-8"))
    scripts = re.findall(r'<script src="([^"]+)"', index)
    assets = ["styles.css", "favicon.svg", *scripts]
    for name in assets:
        source = SOURCE / name
        if not source.is_file() or source.resolve().is_relative_to(SOURCE.resolve()) is False:
            raise ValueError(f"Missing or unsafe demo asset: {name}")
    for name in assets:
        output = TARGET / name
        output.parent.mkdir(parents=True, exist_ok=True)
        if name == "app.js":
            output.write_text(app, encoding="utf-8")
        else:
            shutil.copyfile(SOURCE / name, output)
    (TARGET / "index.html").write_text(index, encoding="utf-8")
    for name in ("README.md", "LICENSE.sheetjs.txt"):
        shutil.copyfile(SOURCE / "vendor" / name, TARGET / "vendor" / name)
    (TARGET / "README.txt").write_text(
        "FASAD: статическое демо только с тестовыми данными.\n"
        "Изменения хранятся в браузере. Не вводите персональные или рабочие данные.\n"
        "Импорт Excel читается локально и не загружает файл на сервер.\n"
        "JSON для ЧПУ — черновик, не программа станка.\n", encoding="utf-8")
    files = sorted(path for path in TARGET.rglob("*") if path.is_file() and path.name != "manifest.json")
    manifest = {path.relative_to(TARGET).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    (TARGET / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with ZipFile(ARCHIVE, "w", ZIP_DEFLATED) as archive:
        for path in sorted(path for path in TARGET.rglob("*") if path.is_file()):
            archive.write(path, path.relative_to(TARGET).as_posix())
    return TARGET


if __name__ == "__main__":
    print(sync_public_demo())
