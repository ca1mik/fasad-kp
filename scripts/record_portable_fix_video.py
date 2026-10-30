"""Record the address and article fix in the actual Fasad Portable UI.

Run while the preview services are available on ports 13001 and 8000.
The script edits only the temporary preview database.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import time

import edge_tts
from pydub import AudioSegment
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "portable_fix_video_work"
OUTPUT = ROOT / "demo" / "fasad-portable-address-article-fixed.mp4"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
BASE = "http://127.0.0.1:13001"
LEAD = "104ccd0f-ecc2-40e5-b184-924efc3399a4"
ORDER = "333f1cd9-4743-41c6-9f4b-0079fd684009"
LINES = [
    "Открываю сохранённую заявку. Адрес и артикул здесь ещё не заполнены.",
    "В карточке заявки указываю адрес доставки и артикул детали. Сохраняю изменения.",
    "Открываю карту раскроя заказа. Теперь адрес и артикул видны прямо на ней.",
]


async def speak(text: str, path: Path) -> None:
    await edge_tts.Communicate(text, voice="ru-RU-SvetlanaNeural", rate="+0%").save(str(path))


def caption(page, text: str) -> None:
    page.evaluate(
        """text => {
          let box = document.getElementById('demo-caption');
          if (!box) {
            box = document.createElement('div');
            box.id = 'demo-caption';
            box.style.cssText = 'position:fixed;z-index:99999;left:24px;bottom:24px;'
              + 'padding:12px 18px;border-radius:12px;background:#111827;'
              + 'color:white;font:600 18px/1.25 Arial,sans-serif;'
              + 'box-shadow:0 8px 25px #0005;pointer-events:none';
            document.body.append(box);
          }
          box.textContent = text;
        }""",
        text,
    )


def main() -> None:
    assert WORK.resolve().is_relative_to((ROOT / "data").resolve())
    WORK.mkdir(parents=True, exist_ok=True)
    voice_paths = [WORK / f"line-{i}.mp3" for i in range(len(LINES))]
    for line, path in zip(LINES, voice_paths):
        asyncio.run(speak(line, path))
        if path.stat().st_size < 1000:
            raise RuntimeError(f"Speech is empty: {path}")
    voices = [AudioSegment.from_file(path).fade_in(100).fade_out(160) for path in voice_paths]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(EDGE), headless=True)
        seed = browser.new_context(locale="ru-RU")
        login = seed.new_page()
        login.goto(f"{BASE}/login")
        login.locator("input[name=login]").fill("admin")
        login.locator("input[name=password]").fill("preview-demo-2026")
        login.locator("button[type=submit]").click()
        login.wait_for_url("**/dashboard")
        state = seed.storage_state()
        seed.close()

        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
            storage_state=state,
            record_video_dir=str(WORK),
            record_video_size={"width": 1440, "height": 900},
            reduced_motion="reduce",
        )
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{BASE}/leads/{LEAD}")
        page.get_by_role("button", name="Изменить заявку").wait_for()
        cues: list[tuple[int, AudioSegment]] = []
        started = time.monotonic()

        def scene(index: int, title: str, action=None) -> None:
            caption(page, title)
            cue = int((time.monotonic() - started) * 1000)
            cues.append((cue, voices[index]))
            if action:
                action()
            spent = int((time.monotonic() - started) * 1000) - cue
            page.wait_for_timeout(max(900, max(len(voices[index]) + 900, 6000) - spent))

        scene(0, "Заявка до правки")

        def edit() -> None:
            page.get_by_role("button", name="Изменить заявку").click()
            page.get_by_placeholder("куда везти именно этот заказ").wait_for()
            page.wait_for_timeout(1200)
            address = page.get_by_placeholder("куда везти именно этот заказ")
            address.fill("")
            address.press_sequentially("Москва, Лесная улица, 5", delay=30)
            article = page.locator("label").filter(has_text="Позиция 1").locator("input")
            article.fill("")
            article.press_sequentially("ART-2026", delay=70)
            page.wait_for_timeout(1700)
            page.get_by_role("button", name="Сохранить", exact=True).click()
            page.get_by_role("button", name="Изменить заявку").wait_for()

        scene(1, "Адрес и артикул в программе", edit)

        def show_map() -> None:
            page.goto(f"{BASE}/leads/{LEAD}/cutting?orderId={ORDER}")
            page.locator("body").get_by_text("ART-2026").first.wait_for()
            page.evaluate("document.body.style.zoom='1.2'")
            caption(page, "Адрес и артикул на карте раскроя")
            body = page.locator("body").inner_text()
            if "Москва, Лесная улица, 5" not in body or "ART-2026" not in body:
                raise RuntimeError("Address or article missing from the actual Portable cutting map")

        scene(2, "Адрес и артикул на карте раскроя", show_map)
        if errors:
            raise RuntimeError("Browser errors: " + "; ".join(errors))
        raw = Path(page.video.path())
        elapsed = int((time.monotonic() - started) * 1000)
        context.close()
        browser.close()

    narration = AudioSegment.silent(duration=elapsed + 500)
    for cue, voice in cues:
        narration = narration.overlay(voice, position=cue + 300)
    wave = WORK / "narration.wav"
    narration.export(wave, format="wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(raw), "-i", str(wave),
            "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart", str(OUTPUT),
        ],
        check=True,
        capture_output=True,
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
