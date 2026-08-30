"""
Скачивает свежие метаданные Google Fonts Developer API с параметром
capability=WOFF2, чтобы получить прямые ссылки на .woff2-файлы на
fonts.gstatic.com (по умолчанию API отдаёт .ttf — см. официальную
документацию https://developers.google.com/fonts/docs/developer_api).

Перезаписывает data/fonts_metadata.json. Отдельный шаг от build_database.py
намеренно: это внешний сетевой вызов к Google, который не обязан
выполняться на каждой сборке БД — метаданные шрифтов меняются редко,
запускать этот скрипт достаточно раз в несколько месяцев (или когда
build_database.py пожалуется на нехватку записи в метаданных для
какого-то шрифта).

Нужен бесплатный API-ключ Google Fonts Developer API:
https://developers.google.com/fonts/docs/developer_api#authentication

Запуск:
    export GOOGLE_FONTS_API_KEY=...
    python backend/fetch_google_fonts_metadata.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "fonts_metadata.json"

API_URL = "https://www.googleapis.com/webfonts/v1/webfonts?key={key}&capability=WOFF2"


def main():
    api_key = os.getenv("GOOGLE_FONTS_API_KEY")
    if not api_key:
        print("Не задан GOOGLE_FONTS_API_KEY в окружении.", file=sys.stderr)
        print("Получить ключ: https://developers.google.com/fonts/docs/developer_api#authentication", file=sys.stderr)
        sys.exit(1)

    url = API_URL.format(key=api_key)
    print(f"Запрашиваю {url.replace(api_key, '***')} ...")

    with urllib.request.urlopen(url) as resp:
        data = json.load(resp)

    items = data.get("items", [])
    print(f"Получено {len(items)} записей о шрифтах.")

    # sanity-check: убеждаемся, что реально получили .woff2, а не .ttf —
    # если Google когда-нибудь поменяет поведение параметра, лучше упасть
    # тут явно, чем молча положить в БД битые ссылки на .ttf
    sample_files = []
    for item in items[:20]:
        sample_files.extend(item.get("files", {}).values())
    non_woff2 = [f for f in sample_files if not f.endswith(".woff2")]
    if non_woff2:
        print(
            f"  [warn] среди первых записей есть файлы не в .woff2 "
            f"(например: {non_woff2[0]}) — проверьте, что capability=WOFF2 "
            f"действительно сработал",
            file=sys.stderr,
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Сохранено: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
