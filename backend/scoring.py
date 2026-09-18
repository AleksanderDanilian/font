"""
Скоринг шрифтов (раздел 7.5 ТЗ).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FontRecord:
    id: int
    family_name: str
    slug: str
    category: str | None
    subsets: list[str]
    mood_tags: list[str]
    is_premium: bool
    referral_url: str | None
    is_google_font: bool
    regular_woff2_path: str
    bold_woff2_path: str
    embedding_row: int


def cosine_similarity_matrix(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q_norm = np.linalg.norm(query_vec)
    if q_norm == 0:
        return np.zeros(matrix.shape[0], dtype=np.float32)
    q_normalized = query_vec / q_norm
    return matrix @ q_normalized


def tag_overlap_ratio(query_tags: list[str], font_mood_tags: list[str]) -> float:
    if not query_tags:
        return 0.0
    q = set(query_tags)
    f = set(font_mood_tags)
    return len(q & f) / len(q)


def score_fonts(
    query_tags: list[str],
    query_embedding: np.ndarray | None,
    fonts: list[FontRecord],
    embedding_matrix: np.ndarray,
    weight_tags: float = 0.45,
    weight_embedding: float = 0.45,
    weight_premium_bonus: float = 0.10,
) -> list[tuple[FontRecord, float]]:
    if query_embedding is not None:
        cos_sims = cosine_similarity_matrix(query_embedding, embedding_matrix)
    else:
        cos_sims = None

    results: list[tuple[FontRecord, float]] = []
    for font in fonts:
        tag_score = tag_overlap_ratio(query_tags, font.mood_tags)
        emb_score = float(cos_sims[font.embedding_row]) if cos_sims is not None else 0.0
        premium_score = 1.0 if font.is_premium else 0.0

        score = (
            weight_tags * tag_score
            + weight_embedding * emb_score
            + weight_premium_bonus * premium_score
        )
        results.append((font, score))

    results.sort(key=lambda pair: pair[1], reverse=True)
    return results