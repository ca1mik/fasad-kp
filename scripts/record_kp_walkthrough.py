"""Record a short, reproducible walkthrough of the local Fasad Flow demo."""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
OUTPUT = ROOT / "demo" / "fasad-flow-kp-walkthrough.mp4"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def caption(page, text: str, seconds: float = 2.2) -> None:
    page.evaluate(
        """text => {
          let box = document.querySelector('#recording-caption');
          if (!box) {
            box = document.createElement('div');
            box.id = 'recording-caption';
            box.style.cssText = 'position:fixed;z-index:99999;right:24px;bottom:22px;'
              + 'max-width:560px;padding:15px 22px;border-radius:14px;'
              + 'background:#172033;color:white;font:600 20px/1.3 Arial,sans-serif;'
              + 'box-shadow:0 8px 28px #0005;pointer-events:none';
            document.body.appendChild(box);
          }
          box.textContent = text;
        }""",
        text,
    )
    page.wait_for_timeout(int(seconds * 1000))


def main() -> None:
    if not EDGE.exists():
        raise RuntimeError(f"Microsoft Edge is missing: {EDGE}")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required")

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(DEMO))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="fasad-video-") as temp_dir:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(EDGE), headless=True, slow_mo=120)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    record_video_dir=temp_dir,
                    record_video_size={"width": 1280, "height": 800},
                    locale="ru-RU",
                    reduced_motion="reduce",
                )
                page = context.new_page()
                page.set_default_timeout(7000)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/#price-book")
                caption(page, "Fasad Flow · КП из актуального справочника цен", 2.5)

                page.get_by_role("button", name="Добавить запись").click()
                form = page.locator("#priceItemForm")
                for name, value in {
                    "article": "FF-101", "name": "Фасад МДФ эмаль", "kind": "Эмаль",
                    "unit": "м²", "price": "2500",
                }.items():
                    form.locator(f'[name="{name}"]').fill(value)
                caption(page, "1. Добавляем позицию: 2 500 ₽ за м²", 2.0)
                page.get_by_role("button", name="Сохранить запись").click()
                caption(page, "Справочник готов для новых предложений", 2.0)

                page.goto(f"http://127.0.0.1:{server.server_port}/#clients")
                page.locator('[data-action="new-client"]').click()
                page.locator('#newClientForm [name="name"]').fill("Демо клиент")
                page.locator("[data-modal-save]").click()
                client_id = page.url.split("/")[-1]
                page.get_by_role("button", name="Пополнить депозит").click()
                page.locator('#depositForm [name="amount"]').fill("1000")
                page.locator("[data-modal-save]").click()
                caption(page, "2. У клиента отдельный депозит: 1 000 ₽", 2.4)

                page.goto(f"http://127.0.0.1:{server.server_port}/#quotes")
                caption(page, "3. Создаём КП без заказа и предоплаты", 2.2)
                page.locator('[data-quote="new"]').click()
                quote = page.locator("#newQuoteForm")
                quote.locator('[name="clientId"]').select_option(client_id)
                quote.locator('[name="title"]').fill("Фасады для кухни")
                line = quote.locator(".quote-line-card").first
                line.locator('[name="priceItemId"]').select_option(label="FF-101 · Фасад МДФ эмаль · 2 500 ₽/м²")
                line.locator('[name="qty"]').fill("4")
                line.locator('[name="height"]').fill("700")
                line.locator('[name="width"]').fill("400")
                assert re.sub(r"\D", "", quote.locator("#quoteDraftTotal").inner_text()) == "2800"
                caption(page, "4 детали × 0,7 × 0,4 м × 2 500 ₽ = 2 800 ₽", 3.0)
                page.locator("[data-modal-save]").click()
                assert "2 800" in re.sub(r"\s+", " ", page.locator("#app").inner_text()), repr(page.locator("#app").inner_text())
                caption(page, "4. Готовое КП: 2 800 ₽ · доступна печать", 3.2)

                page.goto(f"http://127.0.0.1:{server.server_port}/#price-book")
                page.get_by_role("button", name="Изменить запись").click()
                page.locator('#priceItemForm [name="price"]').fill("3000")
                page.get_by_role("button", name="Сохранить запись").click()
                caption(page, "5. Меняем цену в справочнике на 3 000 ₽", 2.4)
                page.goto(f"http://127.0.0.1:{server.server_port}/#quotes")
                page.locator("[data-quote-open]").first.click()
                assert "2 800" in re.sub(r"\s+", " ", page.locator("#app").inner_text()), repr(page.locator("#app").inner_text())
                caption(page, "Созданное КП сохраняет согласованную цену", 3.2)
                page.goto(f"http://127.0.0.1:{server.server_port}/#clients/{client_id}")
                caption(page, "Депозит остаётся отдельно от суммы КП", 2.8)

                if errors:
                    raise RuntimeError("Browser errors: " + "; ".join(errors))
                video = page.video
                context.close()
                browser.close()
                raw = Path(video.path())

            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                 "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUTPUT)],
                check=True,
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print(OUTPUT)


if __name__ == "__main__":
    main()
