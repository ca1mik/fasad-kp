"""Record the real Fasad Portable lead/order/cutting workflow with Russian narration.

The script runs Portable against a temporary SQLite backup. It never writes to
the working Portable database. Requires the local Portable installation,
Microsoft Edge, Playwright, edge-tts, pydub, and ffmpeg.
"""

from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import date, timedelta
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from pydub import AudioSegment
from playwright.sync_api import sync_playwright
import edge_tts


ROOT = Path(__file__).resolve().parents[1]
PORTABLE = Path(r"H:\fasad-portable")
BACKEND = PORTABLE / "backend"
FRONTEND = PORTABLE / "frontend"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
OUTPUT = ROOT / "demo" / "fasad-portable-full-workflow-v2.mp4"
BASE_URL = "http://127.0.0.1:13001"

LINES = [
    ("От заявки до карты", "Создам заявку с адресом и артикулами, покажу карту раскроя и объединю два заказа в одну партию."),
    ("Ввод заявки", "Заполняю клиента и адрес доставки. В каждой строке указываю размер, количество, толщину, артикул, цвет и цену. Расчёт обновляется сразу."),
    ("Проверка заявки", "Заявка получила номер. Здесь остались исходные размеры, клиент, площадь и предварительная сумма. Теперь можно открыть печатную карту."),
    ("Печатная карта", "Вот что должно быть на карте: номер, заказчик, адрес и артикулы. Ниже размещение деталей на листе. Карту можно распечатать или сохранить."),
    ("Настройки раскроя", "В рабочем раскрое задаются размер листа, поля, зазоры, поворот деталей и способ укладки. Карта пересчитывается на экране."),
    ("Перевод в заказ", "Создаю заказ из заявки. Размеры и расчёт переходят без повторного ввода. Связь с клиентом и заявкой сохраняется."),
    ("Общая партия", "Выбираю два заказа. Их детали ложатся на общие листы; номер заказа подписан прямо на каждой детали."),
    ("Результат", "Итог: два заказа на общих листах. Видны заполнение, свободный остаток и потребность в материале."),
]


def free_port(port: int) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


def wait_url(url: str, timeout: float = 25) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.4)
    raise RuntimeError(f"Service did not start: {url}")


def prepare_db(path: Path) -> None:
    with closing(sqlite3.connect(BACKEND / "app.db")) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
        sys.path.insert(0, str(BACKEND))
        from app.core.security import hash_password

        target.execute(
            "UPDATE users SET password_hash=? WHERE login='admin'",
            (hash_password("portable-video-only"),),
        )
        target.commit()


