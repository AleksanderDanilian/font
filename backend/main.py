"""
FastAPI-приложение (раздел 7 ТЗ).
"""
from __future__ import annotations

import json
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from db import FontStore
from models import (
    FontOut,
    LanguageOut,
    LanguagesResponse,
    MoreResponse,
    SearchRequest,
    SearchResponse,
    TagOut,
    TagsResponse,
)
from scoring import score_fonts
from text_parser import SynonymMatcher, load_synonyms

LANGUAGE_LABELS: dict[str, str] = {
    "latin": "English / Latin",
    "latin-ext": "Latin Extended",
    "cyrillic": "Cyrillic (Russian, etc.)",
    "cyrillic-ext": "Cyrillic Extended",
    "greek": "Greek",
    "greek-ext": "Greek Extended",
    "vietnamese": "Vietnamese",
    "arabic": "Arabic",
    "hebrew": "Hebrew",
    "devanagari": "Devanagari",
    "thai": "Thai",
    "korean": "Korean",
    "japanese": "Japanese",
    "chinese-simplified": "Chinese (Simplified)",
    "chinese-traditional": "Chinese (Traditional)",
    "chinese-hongkong": "Chinese (Hong Kong)",
    "tamil": "Tamil",
    "bengali": "Bengali",
    "menu": "Menu (служебный, не для контента)",
}

store = FontStore(db_path=settings.db_path, embedding_dim=settings.embedding_dim)
tags_data: list[dict] = []
synonym_matcher: SynonymMatcher | None = None
search_cache: dict[str, dict] = {}

_embedding_model = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(settings.embedding_model_name)
    return _embedding_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tags_data, synonym_matcher

    store.load_all()

    tags_path = settings.data_dir / "tags.json"
    with open(tags_path, "r", encoding="utf-8") as f:
        tags_data = json.load(f)

    synonyms = load_synonyms(settings.synonyms_path)
    synonym_matcher = SynonymMatcher(synonyms)

    print(f"Загружено {len(store.fonts)} шрифтов, {len(tags_data)} тегов.")
    yield


app = FastAPI(title="Fontasize API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    settings.static_fonts_url_prefix,
    StaticFiles(directory=settings.fonts_dir),
    name="static-fonts",
)


def _clean_expired_cache() -> None:
    now = time.time()
    expired = [
        sid for sid, entry in search_cache.items()
        if now - entry["created_at"] > settings.search_cache_ttl_seconds
    ]
    for sid in expired:
        del search_cache[sid]


def _resolve_font_url(path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return f"{settings.static_fonts_url_prefix}/{path_or_url}"


def _google_specimen_url(family_name: str) -> str:
    """https://fonts.google.com/specimen/Roboto+Mono — пробелы на "+"."""
    return f"https://fonts.google.com/specimen/{family_name.strip().replace(' ', '+')}"


def _font_to_out(font) -> FontOut:
    # source_url: явный referral_url (premium/affiliate) побеждает всегда;
    # иначе, если шрифт подтверждённо с Google Fonts (is_google_font,
    # проставлен в build_database.py по факту найденной записи в
    # fonts_metadata.json, а не по URL самого файла) — автогенерируем
    # ссылку на специмен-страницу; иначе ссылки нет.
    if font.referral_url:
        source_url = font.referral_url
        source_is_affiliate = True
    elif font.is_google_font:
        source_url = _google_specimen_url(font.family_name)
        source_is_affiliate = False
    else:
        source_url = None
        source_is_affiliate = False

    return FontOut(
        family_name=font.family_name,
        slug=font.slug,
        category=font.category,
        regular_woff2_url=_resolve_font_url(font.regular_woff2_path),
        bold_woff2_url=_resolve_font_url(font.bold_woff2_path),
        mood_tags=font.mood_tags,
        is_premium=font.is_premium,
        referral_url=font.referral_url,
        source_url=source_url,
        source_is_affiliate=source_is_affiliate,
    )


@app.get("/api/tags", response_model=TagsResponse)
def get_tags():
    return TagsResponse(tags=[TagOut(**t) for t in tags_data])


@app.get("/api/languages", response_model=LanguagesResponse)
def get_languages():
    codes = store.available_languages()
    languages = [
        LanguageOut(code=code, label=LANGUAGE_LABELS.get(code, code.replace("-", " ").title()))
        for code in codes
    ]
    return LanguagesResponse(languages=languages)


@app.post("/api/fonts/search", response_model=SearchResponse)
def search_fonts(req: SearchRequest):
    _clean_expired_cache()

    candidates = store.filter_by_languages(req.languages)

    query_tags = list(req.tags)
    if req.text and synonym_matcher is not None:
        text_tags = synonym_matcher.extract_tags(req.text)
        for t in text_tags:
            if t not in query_tags:
                query_tags.append(t)

    query_embedding = None
    if req.text and req.text.strip():
        model = get_embedding_model()
        vec = model.encode(req.text, normalize_embeddings=False)
        import numpy as np
        query_embedding = np.asarray(vec, dtype="float32")

    scored = score_fonts(
        query_tags=query_tags,
        query_embedding=query_embedding,
        fonts=candidates,
        embedding_matrix=store.embedding_matrix,
        weight_tags=settings.weight_tags,
        weight_embedding=settings.weight_embedding,
        weight_premium_bonus=settings.weight_premium_bonus,
    )

    ordered_ids = [font.id for font, _score in scored]

    search_id = secrets.token_hex(8)
    search_cache[search_id] = {"ordered_ids": ordered_ids, "created_at": time.time()}

    page_size = settings.search_page_size
    page_ids = ordered_ids[:page_size]
    fonts_out = [_font_to_out(store.by_id[fid]) for fid in page_ids]

    return SearchResponse(
        search_id=search_id,
        fonts=fonts_out,
        has_more=len(ordered_ids) > page_size,
    )


@app.get("/api/fonts/search/{search_id}/more", response_model=MoreResponse)
def more_fonts(search_id: str, offset: int = 10):
    _clean_expired_cache()

    entry = search_cache.get(search_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "search_expired",
                "message": "Результаты поиска устарели или сервер перезапускался. Повторите Apply.",
            },
        )

    ordered_ids = entry["ordered_ids"]
    page_size = settings.search_page_size
    page_ids = ordered_ids[offset: offset + page_size]
    fonts_out = [_font_to_out(store.by_id[fid]) for fid in page_ids if fid in store.by_id]

    return MoreResponse(
        fonts=fonts_out,
        has_more=(offset + page_size) < len(ordered_ids),
    )


if settings.frontend_dir.exists():
    app.mount(
        "/",
        StaticFiles(directory=settings.frontend_dir, html=True),
        name="frontend",
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8010, reload=True)
