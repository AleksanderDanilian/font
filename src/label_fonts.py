"""
label_fonts.py

Разметка шрифтов через vision-модель: ОДИН запрос на ОДИН шрифт (не коллаж),
чтобы модель не путала характеристики соседних шрифтов между собой.

Запросы к API идут ПАРАЛЛЕЛЬНО (через asyncio + Semaphore), с ограничением
на количество одновременных запросов — CONCURRENCY ниже. Это только для
сетевого I/O (сами запросы к API); эмбеддинги (CPU-задача) считаются
локально и последовательно, там параллелизм не нужен.

Описание (description) генерируется СТРОГО на английском языке.

Установка зависимостей:
    pip install anthropic sentence-transformers tqdm python-dotenv

Переменные окружения (например, через .env):
    ANTHROPIC_API_KEY — ключ API (или свой, если используешь прокси — см. код run_labeling)

Использование:
    python label_fonts.py --label          # разметка через API (параллельно)
    python label_fonts.py --embed          # добавить эмбеддинги локально
    python label_fonts.py --label --embed  # и то и другое последовательно
    python label_fonts.py --embed --rewrite # перезаписать существующие эмбеддинги новой моделью
"""

import argparse
import asyncio
import base64
import json
import os
import time
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).parent            # директория скрипта (src/)
PROJECT_ROOT = BASE_DIR.parent               # корень проекта (там же, где /data)

PREVIEWS_DIR = PROJECT_ROOT / "previews"
OUTPUT_PATH = PROJECT_ROOT / "data" / "fonts.jsonl"

# Модель с vision. Для рутинной разметки берём более дешёвую/быструю модель —
# точности достаточно для классификации внешнего вида шрифта.
MODEL_NAME = "claude-haiku-4-5-20251001"

# Сколько запросов к API держать в полёте одновременно.
# Слишком большое значение может упереться в rate limit — если начнёшь часто
# ловить RateLimitError, просто уменьши число.
CONCURRENCY = 6

load_dotenv()

MOOD_TAGS_ALLOWED = {
    "soft", "strong", "playful", "serious", "elegant", "casual",
    "modern", "vintage", "minimal", "decorative", "warm", "cold",
    "friendly", "corporate",
}

INDUSTRY_TAGS_ALLOWED = {
    "fashion", "cosmetics", "tech", "food", "finance", "luxury",
    "kids", "wedding", "gaming", "editorial", "health", "real_estate", "art",
}

SYSTEM_PROMPT = f"""You are a typography and branding expert.
You are shown a preview image of ONE font (Regular and Bold weights).

Analyze its visual character and return STRICTLY a JSON object,
with no markdown formatting, no explanations before or after, no ```.

Response format:
{{
  "mood_tags": ["tag1", "tag2"],
  "industry_tags": ["tag1", "tag2"],
  "description": "2-3 sentences IN ENGLISH describing the font's character
    and which brands/use cases it fits"
}}

Rules:
- mood_tags: pick 2 to 4 tags STRICTLY from this list:
  {sorted(MOOD_TAGS_ALLOWED)}
- industry_tags: pick 1 to 3 tags STRICTLY from this list:
  {sorted(INDUSTRY_TAGS_ALLOWED)}
- Do not invent tags outside these lists.
- description MUST be in English, regardless of any other language.
  It should be substantive and useful for semantic search (mention style,
  feeling, associations — no filler).
"""


def encode_image(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


async def call_model(client: anthropic.AsyncAnthropic, image_path: Path, family_name: str) -> dict:
    image_b64 = encode_image(image_path)

    response = await client.messages.create(
        model=MODEL_NAME,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"Font name: {family_name}. Label it according to the instructions.",
                    },
                ],
            }
        ],
    )

    raw_text = response.content[0].text.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:].strip()

    return json.loads(raw_text)


def validate_and_clean(parsed: dict, family_name: str) -> Optional[dict]:
    mood = [t for t in parsed.get("mood_tags", []) if t in MOOD_TAGS_ALLOWED]
    industry = [t for t in parsed.get("industry_tags", []) if t in INDUSTRY_TAGS_ALLOWED]
    description = parsed.get("description", "").strip()

    if not mood or not description:
        print(f"[warn] {family_name}: подозрительный ответ, требуется ручная проверка: {parsed}")
        return None

    return {
        "mood_tags": mood,
        "industry_tags": industry,
        "description": description,
    }


def load_existing_results() -> dict:
    """Чтобы можно было прерывать и перезапускать скрипт без повторной оплаты
    уже размеченных шрифтов."""
    results = {}
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line)
                    results[obj["family_name"]] = obj
    return results


def get_client() -> anthropic.AsyncAnthropic:
    api_key = os.environ.get("proxy_api_claudie")
    if not api_key:
        raise RuntimeError("Установи переменную окружения ANTHROPIC_API_KEY")
    return anthropic.AsyncAnthropic(api_key=api_key, base_url="https://api.proxyapi.ru/anthropic")
    # return anthropic.AsyncAnthropic(api_key=api_key)
    # Если используешь прокси (например proxyapi.ru), раскомментируй и поправь:
    # return anthropic.AsyncAnthropic(api_key=api_key, base_url="https://api.proxyapi.ru/anthropic")