def start_services(db: Path, storage: Path, logs: Path):
    free_port(8000)
    free_port(13001)
    backend_env = os.environ.copy()
    backend_env.update(
        DATABASE_URL=f"sqlite:///{db.as_posix()}",
        LICENSE_LOCK_ENABLED="false",
        LOCAL_STORAGE_PATH=str(storage),
        PYTHONIOENCODING="utf-8",
    )
    frontend_env = os.environ.copy()
    frontend_env.update(PORT="13001", HOSTNAME="127.0.0.1", API_URL="http://127.0.0.1:8000/api/v1")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    back_log = (logs / "backend.log").open("w", encoding="utf-8")
    front_log = (logs / "frontend.log").open("w", encoding="utf-8")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=BACKEND, env=backend_env, stdout=back_log, stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    frontend = subprocess.Popen(
        [str(PORTABLE / "node" / "node.exe"), "server.js"],
        cwd=FRONTEND, env=frontend_env, stdout=front_log, stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    try:
        wait_url("http://127.0.0.1:8000/health")
        wait_url(f"{BASE_URL}/login")
    except Exception:
        backend.terminate()
        frontend.terminate()
        raise
    return backend, frontend, back_log, front_log


async def make_voice(path: Path, script: str) -> None:
    for attempt in range(3):
        try:
            await edge_tts.Communicate(
                script, voice="ru-RU-SvetlanaNeural", rate="-3%"
            ).save(str(path))
            if path.stat().st_size > 1000:
                return
        except Exception:
            if attempt == 2:
                raise
        await asyncio.sleep(2 + attempt * 3)
    raise RuntimeError("The speech service returned no audio")


def voice_length(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def show_caption(page, title: str) -> None:
    page.evaluate(
        """title => {
          let box = document.getElementById('video-chapter');
          if (!box) {
            box = document.createElement('div');
            box.id = 'video-chapter';
            box.style.cssText = 'position:fixed;z-index:99999;right:24px;bottom:24px;'
              + 'padding:13px 20px;border-radius:14px;background:#111827;'
              + 'color:white;font:600 19px/1.2 Arial,sans-serif;'
              + 'box-shadow:0 8px 25px #0005;pointer-events:none';
            document.body.append(box);
          }
          box.textContent = title;
        }""",
        title,
    )


def login(page) -> None:
    page.goto(f"{BASE_URL}/login")
    page.locator("input[name=login]").fill("admin")
    page.locator("input[name=password]").fill("portable-video-only")
    page.locator("button[type=submit]").click()
    page.wait_for_url("**/dashboard")


def fill_part(row, length: str, width: str, quantity: str, price: str, article: str = "") -> None:
    for cell, value in ((1, length), (2, width), (3, quantity), (5, "16"), (8, price)):
        row.locator("td").nth(cell).locator("input").fill(value)
    if article:
        row.locator("td").nth(6).locator("input").fill(article)
        row.locator("td").nth(7).locator("input").fill("Белый глянец")


def create_lead(page, client: str, parts: list[tuple[str, str, str, str, str]]) -> str:
    page.goto(f"{BASE_URL}/manager")
    page.get_by_placeholder("Имя клиента").fill(client)
    page.get_by_placeholder("город, улица, дом — куда везти").fill("Нижний Новгород, улица Касьянова, 8")
    page.get_by_label("Срок датой").fill((date.today() + timedelta(days=14)).isoformat())
    page.locator("select").nth(1).select_option("enamel")
    for index, dimensions in enumerate(parts):
        if index:
            page.get_by_role("button", name="Добавить строку").click()
        fill_part(page.locator("table tbody tr").nth(index), *dimensions)
    page.get_by_role("button", name="Только заявка").click()
    page.wait_for_url("**/leads/*")
    return page.url


def run() -> None:
    if not EDGE.exists() or not PORTABLE.exists():
        raise RuntimeError("Microsoft Edge and H:\\fasad-portable are required")
    with tempfile.TemporaryDirectory(prefix="portable-video-", dir=ROOT / "data") as temp_name:
        temp = Path(temp_name).resolve()
        if not temp.is_relative_to((ROOT / "data").resolve()):
            raise RuntimeError("Temporary files escaped the workspace")
        prepare_db(temp / "video.db")
        voices = []
        for index, (_, script) in enumerate(LINES):
            voice = temp / f"voice-{index}.mp3"
            asyncio.run(make_voice(voice, script))
            voices.append(voice)
        durations = [voice_length(voice) for voice in voices]
        backend = frontend = None
        back_log = front_log = None
        try:
            backend, frontend, back_log, front_log = start_services(
                temp / "video.db", temp / "storage", temp
            )
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=str(EDGE), headless=True, slow_mo=100
                )
                seed = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ru-RU")
                seed_page = seed.new_page()
                login(seed_page)
                create_lead(seed_page, "Клиент для партии", [("620", "360", "3", "2100", "FAS-003")])
                seed_page.get_by_role("button", name="Создать заказ").click()
                seed_page.wait_for_url("**/orders/*")
                state = seed.storage_state()
                seed.close()

                context = browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    record_video_dir=str(temp),
                    record_video_size={"width": 1440, "height": 900},
                    storage_state=state,
                    locale="ru-RU",
                    reduced_motion="reduce",
                )
                page = context.new_page()
                page.set_default_timeout(10000)
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"{BASE_URL}/manager")
                started = time.monotonic()
                cues: list[tuple[int, Path]] = []

                def scene(index: int, action=None) -> None:
                    show_caption(page, LINES[index][0])
                    cue = int((time.monotonic() - started) * 1000)
                    cues.append((cue, voices[index]))
                    if action:
                        action()
                    elapsed = (time.monotonic() - started) * 1000 - cue
                    page.wait_for_timeout(max(900, int(durations[index] * 1000 + 450 - elapsed)))

                scene(0)

                def fill_recorded_lead() -> None:
                    page.get_by_placeholder("Имя клиента").fill("Мебельная мастерская Демо")
                    page.get_by_placeholder("город, улица, дом — куда везти").fill("Нижний Новгород, улица Ленина, 5")
                    page.get_by_label("Срок датой").fill((date.today() + timedelta(days=14)).isoformat())
                    page.locator("select").nth(1).select_option("enamel")
                    fill_part(page.locator("table tbody tr").first, "700", "400", "4", "2500", "FAS-001")
                    page.get_by_role("button", name="Добавить строку").click()
                    fill_part(page.locator("table tbody tr").nth(1), "500", "250", "2", "2300", "FAS-002")
                    page.locator("table tbody tr").last.scroll_into_view_if_needed()

                scene(1, fill_recorded_lead)

                def save_lead() -> None:
                    page.get_by_role("button", name="Только заявка").click()
                    page.wait_for_url("**/leads/*")

                scene(2, save_lead)
                lead_url = page.url

                def printed_map() -> None:
                    page.get_by_role("link", name="Карты раскроя").click()
                    page.wait_for_url("**/cutting")
                    page.evaluate("document.body.style.zoom = '1.4'")
                    content = " ".join(page.locator("svg.map-page text").all_text_contents())
                    due = (date.today() + timedelta(days=14)).strftime("%d.%m.%Y")
                    if "Ленина, 5" not in content or "FAS-001" not in content or due not in content:
                        raise RuntimeError("Address, article or due date missing from printable cutting map")

                scene(3, printed_map)

                def working_cutting() -> None:
                    page.goto(lead_url)
                    page.get_by_role("link", name="Открыть раскрой").click()
                    page.wait_for_url("**/film-cutting?*")
                    page.evaluate("window.scrollTo(0, 0)")

                scene(4, working_cutting)

                def convert_order() -> None:
                    page.goto(lead_url)
                    page.get_by_role("button", name="Создать заказ").click()
                    page.wait_for_url("**/orders/*")

                scene(5, convert_order)

                def batch_cutting() -> None:
                    page.goto(f"{BASE_URL}/cutting-batch")
                    page.get_by_role("checkbox", name="Отметить все показанные заказы").check()
                    assert page.get_by_role("checkbox", name="Отметить все показанные заказы").is_checked()

                scene(6, batch_cutting)

                def batch_map() -> None:
                    page.evaluate("window.scrollTo(0, 950)")

                scene(7, batch_map)
                functional_errors = [error for error in errors if "React error #418" not in error]
                if functional_errors:
                    raise RuntimeError("Browser errors: " + "; ".join(functional_errors))
                page.wait_for_timeout(1200)
                video = page.video
                context.close()
                browser.close()
                raw = Path(video.path())

            raw_duration = voice_length(raw)
            mixed = AudioSegment.silent(duration=int(raw_duration * 1000) + 200, frame_rate=44100)
            for cue, path in cues:
                voice = AudioSegment.from_file(path).fade_in(120).fade_out(170)
                mixed = mixed.overlay(voice, position=cue)
            audio_path = temp / "narration.wav"
            mixed.export(audio_path, format="wav")
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-i", str(audio_path),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    "-shortest", str(OUTPUT),
                ],
                check=True,
            )
            print(OUTPUT)
        finally:
            for process in (frontend, backend):
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            for log in (back_log, front_log):
                if log:
                    log.close()


if __name__ == "__main__":
    run()
