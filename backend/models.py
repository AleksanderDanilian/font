"""
Pydantic-схемы запросов/ответов API (раздел 7 ТЗ).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TagOut(BaseModel):
    id: str
    label_en: str
    label_ru: str
    excludes: list[str] = Field(default_factory=list)


class TagsResponse(BaseModel):
    tags: list[TagOut]


class LanguageOut(BaseModel):
    code: str
    label: str


class LanguagesResponse(BaseModel):
    languages: list[LanguageOut]


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
        if len(v) > 4:
            raise ValueError("no more than 4 tags allowed")
        return v


class FontOut(BaseModel):
    family_name: str
    slug: str
    category: Optional[str]
    regular_woff2_url: str
    bold_woff2_url: str
    mood_tags: list[str]
    is_premium: bool
    referral_url: Optional[str] = None
    # --- ссылка на источник (см. чат про "download links") ---
    # source_url: либо явный referral_url (premium/affiliate), либо
    # автосгенерированная ссылка на fonts.google.com/specimen/... для
    # подтверждённых Google-шрифтов, либо None.
    source_url: Optional[str] = None
    # True, если source_url пришёл из referral_url (монетизируемая/партнёрская
    # ссылка — нужен rel="sponsored nofollow" на фронте). False для
    # обычной ссылки на специмен-страницу Google Fonts (это не аффилиэйт,
    # nofollow ей не нужен и даже вреден для SEO).
    source_is_affiliate: bool = False


class SearchResponse(BaseModel):
    search_id: str
    fonts: list[FontOut]
    has_more: bool


class MoreResponse(BaseModel):
    fonts: list[FontOut]
    has_more: bool