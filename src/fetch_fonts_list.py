"""
fetch_fonts_list.py  (было save_fonts_info.py)

Скачивает полный список шрифтов Google Fonts через официальный
Google Fonts Developer API (https://www.googleapis.com/webfonts/v1/webfonts)
и сохраняет:
    - data/fonts_metadata.json — сырой ответ API (все поля: family,
      category, variants, subsets, files и т.д.);
    - data/families.txt — только имена семейств, по одному на строку
      (этот файл дальше скармливается в download_fonts.py через
      --families-file).

Нужен API-ключ Google Fonts (google_fonts_api_key в .env в корне проекта).

Примечание: у тебя уже есть готовые и заполненные data/fonts_metadata.json
и data/families.txt, так что повторно этот скрипт запускать не обязательно —
он нужен только если список шрифтов Google Fonts нужно обновить/перекачать
с нуля.

Использование:
    python src/fetch_fonts_list.py
"""

import requests
import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Корень проекта = родитель директории src/, где лежит этот файл.
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ENV_PATH = BASE_DIR / ".env"

# Загружаем .env из корня проекта явно (а не из текущей рабочей директории) —
# так скрипт работает одинаково, из какой бы папки его ни запустили.
load_dotenv(ENV_PATH)

API_KEY = os.getenv("google_fonts_api_key")
API_URL = "https://www.googleapis.com/webfonts/v1/webfonts"

METADATA_FILE = DATA_DIR / "fonts_metadata.json"
FAMILIES_FILE = DATA_DIR / "families.txt"


def download_fonts_metadata(api_key: str) -> dict:
    """Делает запрос к Google Fonts Developer API и возвращает JSON-ответ
    целиком (список всех шрифтов Google Fonts со всеми их метаданными:
    category, variants, subsets, files, ...).

    Args:
        api_key: ключ Google Fonts API.

    Returns:
        Разобранный JSON-ответ API (dict с ключом "items" — списком шрифтов).

    Raises:
        ValueError: если ключ не передан.
        Exception: если запрос или разбор JSON завершились ошибкой.
    """
    if not api_key:
        raise ValueError("API key is missing. Please set google_fonts_api_key in your .env file.")

    params = {
        "key": api_key,
        "sort": "alpha",  # сортировка по алфавиту (не обязательно, но удобно для чтения файла)
    }

    try:
        print("Fetching Google Fonts metadata...")
        response = requests.get(API_URL, params=params)
        response.raise_for_status()

        data = response.json()
        print(f"Successfully fetched metadata for {len(data.get('items', []))} fonts")
        return data

    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to fetch fonts metadata: {e}")
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse API response: {e}")


def save_metadata(data: dict, filepath: Path) -> None:
    """Сохраняет весь ответ API как есть в JSON-файл (с отступами,
    с сохранением не-ASCII символов для читаемости)."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Metadata saved to {filepath}")


def extract_family_names(data: dict) -> list[str]:
    """Достаёт из полного ответа API только имена семейств (поле "family"
    у каждого элемента "items"), в том порядке, в котором они пришли от API."""
    items = data.get("items", [])
    family_names = [item.get("family", "") for item in items if item.get("family")]
    return family_names


def save_family_names(family_names: list[str], filepath: Path) -> None:
    """Сохраняет список имён семейств в текстовый файл — по одному имени
    на строку. Этот файл дальше используется как вход для
    download_fonts.py --families-file."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(family_names))

    print(f"Family names saved to {filepath}")
    print(f"Total families: {len(family_names)}")


def main() -> int:
    """Точка входа: скачивает метаданные всех шрифтов Google Fonts,
    сохраняет полный JSON и отдельно — список имён семейств."""
    try:
        if not ENV_PATH.exists():
            print(f"Warning: .env file not found at {ENV_PATH}. "
                  f"Make sure it exists with google_fonts_api_key=YOUR_API_KEY")

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        metadata = download_fonts_metadata(API_KEY)

        save_metadata(metadata, METADATA_FILE)

        family_names = extract_family_names(metadata)
        save_family_names(family_names, FAMILIES_FILE)

        print("\n✅ Done! Files created:")
        print(f"  - {METADATA_FILE}: Full metadata")
        print(f"  - {FAMILIES_FILE}: Family names only (one per line)")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
