"""
translate_descriptions.py

Одноразовый скрипт для уже размеченных шрифтов (когда description был
на русском). Проходится по data/fonts.jsonl, для записей, где description
на русском (определяем по наличию кириллицы):

    1. Переводит description на английский через API.
    2. Кладёт оригинальный русский текст в новое поле description_ru.
    3. Заменяет description на английский перевод.

Записи, где description уже на английском — пропускаются, никаких лишних
вызовов API. Записи с needs_review — тоже пропускаются.

ВАЖНО (в отличие от первой версии скрипта): результат каждого перевода
сразу дописывается в кэш-файл data/translations_cache.jsonl (append-only,
как в label_fonts.py) — а не хранится только в памяти до самого конца.
Слияние кэша в основной fonts.jsonl происходит ПРИ КАЖДОМ запуске скрипта,
поэтому даже если скрипт упадёт, зависнет или будет прерван вручную —
уже полученные (и оплаченные) переводы не потеряются, их подхватит
следующий запуск.

Также на каждый запрос к API стоит таймаут (REQUEST_TIMEOUT) — если
соединение (особенно через прокси) подвиснет, задача упадёт по таймауту
и уйдёт на retry вместо того, чтобы висеть бесконечно и блокировать
весь asyncio.gather.

Установка зависимостей:
    pip install anthropic python-dotenv

Использование:
    python translate_descriptions.py
    python translate_descriptions.py --concurrency 10
    python translate_descriptions.py --dry-run   # показать, что будет переведено, без вызовов API
"""

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent
DATA_PATH = PROJECT_ROOT / "data" / "fonts.jsonl"
CACHE_PATH = PROJECT_ROOT / "data" / "translations_cache.jsonl"

MODEL_NAME = "claude-haiku-4-5-20251001"
CONCURRENCY = 8
REQUEST_TIMEOUT = 60  # секунд на один запрос, после этого — retry

load_dotenv()

CYRILLIC_RE = re.compile(r"[а-яА-ЯёЁ]")

SYSTEM_PROMPT = """You translate short font-description texts from Russian to English.
Return ONLY the translated text — no quotes, no explanations, no preamble.
Keep it natural and concise, suitable for semantic search / embeddings.
Preserve the original meaning and tone; do not add new information."""


def is_russian(text: str) -> bool:
    return bool(CYRILLIC_RE.search(text))


def get_client() -> anthropic.AsyncAnthropic:
    api_key = os.environ.get("proxy_api_claudie")
    if not api_key:
        raise RuntimeError("Установи переменную окружения proxy_api_claudie")
    return anthropic.AsyncAnthropic(api_key=api_key, base_url="https://api.proxyapi.ru/anthropic")


async def translate_one(client: anthropic.AsyncAnthropic, text: str) -> str:
    response = await client.messages.create(
        model=MODEL_NAME,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
    )
    return response.content[0].text.strip()


def load_cache() -> dict:
    """Читает уже полученные (и уже оплаченные) переводы из кэш-файла.
    Ключ — family_name. Используется и для skip уже переведённых,
    и для восстановления прогресса после сбоя/зависания."""
    cache = {}
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line)
                    cache[obj["family_name"]] = obj
    return cache


def merge_cache_into_main(cache: dict) -> int:
    """Применяет всё, что есть в кэше, к основному fonts.jsonl.
    Вызывается при КАЖДОМ запуске скрипта — до и после перевода —
    чтобы подхватить результаты прошлых прерванных запусков."""
    if not DATA_PATH.exists():
        raise RuntimeError(f"{DATA_PATH} не найден.")

    records = []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    merged_count = 0
    for r in records:
        family_name = r.get("family_name")
        if family_name in cache and "description_ru" not in r:
            cached = cache[family_name]
            r["description_ru"] = cached["description_ru"]
            r["description"] = cached["description_en"]
            merged_count += 1

    if merged_count:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return merged_count


async def process_record(
    client: anthropic.AsyncAnthropic,
    sem: asyncio.Semaphore,
    write_lock: asyncio.Lock,
    cache_file,
    family_name: str,
    description_ru: str,
) -> None:
    retries = 3

    async with sem:
        for attempt in range(1, retries + 1):
            try:
                translated = await asyncio.wait_for(
                    translate_one(client, description_ru),
                    timeout=REQUEST_TIMEOUT,
                )

                # Пишем сразу же, не дожидаясь остальных задач —
                # это и есть ключевое исправление
                async with write_lock:
                    cache_file.write(json.dumps({
                        "family_name": family_name,
                        "description_en": translated,
                        "description_ru": description_ru,
                    }, ensure_ascii=False) + "\n")
                    cache_file.flush()

                print(f"[ok] {family_name}")
                return

            except asyncio.TimeoutError:
                print(f"[timeout attempt {attempt}/{retries}] {family_name}: превышен таймаут {REQUEST_TIMEOUT}с")
            except anthropic.RateLimitError:
                print(f"[rate limit] {family_name}: пауза 20с...")
                await asyncio.sleep(20)
            except Exception as e:
                print(f"[error attempt {attempt}/{retries}] {family_name}: {e}")
                await asyncio.sleep(3)

        print(f"[FAIL] {family_name}: не удалось перевести после {retries} попыток")


async def run_async(dry_run: bool, concurrency: int):
    if not DATA_PATH.exists():
        raise RuntimeError(f"{DATA_PATH} не найден.")

    # Шаг 1: подхватываем результаты прошлых (возможно прерванных) запусков
    cache = load_cache()
    if cache:
        merged = merge_cache_into_main(cache)
        if merged:
            print(f"Подхвачено из кэша прошлого запуска и слито в fonts.jsonl: {merged}")

    records = []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    to_translate = []
    for r in records:
        if r.get("needs_review"):
            continue
        if "description_ru" in r:
            continue  # уже переведено (в т.ч. только что слито из кэша)
        description = r.get("description", "")
        if description and is_russian(description):
            to_translate.append((r["family_name"], description))

    print(f"Всего записей: {len(records)}. К переводу: {len(to_translate)}.")

    if dry_run:
        print("Dry-run, вызовов API не будет. Шрифты, которые были бы переведены:")
        for family_name, description in to_translate:
            print(f"  - {family_name}: {description[:60]}...")
        return

    if not to_translate:
        print("Нечего переводить.")
        return

    client = get_client()
    sem = asyncio.Semaphore(concurrency)
    write_lock = asyncio.Lock()

    start = time.time()
    with open(CACHE_PATH, "a", encoding="utf-8") as cache_file:
        tasks = [
            process_record(client, sem, write_lock, cache_file, family_name, description)
            for family_name, description in to_translate
        ]
        await asyncio.gather(*tasks)
    elapsed = time.time() - start

    # Шаг 2: сливаем свежепереведённое в основной файл
    cache = load_cache()
    merged = merge_cache_into_main(cache)

    print(f"Готово за {elapsed:.1f}с. Слито в {DATA_PATH.name}: {merged}.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Показать, что будет переведено, без вызовов API")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY, help="Число параллельных запросов")
    args = parser.parse_args()

    asyncio.run(run_async(dry_run=args.dry_run, concurrency=args.concurrency))


if __name__ == "__main__":
    main()