"""
Pydantic-схемы запросов/ответов API (раздел 7 ТЗ).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------- /api/tags ----------

class TagOut(BaseModel):
    id: str
    label_en: str
    label_ru: str
    excludes: list[str] = Field(default_factory=list)


class TagsResponse(BaseModel):
    tags: list[TagOut]


# ---------- /api/languages ----------

class LanguageOut(BaseModel):
    code: str
    label: str


class LanguagesResponse(BaseModel):
    languages: list[LanguageOut]


# ---------- /api/fonts/search ----------

class SearchRequest(BaseModel):
    text: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    languages: list[str] = Field(min_length=1)
    preview_text: Optional[str] = None

    @field_validator("languages")
    @classmethod
    def languages_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("languages must contain at least one element")
        return v

    @field_validator("tags")
    @classmethod
    def max_four_tags(cls, v: list[str]) -> list[str]:
        # Бэкенд не полагается на фронт в вопросе валидации количества тегов —
        # дублируем ограничение раздела 2 ТЗ ("до 4 тегов одновременно").
        if len(v) > 4:
            raise ValueError("no more than 4 tags allowed")
        return v


class FontOut(BaseModel):
    family_name: str
    slug: str
    category: Optional[str] = None
    regular_woff2_url: str
    bold_woff2_url: str
    mood_tags: list[str]
    is_premium: bool
    referral_url: Optional[str] = None


class SearchResponse(BaseModel):
    search_id: str
    fonts: list[FontOut]
    has_more: bool


class MoreResponse(BaseModel):
    fonts: list[FontOut]
    has_more: bool
