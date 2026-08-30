"""
render_previews.py

Рендерит превью-картинку (PNG) для каждого шрифта: одна картинка на один шрифт,
с Regular и Bold начертанием и панграммой. Использует headless Chromium через
Playwright, поэтому рендер идентичен тому, что увидит пользователь в браузере
(тот же хинтинг, кернинг, лигатуры).

Слова "Regular"/"Bold" здесь — это просто подписи в HTML-шаблоне и имена
CSS-классов, а НЕ ожидаемые имена файлов. Реальные файлы шрифтов скрипт
берёт из значений ключей "regular"/"bold" в data/fonts_manifest.json — а
там уже лежат актуальные пути вида "fonts/{slug}/{slug}-400.woff2" и
"fonts/{slug}/{slug}-700.woff2" (именно так их называет download_fonts.py).
То есть с шрифтами, названными по весам (400/700), а не по словам
Regular/Bold, этот скрипт работает без каких-либо изменений — единственное,
что действительно важно, это чтобы пути в манифесте были верными
относительно корня проекта (см. BASE_DIR ниже).

Входные данные (в структуре проекта google-fonts-project):
    fonts/{slug}/{slug}-400.woff2
    fonts/{slug}/{slug}-700.woff2
    data/fonts_manifest.json  — список шрифтов с путями к файлам (см. пример ниже)

Результат:
    previews/
        {slug}.png
        ...

Расположение: этот файл лежит в src/, рядом с download_fonts.py.
Все пути ниже вычисляются от корня проекта (Path(__file__).parent.parent),
поэтому запускать можно из любой директории.

Установка зависимостей:
    pip install playwright
    playwright install chromium

Запуск:
    python src/render_previews.py
"""

import asyncio
import base64
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright

# Корень проекта = родитель директории src/, где лежит этот файл.
BASE_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = BASE_DIR / "fonts"
PREVIEWS_DIR = BASE_DIR / "previews"
MANIFEST_PATH = BASE_DIR / "data" / "fonts_manifest.json"

# Текст для превью. Панграмма + буквы разного регистра, чтобы были видны
# характерные засечки/формы букв. При желании можно добавить кириллическую
# панграмму вторым блоком, если разметка ведётся с прицелом на кириллицу.
PREVIEW_TEXT = "Aa Bb Gg Qq — The quick brown fox jumps"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
    @font-face {{
        font-family: 'PreviewFont';
        src: url(data:font/woff2;base64,{regular_b64}) format('woff2');
        font-weight: 400;
    }}
    @font-face {{
        font-family: 'PreviewFont';
        src: url(data:font/woff2;base64,{bold_b64}) format('woff2');
        font-weight: 700;
    }}
    body {{
        margin: 0;
        padding: 24px;
        background: #ffffff;
        width: 900px;
    }}
    .line {{
        font-family: 'PreviewFont', sans-serif;
        font-size: 42px;
        line-height: 1.3;
        color: #111111;
        white-space: nowrap;
    }}
    .regular {{ font-weight: 400; margin-bottom: 12px; }}
    .bold {{ font-weight: 700; }}
    .label {{
        font-family: Arial, sans-serif;
        font-size: 13px;
        color: #999999;
        margin-bottom: 4px;
    }}
</style>
</head>
<body>
    <div id="capture">
        <div class="label">{family_name} — Regular (400)</div>
        <div class="line regular">{text}</div>
        <div class="label">{family_name} — Bold (700)</div>
        <div class="line bold">{text}</div>
    </div>
</body>
</html>
"""


def load_manifest() -> list[dict]:
    """Читает data/fonts_manifest.json — упрощённый манифест, который пишет
    download_fonts.py. Формат:
    [
        {
            "family_name": "Montserrat",
            "slug": "montserrat",
            "regular": "fonts/montserrat/montserrat-400.woff2",
            "bold": "fonts/montserrat/montserrat-700.woff2"
        },
        ...
    ]
    Ключи "regular"/"bold" — это просто ярлыки начертаний (400/700 веса),
    имена самих файлов при этом могут быть любыми — скрипт их не парсит,
    а просто открывает по указанному пути.

    Если для шрифта нет отдельного Bold-файла — download_fonts.py уже
    подставляет туда путь к Regular (см. build_full_record), так что в
    превью в этом случае будут два одинаковых начертания — не страшно,
    просто не будет виден жирный вариант.
    """
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Манифест не найден: {MANIFEST_PATH}\n"
            f"Сначала запусти download_fonts.py (или --rebuild-from-disk), "
            f"чтобы он создал data/fonts_manifest.json."
        )
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_slug(name: str) -> str:
    """Превращает имя семейства/slug в безопасное имя файла для PNG-превью
    (заменяет всё, кроме букв/цифр/подчёркиваний/дефисов, на '_')."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)


async def render_font(page, font_entry: dict) -> None:
    """Рендерит одну картинку-превью для одного шрифта: читает его
    .woff2-файлы (regular/bold), зашивает их в HTML как base64 data URI,
    открывает эту страницу в headless Chromium, дожидается загрузки
    шрифтов (document.fonts.ready) и делает скриншот блока #capture в PNG.

    Данные шрифта передаются как data URI (а не как ссылка на file://),
    потому что при page.set_content() страница живёт в контексте
    about:blank, и Chromium из соображений безопасности блокирует загрузку
    @font-face по file://-ссылкам с такой страницы — шрифт тихо не
    грузится (без видимой ошибки), и рендерится системный шрифт по
    умолчанию, из-за чего все превью выглядят одинаково. Base64 data URI
    этого ограничения не касается.

    Пропускает шрифт, если превью для него уже существует (previews/{slug}.png) —
    так повторный запуск не перерисовывает всё заново."""
    family_name = font_entry["family_name"]
    slug = safe_slug(font_entry.get("slug", family_name))
    output_path = PREVIEWS_DIR / f"{slug}.png"

    if output_path.exists():
        print(f"[skip] {family_name} — превью уже существует")
        return

    regular_file = BASE_DIR / font_entry["regular"]
    bold_file = BASE_DIR / font_entry["bold"]

    if not regular_file.exists():
        print(f"[error] {family_name}: не найден файл {regular_file}")
        return
    if not bold_file.exists():
        print(f"[error] {family_name}: не найден файл {bold_file}")
        return

    regular_b64 = base64.b64encode(regular_file.read_bytes()).decode("ascii")
    bold_b64 = base64.b64encode(bold_file.read_bytes()).decode("ascii")

    html = HTML_TEMPLATE.format(
        regular_b64=regular_b64,
        bold_b64=bold_b64,
        family_name=family_name,
        text=PREVIEW_TEXT,
    )

    await page.set_content(html)
    # Ждём, чтобы шрифт точно успел загрузиться и отрендериться
    await page.wait_for_timeout(150)
    await page.evaluate("document.fonts.ready")

    element = await page.query_selector("#capture")
    await element.screenshot(path=str(output_path))
    print(f"[ok] {family_name} → {output_path.name}")


async def main():
    """Точка входа: читает манифест, поднимает headless Chromium и рендерит
    превью для каждого шрифта из манифеста (пропуская уже готовые)."""
    PREVIEWS_DIR.mkdir(exist_ok=True)
    manifest = load_manifest()
    print(f"Всего шрифтов в манифесте: {len(manifest)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 950, "height": 300})

        for entry in manifest:
            try:
                await render_font(page, entry)
            except Exception as e:
                print(f"[error] {entry.get('family_name')}: {e}")

        await browser.close()

    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