async def process_one(
    client: anthropic.AsyncAnthropic,
    sem: asyncio.Semaphore,
    write_lock: asyncio.Lock,
    out_file,
    preview_path: Path,
) -> None:
    family_name = preview_path.stem
    retries = 3

    async with sem:  # ограничивает число одновременно летящих запросов
        for attempt in range(1, retries + 1):
            try:
                parsed = await call_model(client, preview_path, family_name)
                cleaned = validate_and_clean(parsed, family_name)

                if cleaned is None:
                    record = {"family_name": family_name, "needs_review": True, "raw": parsed}
                else:
                    record = {"family_name": family_name, **cleaned}

                # Запись в общий файл — под замком, чтобы строки из разных
                # корутин не перемешались друг с другом
                async with write_lock:
                    out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out_file.flush()

                print(f"[ok] {family_name}")
                return

            except json.JSONDecodeError:
                print(f"[retry {attempt}/{retries}] {family_name}: невалидный JSON от модели")
                await asyncio.sleep(2)
            except anthropic.RateLimitError:
                print(f"[rate limit] {family_name}: пауза 20с...")
                await asyncio.sleep(20)
            except Exception as e:
                print(f"[error attempt {attempt}/{retries}] {family_name}: {e}")
                await asyncio.sleep(3)

        print(f"[FAIL] {family_name}: не удалось разметить после {retries} попыток")


async def run_labeling_async():
    client = get_client()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = load_existing_results()

    preview_files = sorted(PREVIEWS_DIR.glob("*.png"))
    todo = [p for p in preview_files if p.stem not in existing]

    print(f"Найдено превью: {len(preview_files)}. Уже размечено: {len(existing)}. К обработке: {len(todo)}")
    print(f"Параллельность: {CONCURRENCY} одновременных запросов")

    if not todo:
        print("Нечего размечать.")
        return

    sem = asyncio.Semaphore(CONCURRENCY)
    write_lock = asyncio.Lock()

    start = time.time()
    with open(OUTPUT_PATH, "a", encoding="utf-8") as out_file:
        tasks = [process_one(client, sem, write_lock, out_file, p) for p in todo]
        await asyncio.gather(*tasks)

    elapsed = time.time() - start
    print(f"Разметка завершена за {elapsed:.1f}с ({elapsed / len(todo):.2f}с на шрифт в среднем).")


def run_labeling():
    asyncio.run(run_labeling_async())


def run_embedding(rewrite: bool = False):
    """Считаем эмбеддинги description локальной моделью (CPU, бесплатно).
    Это CPU-задача, параллелить через asyncio смысла нет — sentence-transformers
    сам эффективно батчит вычисления на всех ядрах внутри model.encode().

    Args:
        rewrite: Если True, перезаписывает существующие эмбеддинги даже если они уже есть.
                Если False, пропускает записи, у которых уже есть embedding.
    """
    if not OUTPUT_PATH.exists():
        raise RuntimeError(
            f"{OUTPUT_PATH} не найден. Сначала запусти разметку: python label_fonts.py --label"
        )

    print("Загружаю локальную embedding-модель")
    model_name = os.getenv('EMBEDDING_MODEL_NAME')
    model = SentenceTransformer(model_name)

    # Читаем все записи
    records = []
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    # Определяем, какие записи нужно обработать
    texts_to_embed = []
    indices_to_embed = []
    needs_embedding_count = 0
    skipped_count = 0

    for i, r in enumerate(records):
        # Пропускаем записи, требующие ручной проверки
        if r.get("needs_review"):
            continue

        # Проверяем, есть ли уже эмбеддинг
        has_embedding = "embedding" in r and r["embedding"] is not None

        if has_embedding and not rewrite:
            # Пропускаем, если уже есть эмбеддинг и мы не в режиме перезаписи
            skipped_count += 1
            continue

        # Добавляем в список для вычисления
        texts_to_embed.append(r["description"])
        indices_to_embed.append(i)
        needs_embedding_count += 1

    if not texts_to_embed:
        print(f"Все записи уже имеют эмбеддинги. Используйте --rewrite для перезаписи.")
        return

    print(f"Найдено записей: {len(records)}")
    print(f"  - Пропущено (уже есть эмбеддинг): {skipped_count}")
    print(f"  - Будет обработано: {needs_embedding_count}")
    if rewrite:
        print("  - Режим: ПЕРЕЗАПИСЬ (все существующие эмбеддинги будут заменены)")

    # Вычисляем эмбеддинги
    print(f"Считаю эмбеддинги для {len(texts_to_embed)} описаний...")
    embeddings = model.encode(texts_to_embed, show_progress_bar=True)

    # Обновляем записи
    for idx, emb in zip(indices_to_embed, embeddings):
        records[idx]["embedding"] = emb.tolist()

    # Сохраняем обновленные записи
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Эмбеддинги {'перезаписаны' if rewrite else 'посчитаны'} и сохранены.")
    print(f"Всего записей в файле: {len(records)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", action="store_true", help="Разметить шрифты через API (параллельно)")
    parser.add_argument("--embed", action="store_true", help="Посчитать локальные эмбеддинги")
    parser.add_argument("--rewrite", action="store_true", help="Перезаписать существующие эмбеддинги (только с --embed)")
    parser.add_argument("--concurrency", type=int, default=None, help="Переопределить число параллельных запросов")
    args = parser.parse_args()

    if args.concurrency:
        CONCURRENCY = args.concurrency

    if not args.label and not args.embed:
        parser.print_help()
    if args.label:
        run_labeling()
    if args.embed:
        run_embedding(rewrite=args.rewrite)