"""Record a complete narrated sales tour of the actual Fasad Portable app.

Uses only data/portable_sales_video.db through the local preview services.
The working H:/fasad-portable/backend/app.db is never opened for writing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import re
import subprocess
import time

import edge_tts
from pydub import AudioSegment, effects
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "portable_sales_video_work"
DEMO_DB = ROOT / "data" / "portable_sales_video.db"
META = ROOT / "data" / "portable_sales_video_meta.json"
OUTPUT = ROOT / "demo" / "fasad-portable-full-sales.mp4"
SCRIPT_OUTPUT = ROOT / "demo" / "fasad-portable-full-sales-transcript.txt"
TIMELINE = WORK / "timeline.json"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
BASE = "http://127.0.0.1:13001"


@dataclass(frozen=True)
class Chapter:
    title: str
    subtitle: str
    speech: str


CHAPTERS = [
    Chapter("Весь заказ в одном окне", "Fasad Portable · демонстрационные данные",
            "Заявка, расчёт, раскрой, цех и деньги. В Фасад Портабл весь путь заказа собран в одной программе."),
    Chapter("Сводка для руководителя", "Заказы · заявки · выручка · загрузка цеха",
            "Руководитель сразу видит новые заявки, выручку, очередь производства и склад. Понятно, где нужна помощь прямо сейчас."),
    Chapter("Все обращения вместе", "Почта, мессенджеры, сайт и ручной ввод",
            "Обращения можно собирать в общую ленту. Менеджер видит контакт, источник, связанную заявку и историю разговора."),
    Chapter("Заявка за несколько минут", "Размеры, материал, артикул, срок и цена",
            "Принимаем новую заявку. Вводим клиента и адрес, размеры деталей, артикул, материал, срок и цену. Сумма считается прямо в форме."),
    Chapter("Ничего не теряется", "Карточка заявки и связь с клиентом",
            "После сохранения у заявки есть номер и карточка. Здесь остаются позиции, контакт клиента, срок и предварительная стоимость."),
    Chapter("Правки без переделки карты", "Адрес и артикул меняются в программе",
            "Если адрес или артикул уточнили позже, менеджер меняет их в самой заявке. Исправление доходит и до карты раскроя."),
    Chapter("Печатная карта раскроя", "Адрес · артикул · детали · PDF",
            "На печатной карте видны заказчик, адрес, артикул и размещение каждой детали. Карту можно сохранить в ПДФ и передать в цех."),
    Chapter("Раскрой отдельной заявки", "Лист, поля, пропил и поворот деталей",
            "В рабочем раскрое задаём формат листа, поля, пропил и поворот деталей. Раскладка и расход материала пересчитываются на экране."),
    Chapter("Понятный результат раскроя", "Карты листов и свободный остаток",
            "Каждый лист показан отдельно: где детали, сколько свободного места и какой остаток можно использовать дальше."),
    Chapter("Из заявки — в заказ", "Размеры и согласованная цена сохраняются",
            "Одним действием заявка становится заказом. Размеры и согласованная цена переходят без повторного ввода."),
    Chapter("Заказ под контролем", "Статус, срок, файлы и технологические действия",
            "В карточке заказа собраны смета, статус, срок, файлы клиента и действия для производства. Всё связано с конкретным заказом."),
    Chapter("Деньги рядом со сметой", "Аванс, доплата и остаток к оплате",
            "Авансы и доплаты видны рядом со сметой. Система показывает, сколько уже оплачено и сколько осталось получить."),
    Chapter("Файлы и подготовка цеха", "Бланк, экспорт раскроя и задание на ЧПУ",
            "Эскизы и замеры хранятся с заказом. Здесь же доступны бланк, экспорт раскроя и подготовка задания для ЧПУ."),
    Chapter("Раскрой партией", "Несколько заказов на общих листах",
            "Можно объединить несколько заказов в одну партию. Детали остаются подписанными по номерам заказов, а листы заполняются плотнее."),
    Chapter("Карта всей партии", "Заполнение листа и подписи деталей",
            "На карте партии видно, какие детали идут в один лист, сколько листов потребуется и какой остаток сохранится."),
    Chapter("Очередь производства", "Этап, участок и исполнитель",
            "После запуска маршрута заказ появляется в очереди цеха. Видны этап, участок, исполнитель и текущий статус работы."),
    Chapter("Прогресс по деталям", "Выполнено · осталось · брак",
            "Рабочий отмечает конкретные детали, брак и при необходимости добавляет фото. Руководитель видит фактический прогресс по заказу."),
    Chapter("Команда цеха", "Загрузка и отчёты работников",
            "У каждого сотрудника есть карточка с активными этапами и отчётами. Распределять задачи и проверять выполнение проще."),
    Chapter("Справочники материалов", "МДФ, кромка и фурнитура",
            "Материалы, кромка и фурнитура ведутся в справочниках. Их характеристики и цены используются при подготовке производства."),
    Chapter("Складские остатки", "Поступление, резерв и списание",
            "Склад показывает остатки, резерв и движения материала по заказам. Видно, что есть в наличии и что пора закупать."),
    Chapter("История клиента", "Заявки, заказы, контакты и расчёты",
            "В карточке клиента собраны контакты, заявки, заказы и расчёты. Историю сотрудничества не приходится искать по разным файлам."),
    Chapter("Отчёты и выгрузки", "Объём, деньги, площадь и направления",
            "Отчёты показывают объёмы, выручку, площадь фасадов и работу направлений. Данные можно выгрузить в Эксель или распечатать."),
    Chapter("Прайс под контролем", "История цены и сохранение старых договорённостей",
            "В справочнике цен живут артикулы и прайс. Новая цена не меняет сумму старого заказа: там остаётся согласованная с клиентом стоимость."),
    Chapter("Настройка под вашу команду", "Каналы, направления, роли и доступы",
            "Каналы связи, направления работ, сотрудники и права доступа настраиваются под ваш процесс. Каждый видит свою часть работы."),
    Chapter("От первого сообщения до отгрузки", "Fasad Portable · всё по заказу на одном экране",
            "Фасад Портабл помогает вести заказ от первого сообщения до отгрузки. Меньше ручного переноса, больше ясности для менеджера и цеха."),
]


async def make_voice(path: Path, speech: str, index: int) -> None:
    for attempt in range(4):
        try:
            # Small changes in pace keep the long narration conversational.
            rate = ["-1%", "+0%", "-2%", "+1%"][index % 4]
            await edge_tts.Communicate(
                speech, voice="ru-RU-SvetlanaNeural", rate=rate,
            ).save(str(path))
            if path.stat().st_size > 1000:
                return
        except Exception:
            if attempt == 3:
                raise
        await asyncio.sleep(2 + attempt * 2)
    raise RuntimeError(f"Voice service returned no audio for chapter {index}")


def overlay(page, chapter: Chapter, index: int, *, hero: bool = False) -> None:
    page.evaluate(
        """({title, subtitle, number, hero}) => {
          document.getElementById('sales-overlay')?.remove();
          const box = document.createElement('div');
          box.id = 'sales-overlay';
          box.style.cssText = hero
            ? 'position:fixed;inset:0;z-index:99999;pointer-events:none;'
              + 'background:linear-gradient(95deg,#0f172aee 0%,#0f172ae8 45%,#0f172a33 100%);'
              + 'display:flex;align-items:center;padding:8vw;color:white;font-family:Arial,sans-serif'
            : 'position:fixed;z-index:99999;left:28px;bottom:25px;pointer-events:none;'
              + 'max-width:660px;padding:14px 20px;border-radius:16px;'
              + 'background:#0f172aef;color:white;font-family:Arial,sans-serif;'
              + 'box-shadow:0 10px 28px #0005';
          const content = document.createElement('div');
          const small = document.createElement('div');
          small.textContent = hero ? 'FASAD PORTABLE' : 'FASAD PORTABLE  •  ' + number;
          small.style.cssText = 'font:700 12px/1.4 Arial,sans-serif;letter-spacing:.17em;color:#fbbf24;margin-bottom:7px';
          const heading = document.createElement('div');
          heading.textContent = title;
          heading.style.cssText = hero
            ? 'font:700 50px/1.08 Arial,sans-serif;max-width:760px'
            : 'font:700 23px/1.15 Arial,sans-serif';
          const sub = document.createElement('div');
          sub.textContent = subtitle;
          sub.style.cssText = hero
            ? 'font:400 23px/1.4 Arial,sans-serif;margin-top:18px;color:#e2e8f0'
            : 'font:400 15px/1.4 Arial,sans-serif;margin-top:5px;color:#e2e8f0';
          content.append(small, heading, sub);
          box.append(content);
          document.body.append(box);
        }""",
        {"title": chapter.title, "subtitle": chapter.subtitle,
         "number": f"{index + 1:02d}/{len(CHAPTERS):02d}", "hero": hero},
    )


def fill_part(row, width: str, height: str, qty: str, price: str, article: str):
    for cell, value in ((1, width), (2, height), (3, qty), (5, "16"), (8, price)):
        row.locator("td").nth(cell).locator("input").fill(value)
    row.locator("td").nth(6).locator("input").fill(article)
    row.locator("td").nth(7).locator("input").fill("Белый глянец")


def main() -> None:
    assert DEMO_DB.resolve().is_relative_to((ROOT / "data").resolve())
    assert WORK.resolve().is_relative_to((ROOT / "data").resolve())
    assert DEMO_DB.exists() and META.exists() and EDGE.exists()
    WORK.mkdir(parents=True, exist_ok=True)
    meta = json.loads(META.read_text(encoding="utf-8"))
    voices: list[AudioSegment] = []
    for index, chapter in enumerate(CHAPTERS):
        path = WORK / f"voice-{index:02d}.mp3"
        if not path.exists() or path.stat().st_size < 1000:
            asyncio.run(make_voice(path, chapter.speech, index))
        voices.append(effects.normalize(AudioSegment.from_file(path)).fade_in(80).fade_out(140))
    SCRIPT_OUTPUT.write_text(
        "\n\n".join(f"{i + 1:02d}. {c.title}\n{c.speech}" for i, c in enumerate(CHAPTERS)),
        encoding="utf-8",
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(EDGE), headless=True)
        seed = browser.new_context(locale="ru-RU")
        login = seed.new_page()
        login.goto(f"{BASE}/login")
        login.locator("input[name=login]").fill("admin")
        login.locator("input[name=password]").fill("sales-video-2026")
        login.locator("button[type=submit]").click()
        login.wait_for_url("**/dashboard")
        state = seed.storage_state()
        seed.close()

        context = browser.new_context(
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(WORK), record_video_size={"width": 1600, "height": 900},
            storage_state=state, locale="ru-RU", reduced_motion="reduce",
            accept_downloads=True,
        )
        page = context.new_page()
        page.set_default_timeout(15000)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        cues: list[dict] = []
        started = time.monotonic()
        lead_url = ""
        order_url = ""

        def goto(route: str) -> None:
            page.goto(BASE + route, wait_until="domcontentloaded")
            page.wait_for_timeout(350)

        def scene(index: int, enter=None, during=None, *, hero=False, min_ms=0):
            if enter:
                enter()
            chapter = CHAPTERS[index]
            overlay(page, chapter, index, hero=hero)
            cue = int((time.monotonic() - started) * 1000)
            cues.append({"index": index, "title": chapter.title, "cue_ms": cue,
                         "voice_ms": len(voices[index])})
            if during:
                during()
            elapsed = int((time.monotonic() - started) * 1000) - cue
            page.wait_for_timeout(max(650, max(len(voices[index]) + 900, min_ms) - elapsed))

        scene(0, lambda: goto("/dashboard"), hero=True, min_ms=8000)
        scene(1, lambda: goto("/dashboard"))
        scene(2, lambda: goto("/inbox"))

        def enter_manager():
            goto("/manager")

        def fill_manager():
            page.get_by_placeholder("Имя клиента").fill("Ателье мебели Контур")
            page.get_by_placeholder("город, улица, дом — куда везти").fill(
                "Москва, улица Бауманская, 17")
            page.get_by_label("Срок датой").fill((date.today() + timedelta(days=21)).isoformat())
            page.locator("select").nth(1).select_option("enamel")
            fill_part(page.locator("table tbody tr").first,
                      "700", "400", "6", "19800", "FR-401")
            page.get_by_role("button", name="Добавить строку").click()
            fill_part(page.locator("table tbody tr").nth(1),
                      "450", "300", "4", "19000", "FR-402")
            page.locator("table tbody tr").first.evaluate(
                "(el) => el.scrollIntoView({block: 'center'})"
            )
            page.wait_for_timeout(800)

        scene(3, enter_manager, fill_manager, min_ms=12000)

        def save_lead():
            nonlocal lead_url
            page.get_by_role("button", name="Только заявка").click()
            page.wait_for_url("**/leads/*")
            lead_url = page.url
            if "/cutting" in lead_url:
                raise RuntimeError("Lead did not open after intake")

        scene(4, save_lead)

        def open_lead_edit():
            page.get_by_role("button", name="Изменить заявку").click()
            page.get_by_text("Артикулы позиций").wait_for()

        def change_lead():
            page.wait_for_timeout(1300)
            page.locator("label").filter(has_text="Позиция 1").locator("input").fill("FR-401B")
            page.wait_for_timeout(3500)
            page.get_by_role("button", name="Сохранить", exact=True).click()
            page.get_by_role("button", name="Изменить заявку").wait_for()

        scene(5, open_lead_edit, change_lead, min_ms=9000)

        def open_print_map():
            goto(lead_url.removeprefix(BASE) + "/cutting")
            body = page.locator("body").inner_text()
            if "Бауманская, 17" not in body or "FR-401B" not in body:
                raise RuntimeError("Saved address or article is missing from cutting map")
            page.evaluate("document.body.style.zoom='1.15'")

        scene(6, open_print_map, min_ms=9500)

        def open_cutting():
            goto(lead_url.removeprefix(BASE))
            page.get_by_role("link", name="Открыть раскрой").click()
            page.wait_for_url("**/film-cutting?*")

        scene(7, open_cutting)
        scene(8, lambda: page.evaluate("window.scrollTo(0, 1920)"), min_ms=8000)

        def convert_order():
            nonlocal order_url
            goto(lead_url.removeprefix(BASE))
            page.get_by_role("button", name="Создать заказ").click()
            page.wait_for_url("**/orders/*")
            order_url = page.url

        scene(9, convert_order)

        def scroll_to(text: str):
            page.get_by_role("heading", name=text, exact=True).scroll_into_view_if_needed()
            page.wait_for_timeout(350)

        scene(10, lambda: scroll_to("Смета заказа"))
        scene(11, lambda: scroll_to("Деньги по заказу"))
        scene(12, lambda: page.get_by_text(re.compile("Технические действия")).first.scroll_into_view_if_needed())

        def open_batch():
            goto("/cutting-batch")
            page.get_by_role("checkbox", name="Отметить все показанные заказы").check()
            if not page.get_by_role("checkbox", name="Отметить все показанные заказы").is_checked():
                raise RuntimeError("Batch selection failed")

        scene(13, open_batch)

        def show_batch_map():
            page.get_by_role("heading", name="Полотно и размещение деталей").scroll_into_view_if_needed()
            page.wait_for_timeout(350)

        scene(14, show_batch_map, min_ms=9000)
        scene(15, lambda: goto("/production/queue"))

        def show_stage():
            goto("/production/stages/" + meta["stage"])
            page.get_by_role("heading", name="Прогресс по деталям").scroll_into_view_if_needed()

        scene(16, show_stage)
        scene(17, lambda: goto("/workers"))
        scene(18, lambda: goto("/materials"))
        scene(19, lambda: goto("/stock"))
        scene(20, lambda: goto("/clients"))
        scene(21, lambda: goto("/reports"))
        scene(22, lambda: goto("/admin/price-book"))

        def admin_tour():
            goto("/admin/channels")
            page.wait_for_timeout(1200)
            goto("/admin/directions")
            page.wait_for_timeout(1200)
            goto("/admin/users")

        scene(23, admin_tour)
        scene(24, lambda: goto("/dashboard"), hero=True, min_ms=8500)

        functional_errors = [error for error in errors if "React error #418" not in error]
        if functional_errors:
            raise RuntimeError("Browser errors: " + "; ".join(functional_errors))
        total_ms = int((time.monotonic() - started) * 1000)
        video = page.video
        context.close()
        browser.close()
        raw = Path(video.path())

    TIMELINE.write_text(json.dumps(cues, ensure_ascii=False, indent=2), encoding="utf-8")
    narration = AudioSegment.silent(duration=total_ms + 250)
    for item in cues:
        narration = narration.overlay(voices[item["index"]], position=item["cue_ms"] + 120)
    wave = WORK / "narration.wav"
    narration.export(wave, format="wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(raw), "-i", str(wave),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-shortest", "-movflags", "+faststart", str(OUTPUT),
        ],
        check=True, capture_output=True,
    )
    print(f"Video: {OUTPUT}\nDuration: {total_ms / 1000:.1f}s\nChapters: {len(cues)}")


if __name__ == "__main__":
    main()
