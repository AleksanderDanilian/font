"""
Переписывает description для всех записей в data/fonts.jsonl через LLM —
из сухого типографского текста в короткий, разговорный, заточенный под то,
как реально формулируют запрос (2-5 слов): "тёплая пекарня", "строгий
техностартап", "нежная косметика".

Асинхронный, с ограничением параллелизма через семафор (--concurrency) —
на 1700 записях последовательные вызовы были бы неоправданно долгими.

ПОЧЕМУ КОРОТКО (1-2 предложения, не 3+):
Смысловой поиск сравнивает эмбеддинг короткого запроса пользователя (2-5
слов) с эмбеддингом description через косинусное сходство. Длинное,
цветистое описание "размывает" вектор — это усреднение многих идей,
поэтому оно хуже совпадает с острым, узким вектором короткого запроса.
Короткое описание, плотное по конкретным словам настроения и сценариям
использования, даёт эмбеддингу более концентрированный сигнал.

ПОЧЕМУ БЕЗ ТИПОГРАФСКОГО ЖАРГОНА:
Никто не ищет шрифт словами "geometric sans" или "x-height" — люди пишут
"современный", "для стартапа", "уютный". Если описание набито терминами,
эмбеддинг смещается в сторону словаря, которым реальные запросы не
пользуются.

Запуск (нужен ANTHROPIC_API_KEY в окружении; по умолчанию ходит через
прокси api.proxyapi.ru — см. --base-url, если у вас другой):
    python backend/enrich_descriptions.py
    python backend/enrich_descriptions.py --limit 20                # тест на 20 записях
    python backend/enrich_descriptions.py --concurrency 16           # больше параллелизма
    python backend/enrich_descriptions.py --model claude-sonnet-5    # другая модель
    python backend/enrich_descriptions.py --base-url https://api.anthropic.com   # без прокси

Скрипт СКИПАЕТ уже обработанные записи при повторном запуске (resume) —
можно спокойно прервать Ctrl+C и продолжить позже. Прогресс сохраняется
построчно в output-файл, входной data/fonts.jsonl не трогается, пока вы
сами не замените его результатом (см. вывод скрипта в конце).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = PROJECT_ROOT / "data" / "fonts.jsonl"
OUTPUT_PATH = PROJECT_ROOT / "data" / "fonts.enriched.jsonl"

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_BASE_URL = "https://api.proxyapi.ru/anthropic"
DEFAULT_CONCURRENCY = 8

# ---------------------------------------------------------------------------
# ПРОМПТ
# ---------------------------------------------------------------------------
# System-инструкция задаёт правила один раз; per-font данные идут в user-turn.
# Формат ответа — строгий JSON, чтобы парсить 1700 ответов без ошибок.

SYSTEM_PROMPT = """\
You are helping build a font-matching search tool. People search for fonts \
by typing SHORT, casual queries — 2 to 5 words, like "cozy bakery menu", \
"elegant wedding invite", "bold techy startup", "soft feminine skincare", \
"strict corporate report". Your job is to rewrite a font's description so \
its meaning aligns well with how real people phrase these short queries, \
so that semantic search (embedding similarity) between a short query and \
this description scores well when they're a genuine match.

