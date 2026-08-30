"""
Доступ к SQLite + загрузка эмбеддингов в память (раздел 6 ТЗ).

При старте приложения (см. main.py -> lifespan) вызывается load_all(),
которая читает всю таблицу fonts (кроме needs_review=1) и строит:
  - self.fonts: list[FontRecord]
  - self.embedding_matrix: np.ndarray (N, dim), L2-нормализованная построчно
  - self.by_id: dict[int, FontRecord]

Матрица нормализуется один раз при загрузке, чтобы cosine_similarity_matrix
в scoring.py сводился к простому матричному умножению.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from scoring import FontRecord


class FontStore:
    def __init__(self, db_path: Path, embedding_dim: int):
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        self.fonts: list[FontRecord] = []
        self.embedding_matrix: np.ndarray = np.zeros((0, embedding_dim), dtype=np.float32)
        self.by_id: dict[int, FontRecord] = {}
        self._all_subsets: set[str] = set()

    def load_all(self) -> None:
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"БД не найдена по пути {self.db_path}. "
                "Сначала запустите build_database.py."
            )

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT id, family_name, slug, category, subsets, mood_tags,
                       is_premium, referral_url, regular_woff2_path,
                       bold_woff2_path, embedding
                FROM fonts
                WHERE needs_review = 0
                ORDER BY id
                """
            ).fetchall()
        finally:
            conn.close()

        fonts: list[FontRecord] = []
        vectors: list[np.ndarray] = []
        all_subsets: set[str] = set()

        for row_idx, row in enumerate(rows):
            subsets = json.loads(row["subsets"]) if row["subsets"] else []
            mood_tags = json.loads(row["mood_tags"]) if row["mood_tags"] else []
            all_subsets.update(subsets)

            vec = np.frombuffer(row["embedding"], dtype=np.float32)
            if vec.shape[0] != self.embedding_dim:
                raise ValueError(
                    f"Font id={row['id']} slug={row['slug']}: embedding dim "
                    f"{vec.shape[0]} != expected {self.embedding_dim}"
                )
            norm = np.linalg.norm(vec)
            normalized = vec / norm if norm > 0 else vec

            font = FontRecord(
                id=row["id"],
                family_name=row["family_name"],
                slug=row["slug"],
                category=row["category"],
                subsets=subsets,
                mood_tags=mood_tags,
                is_premium=bool(row["is_premium"]),
                referral_url=row["referral_url"],
                regular_woff2_path=row["regular_woff2_path"],
                bold_woff2_path=row["bold_woff2_path"],
                embedding_row=row_idx,
            )
            fonts.append(font)
            vectors.append(normalized)

        self.fonts = fonts
        self.embedding_matrix = (
            np.stack(vectors).astype(np.float32)
            if vectors
            else np.zeros((0, self.embedding_dim), dtype=np.float32)
        )
        self.by_id = {f.id: f for f in fonts}
        self._all_subsets = all_subsets

    def filter_by_languages(self, languages: list[str]) -> list[FontRecord]:
        """Шрифт проходит, если ВСЕ запрошенные subset'ы входят в font.subsets
        (раздел 7.3, шаг 1)."""
        required = set(languages)
        return [f for f in self.fonts if required.issubset(set(f.subsets))]

    def available_languages(self) -> list[str]:
        return sorted(self._all_subsets)
