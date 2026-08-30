"""
Сборка backend/fonts.db из data/fonts_full_manifest.jsonl + data/fonts.jsonl
(раздел 6 ТЗ, "Сборка БД").

ВАЖНО — расхождения с буквальным текстом ТЗ, обнаруженные на реальных данных:

1. Ключ джойна — НЕ family_name==family_name (как написано в разделе 6),
   а fonts.jsonl.family_name == fonts_full_manifest.slug. В fonts.jsonl поле
   "family_name" по факту содержит slug ("abeezee"), а не человекочитаемое
   имя ("ABeeZee") — то оно лежит в манифесте под "family_name". Джойним по
   нормализованному (lower+strip) значению.

2. embedding в fonts.jsonl может быть пустым списком []. Если так —
   считаем эмбеддинг на месте из description через EMBEDDING_MODEL_NAME.
   Если непустой и правильной размерности — используем как есть (не тратим
   время на пересчёт всех 1700 при повторных запусках).

3. Пути regular/bold в манифесте на бэкслэшах (Windows) — нормализуются в
   forward slashes.

4. category в манифесте в верхнем регистре с подчёркиванием (SANS_SERIF) —
   приводится к "sans-serif".

5. needs_review/is_premium/referral_url отсутствуют в текущих исходных
   файлах — берутся через .get() с дефолтами (False/False/None), чтобы
   скрипт не падал, если часть из 1700 записей эти поля всё же содержит.

6. ИСТОЧНИК ФАЙЛОВ ШРИФТОВ — Google CDN с фолбэком на VPS.
   Для каждого шрифта regular/bold сначала пытаемся взять прямую ссылку на
   fonts.gstatic.com из data/fonts_metadata.json (см.
   fetch_google_fonts_metadata.py — метаданные должны быть получены с
   capability=WOFF2, иначе там .ttf, не .woff2). Если в метаданных нет
   нужного начертания (не завели файл, шрифт не найден по имени, либо
   fonts_metadata.json вообще отсутствует) — используем локальный путь из
   fonts_full_manifest.jsonl (раздача через /static/fonts на своём VPS) как
   фолбэк. Это позволяет не хранить у себя большинство файлов (Google
   Fonts отдаёт их с CDN сам), но не терять шрифты, для которых Google почему-то
   недоступен, а также даёт задел под будущие НЕ-Google шрифты, у которых
   в fonts_metadata.json записи в принципе не будет — они всегда пойдут
   через локальный путь.
   В БД в regular_woff2_path/bold_woff2_path в обоих случаях попадает
   валидный URL или относительный путь — main.py сам разбирается, что из
   этого абсолютная ссылка (Google), а что — путь на диске (см. _font_to_out).

Usage:
    python build_database.py
    python build_database.py --skip-missing-fonts-dir   # не проверять наличие локальных woff2 на диске
    python build_database.py --no-google-cdn            # игнорировать fonts_metadata.json, всегда локально
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

from config import settings

# --- эмбеддинг-модель загружается лениво, только если реально нужна ---
_model = None


def get_embedder():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.embedding_model_name)
    return _model


def embed_text(text: str) -> np.ndarray:
    model = get_embedder()
    vec = model.encode(text, normalize_embeddings=False)
    return np.asarray(vec, dtype=np.float32)


def normalize_slug(value: str) -> str:
    return value.strip().lower()


def normalize_family_key(value: str) -> str:
    """Нормализация имени семейства для сопоставления с Google Fonts API
    (там "family": "ABeeZee" / "Playfair Display" — человекочитаемо, как
    и manifest.family_name, но регистр/пробелы лучше не считать значимыми)."""
    return "".join(ch for ch in value.lower() if ch.isalnum())


def normalize_category(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower().replace("_", "-")


def normalize_path(value: str) -> str:
    """Приводит ЛОКАЛЬНЫЙ путь из манифеста к виду, относительному к
    fonts_dir (т.е. без ведущего "fonts/"), чтобы он совпадал с тем, что
    реально раздаёт StaticFiles(directory=fonts_dir) в main.py. Абсолютные
    URL (Google CDN) через эту функцию не проходят — они уже готовы."""
    v = value.replace("\\", "/").lstrip("/")
    if v.startswith("fonts/"):
        v = v[len("fonts/"):]
    return v


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [warn] {path.name}:{line_num} — невалидный JSON, пропускаю: {e}", file=sys.stderr)
    return records


def load_google_metadata(path: Path) -> dict[str, dict]:
    """Индексирует data/fonts_metadata.json (формат Google Fonts Developer
    API, см. fetch_google_fonts_metadata.py) по нормализованному имени
    семейства. Возвращает {} если файла нет — тогда все шрифты просто идут
    через локальный фолбэк, ничего не падает."""
    if not path.exists():
        print(
            f"  [info] {path.name} не найден — все шрифты будут раздаваться "
            f"с локального /fonts (см. fetch_google_fonts_metadata.py, если "
            f"хотите отдавать их с CDN Google)",
            file=sys.stderr,
        )
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    by_family: dict[str, dict] = {}
    for item in data.get("items", []):
        family = item.get("family")
        if not family:
            continue
        by_family[normalize_family_key(family)] = item
    return by_family


def resolve_font_url(
    google_item: dict | None,
    variant_key: str,
    local_path: str,
    fonts_dir: Path,
    skip_fonts_dir_check: bool,
    slug: str,
    weight_label: str,
) -> tuple[str, str]:
    """Возвращает (url_or_path, source), где source — "google" | "local".
    variant_key — ключ в Google-овском "files": "regular" для normal 400,
    "700" для bold. Если в google_item такого ключа нет (не всегда есть
    настоящий bold-cut), либо google_item is None (метаданных вообще нет,
    или Google Fonts не знает про такое семейство), падаем на local_path."""
    if google_item is not None:
        files = google_item.get("files", {})
        url = files.get(variant_key)
        if url and url.endswith(".woff2"):
            return url, "google"

    # --- фолбэк на локальный файл ---
    if not skip_fonts_dir_check:
        full = fonts_dir / local_path
        if not full.exists():
            print(
                f"  [warn] {slug} ({weight_label}): нет ни в Google-метаданных, "
                f"ни на диске ({full})",
                file=sys.stderr,
            )
    return local_path, "local"


def build(skip_fonts_dir_check: bool = False, use_google_cdn: bool = True, force_recompute_embeddings: bool = False) -> None:
    manifest_path = settings.fonts_full_manifest_path
    labels_path = settings.fonts_labels_path

    if not manifest_path.exists():
        raise FileNotFoundError(f"Не найден манифест: {manifest_path}")
    if not labels_path.exists():
        raise FileNotFoundError(f"Не найдена разметка: {labels_path}")

    print(f"Читаю манифест: {manifest_path}")
    manifest_records = read_jsonl(manifest_path)
    print(f"  -> {len(manifest_records)} записей")

    print(f"Читаю разметку: {labels_path}")
    label_records = read_jsonl(labels_path)
    print(f"  -> {len(label_records)} записей")

    google_by_family: dict[str, dict] = {}
    if use_google_cdn:
        metadata_path = settings.data_dir / "fonts_metadata.json"
        google_by_family = load_google_metadata(metadata_path)
        if google_by_family:
            print(f"Google Fonts метаданные: {len(google_by_family)} семейств")

    # Индексируем манифест по slug
    manifest_by_slug: dict[str, dict] = {}
    for rec in manifest_records:
        slug = rec.get("slug")
        if not slug:
            continue
        manifest_by_slug[normalize_slug(slug)] = rec

    joined: list[dict] = []
    unmatched_labels: list[str] = []

    for label_rec in label_records:
        raw_key = label_rec.get("family_name", "")
        key = normalize_slug(raw_key)
        manifest_rec = manifest_by_slug.get(key)
        if manifest_rec is None:
            unmatched_labels.append(raw_key)
            continue
        joined.append({"label": label_rec, "manifest": manifest_rec})

    print(f"Смэтчено: {len(joined)} / {len(label_records)}")
    if unmatched_labels:
        print(
            f"  [warn] {len(unmatched_labels)} записей из fonts.jsonl не нашли пару в манифесте "
            f"(первые 10): {unmatched_labels[:10]}",
            file=sys.stderr,
        )

    # --- считаем эмбеддинги, где нужно; резолвим URL шрифтов ---
    n_reused = 0
    n_computed = 0
    n_google_regular = 0
    n_google_bold = 0
    n_local_regular = 0
    n_local_bold = 0
    rows_to_insert = []

    for item in joined:
        label = item["label"]
        manifest = item["manifest"]

        slug = manifest["slug"]
        family_name = manifest.get("family_name") or label.get("family_name") or slug
        category = normalize_category(manifest.get("category"))
        subsets = manifest.get("subsets") or []
        license_ = manifest.get("license")
        is_variable = bool(manifest.get("is_variable", False))

        local_regular_path = normalize_path(manifest.get("regular", ""))
        local_bold_path = normalize_path(manifest.get("bold", ""))

        google_item = google_by_family.get(normalize_family_key(family_name))

        regular_url, regular_source = resolve_font_url(
            google_item, "regular", local_regular_path,
            settings.fonts_dir, skip_fonts_dir_check, slug, "regular",
        )
        bold_url, bold_source = resolve_font_url(
            google_item, "700", local_bold_path,
            settings.fonts_dir, skip_fonts_dir_check, slug, "bold",
        )
        n_google_regular += regular_source == "google"
        n_google_bold += bold_source == "google"
        n_local_regular += regular_source == "local"
        n_local_bold += bold_source == "local"

        mood_tags = label.get("mood_tags") or []
        industry_tags = label.get("industry_tags") or []
        description = label.get("description") or ""
        description_ru = label.get("description_ru") or None

        embedding_raw = label.get("embedding") or []
        # ВАЖНО: проверяем только размерность — но если поменяли
        # EMBEDDING_MODEL_NAME на другую модель с ТОЙ ЖЕ размерностью
        # выхода (как all-MiniLM-L6-v2 -> paraphrase-multilingual-MiniLM-
        # L12-v2, у обеих 384), эта проверка ничего не заметит и молча
        # переиспользует векторы от старой модели — они несовместимы с
        # новыми, эмбеддинги разных моделей не сравнимы косинусным
        # сходством, даже если совпадает размерность. Если модель меняли —
        # обязательно запускайте сборку с --force-recompute-embeddings.
        if not force_recompute_embeddings and len(embedding_raw) == settings.embedding_dim:
            vec = np.asarray(embedding_raw, dtype=np.float32)
            n_reused += 1
        else:
            if not description:
                print(
                    f"  [warn] {slug}: нет embedding и нет description — "
                    f"пишу нулевой вектор, шрифт не будет находиться по тексту",
                    file=sys.stderr,
                )
                vec = np.zeros(settings.embedding_dim, dtype=np.float32)
            else:
                vec = embed_text(description)
                n_computed += 1

        if vec.shape[0] != settings.embedding_dim:
            raise ValueError(
                f"{slug}: итоговая размерность эмбеддинга {vec.shape[0]} != "
                f"{settings.embedding_dim}"
            )

        needs_review = bool(label.get("needs_review", False) or manifest.get("needs_review", False))
        is_premium = bool(label.get("is_premium", False) or manifest.get("is_premium", False))
        referral_url = label.get("referral_url") or manifest.get("referral_url")

        rows_to_insert.append(
            {
                "family_name": family_name,
                "slug": slug,
                "category": category,
                "subsets": json.dumps(subsets, ensure_ascii=False),
                "license": license_,
                "is_variable": is_variable,
                "regular_woff2_path": regular_url,
                "bold_woff2_path": bold_url,
                "mood_tags": json.dumps(mood_tags, ensure_ascii=False),
                "industry_tags": json.dumps(industry_tags, ensure_ascii=False),
                "description": description,
                "description_ru": description_ru,
                "embedding": vec.tobytes(),
                "is_premium": is_premium,
                "referral_url": referral_url,
                "needs_review": needs_review,
            }
        )

    print(f"Эмбеддинги: переиспользовано {n_reused}, посчитано заново {n_computed}")
    print(
        f"Источник файлов — regular: Google CDN {n_google_regular} / локально {n_local_regular}; "
        f"bold: Google CDN {n_google_bold} / локально {n_local_bold}"
    )

    # --- пишем в sqlite ---
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.db_path.exists():
        settings.db_path.unlink()

    conn = sqlite3.connect(settings.db_path)
    try:
        conn.execute(
            """
            CREATE TABLE fonts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                category TEXT,
                subsets TEXT NOT NULL,
                license TEXT,
                is_variable BOOLEAN,
                regular_woff2_path TEXT NOT NULL,
                bold_woff2_path TEXT NOT NULL,
                mood_tags TEXT NOT NULL,
                industry_tags TEXT,
                description TEXT NOT NULL,
                description_ru TEXT,
                embedding BLOB NOT NULL,
                is_premium BOOLEAN DEFAULT 0,
                referral_url TEXT,
                needs_review BOOLEAN DEFAULT 0
            )
            """
        )
        conn.execute("CREATE INDEX idx_fonts_category ON fonts(category)")

        conn.executemany(
            """
            INSERT INTO fonts (
                family_name, slug, category, subsets, license, is_variable,
                regular_woff2_path, bold_woff2_path, mood_tags, industry_tags,
                description, description_ru, embedding, is_premium,
                referral_url, needs_review
            ) VALUES (
                :family_name, :slug, :category, :subsets, :license, :is_variable,
                :regular_woff2_path, :bold_woff2_path, :mood_tags, :industry_tags,
                :description, :description_ru, :embedding, :is_premium,
                :referral_url, :needs_review
            )
            """,
            rows_to_insert,
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Готово: {settings.db_path} ({len(rows_to_insert)} шрифтов)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-missing-fonts-dir",
        action="store_true",
        help="Не проверять наличие локальных woff2-файлов на диске при сборке",
    )
    parser.add_argument(
        "--no-google-cdn",
        action="store_true",
        help="Игнорировать data/fonts_metadata.json, всегда использовать локальные файлы",
    )
    parser.add_argument(
        "--force-recompute-embeddings",
        action="store_true",
        help=(
            "Игнорировать закэшированные embedding в fonts.jsonl, считать заново для ВСЕХ "
            "записей. Обязательно после смены EMBEDDING_MODEL_NAME — иначе при совпадении "
            "размерности со старой моделью скрипт молча оставит несовместимые векторы."
        ),
    )
    args = parser.parse_args()
    build(
        skip_fonts_dir_check=args.skip_missing_fonts_dir,
        use_google_cdn=not args.no_google_cdn,
        force_recompute_embeddings=args.force_recompute_embeddings,
    )
