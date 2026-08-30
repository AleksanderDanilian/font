"""
Парсинг свободного текста пользователя в mood/industry-теги через словарь
синонимов (раздел 4.3 ТЗ). Словарь лежит в data/synonyms.json — не хардкод,
пополняется без деплоя.

Используется в /api/fonts/search: текст пользователя дополнительно
матчится на теги (в т.ч. industry-теги, которые не показываются в UI, но
участвуют в скоринге через query_tags).
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def load_synonyms(path: Path) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class SynonymMatcher:
    """Простой матчер по вхождению подстроки (case-insensitive), без
    NLP/стемминга — достаточно для MVP согласно ТЗ (раздел 4.3: "стартовый
    набор на 15-20 записей на тег достаточно для MVP")."""

    def __init__(self, synonyms: dict[str, list[str]]):
        self.synonyms = synonyms

    def extract_tags(self, text: str) -> list[str]:
        if not text:
            return []
        normalized = text.lower()
        found: list[str] = []
        for tag_id, phrases in self.synonyms.items():
            for phrase in phrases:
                # \b работает не идеально для кириллицы в некоторых re-реализациях,
                # поэтому используем простой поиск подстроки с учётом границ пробелов.
                pattern = r"(?<![а-яa-z0-9])" + re.escape(phrase.lower()) + r"(?![а-яa-z0-9])"
                if re.search(pattern, normalized):
                    found.append(tag_id)
                    break
        return found