Rules:
- Write 1–2 sentences, 20–35 words total. Never 3+ sentences.
- NO typographic jargon: never use words like "x-height", "geometric", \
"humanist", "counters", "aperture", "contrast strokes", "grotesque", \
"didone". Plain "serif" / "sans-serif" / "script" / "monospace" is fine \
if natural, but don't lean on them as the main content.
- Write like a brand/design consultant describing the \
font's personality and where it shines — not like a type foundry spec \
sheet. DONT use rare words, or words that might rarely be used by common users.
Example: no-nonsence / flair / fuss / stiff—perfect. REMEMBER, I am using it for sentence similarity purposes.
And users might not speak good english.
- Dont use negations, where possible. Instead of "not cold", write "warm".
- Naturally weave in 2–4 concrete, searchable words: mood adjectives (pull \
from mood_tags) AND real-world use cases / industries (pull from \
industry_tags) — don't invent moods or industries that aren't in the \
provided tags, but you don't have to use every single tag either, pick \
the ones that combine into a natural sentence.
- Avoid empty superlatives ("amazing", "stunning", "gorgeous", "perfect") \
that add no distinguishing signal — be specific instead.
- Write it in a way so that a 5th grader could read and understand it, without complex words and word structures.
- Avoid complexity, but remain main features of the font.
- Dont use rare words in description of fonts.
- Output ONLY valid JSON, nothing else, no markdown fences: \
{"description": "..."}
"""

USER_TEMPLATE = """\
Font family: {family_name}
Category: {category}
Mood tags: {mood_tags}
Industry tags: {industry_tags}
Existing (typographic, don't copy the style of this) description: {old_description}

Rewrite per the rules. Output JSON only.
"""


def build_user_prompt(record: dict) -> str:
    return USER_TEMPLATE.format(
        family_name=record.get("family_name", ""),
        category=record.get("category", "") or "unknown",
        mood_tags=", ".join(record.get("mood_tags", [])) or "none",
        industry_tags=", ".join(record.get("industry_tags", [])) or "none",
        old_description=record.get("description", "") or "(none)",
    )


async def call_llm(client, model: str, user_prompt: str, max_retries: int = 3) -> dict:
    """Вызывает Anthropic API (асинхронно), парсит JSON-ответ. Ретраит на
    transient-ошибках и на невалидном JSON (модель иногда оборачивает в
    ```json — подчищаем)."""
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=200,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = resp.content[0].text.strip()
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(text)
            if "description" not in parsed:
                raise ValueError(f"missing 'description' key in response: {parsed}")
            return parsed
        except Exception as e:  # noqa: BLE001 — намеренно широкий catch для ретраев
            last_err = e
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_err}")


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


async def process_one(
    record: dict,
    client,
    model: str,
    semaphore: asyncio.Semaphore,
    write_lock: asyncio.Lock,
    out_f,
    counters: dict,
) -> None:
    slug = record.get("family_name")

    async with semaphore:
        user_prompt = build_user_prompt(record)
        try:
            result = await call_llm(client, model, user_prompt)
        except Exception as e:  # noqa: BLE001
            print(f"  {slug}: ОШИБКА, пропускаю — {e}", file=sys.stderr)
            counters["failed"] += 1
            return

    new_record = dict(record)
    new_record["description"] = result["description"]
    # Сбрасываем embedding — раз текст изменился, старый вектор больше не
    # соответствует новому описанию. build_database.py сам пересчитает
    # эмбеддинг для записей с пустым embedding.
    new_record["embedding"] = []

    line = json.dumps(new_record, ensure_ascii=False) + "\n"
    async with write_lock:
        out_f.write(line)
        out_f.flush()

    counters["done"] += 1
    processed = counters["done"] + counters["failed"]
    if processed % 25 == 0 or processed == counters["total_to_process"]:
        print(
            f"  [{processed}/{counters['total_to_process']}] "
            f"готово: {counters['done']}, ошибок: {counters['failed']}"
        )


async def run(args) -> None:
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Не задан ANTHROPIC_API_KEY в окружении.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.AsyncAnthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url=args.base_url,
    )

    input_path = Path(args.input)
    output_path = Path(args.output)

    records = read_jsonl(input_path)
    if args.limit:
        records = records[: args.limit]
    print(f"Всего записей: {len(records)}")

    # --- resume: уже обработанные family_name пропускаем ---
    done_slugs: set[str] = set()
    if output_path.exists():
        for rec in read_jsonl(output_path):
            done_slugs.add(rec.get("family_name"))
        print(f"Уже обработано ранее (resume): {len(done_slugs)}")

    to_process = [r for r in records if r.get("family_name") not in done_slugs]
    print(f"К обработке сейчас: {len(to_process)} (параллелизм: {args.concurrency})")

    if not to_process:
        print("Нечего обрабатывать — всё уже готово.")
        return

    counters = {"done": 0, "failed": 0, "total_to_process": len(to_process)}
    semaphore = asyncio.Semaphore(args.concurrency)
    write_lock = asyncio.Lock()

    try:
        with open(output_path, "a", encoding="utf-8") as out_f:
            tasks = [
                process_one(record, client, args.model, semaphore, write_lock, out_f, counters)
                for record in to_process
            ]
            await asyncio.gather(*tasks)
    finally:
        await client.close()

    print(f"\nГотово. Результат: {output_path}")
    print(f"Успешно: {counters['done']}, ошибок: {counters['failed']}")
    if counters["failed"]:
        print("Ошибочные записи просто пропущены — перезапустите скрипт ещё раз, resume их подхватит.")
    print("\nПроверьте выборочно несколько записей, затем замените ими data/fonts.jsonl:")
    print(f"  mv {output_path} {input_path}")
    print("После замены обязательно пересоберите БД — embedding сброшен и посчитается заново:")
    print("  python backend/build_database.py")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL),
        help="Anthropic-совместимый endpoint. По умолчанию — прокси api.proxyapi.ru.",
    )
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Сколько запросов параллельно")
    parser.add_argument("--limit", type=int, default=None, help="Обработать только первые N записей (для теста)")
    parser.add_argument("--input", default=str(INPUT_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()

    try:
        import anthropic  # noqa: F401
    except ImportError:
        print("Нужен пакет anthropic: pip install anthropic --break-system-packages", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()