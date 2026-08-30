"""
Скоринг шрифтов (раздел 7.5 ТЗ).

Решение по открытому вопросу "эмбеддинг тегов без текста" (раздел 7.5 /
раздел 13.3): выбран вариант (а) — если пользователь не ввёл текст,
query_embedding = None и вклад weight_embedding обнуляется сам по формуле.
Шаблонная фраза из тегов НЕ строится.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class FontRecord:
    id: int
    family_name: str
    slug: str
    category: Optional[str]
    subsets: list[str]
    mood_tags: list[str]
    is_premium: bool
    referral_url: Optional[str]
    regular_woff2_path: str
    bold_woff2_path: str
    # embedding хранится отдельно, в общей матрице (N, dim) — см. db.py.
    # Здесь только индекс строки в этой матрице.
    embedding_row: int


def cosine_similarity_matrix(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """
    query_vec: (dim,) — эмбеддинг запроса.
    matrix: (N, dim) — эмбеддинги всех шрифтов (уже L2-нормализованные при
        загрузке в db.py, см. load_embeddings()).
    Возвращает (N,) массив косинусных сходств.
    """
    q_norm = np.linalg.norm(query_vec)
    if q_norm == 0:
        return np.zeros(matrix.shape[0], dtype=np.float32)
    q_normalized = query_vec / q_norm
    # matrix уже нормализована построчно -> скалярное произведение = cos sim
    return matrix @ q_normalized


def tag_overlap_ratio(query_tags: list[str], font_mood_tags: list[str]) -> float:
    if not query_tags:
        return 0.0
    q = set(query_tags)
    f = set(font_mood_tags)
    return len(q & f) / len(q)


def score_fonts(
    query_tags: list[str],
    query_embedding: Optional[np.ndarray],
    fonts: list[FontRecord],
    embedding_matrix: np.ndarray,
    weight_tags: float = 0.45,
    weight_embedding: float = 0.45,
    weight_premium_bonus: float = 0.10,
) -> list[tuple[FontRecord, float]]:
    """
    score = weight_tags * tag_overlap_ratio
          + weight_embedding * cosine_similarity
          + weight_premium_bonus * (1 if font.is_premium else 0)

    Веса передаются параметрами (не хардкод) — см. раздел 7.5 ТЗ,
    "КЛЮЧЕВОЕ ТРЕБОВАНИЕ".

    embedding_matrix — полная (N, dim) матрица эмбеддингов всех шрифтов в БД
    (в том же порядке индексов, что font.embedding_row). Косинусное сходство
    считается матричным умножением, не через SQL (см. раздел 6 ТЗ).
    """
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
