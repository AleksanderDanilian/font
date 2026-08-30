"""
ТЕСТОВЫЙ СТАБ, НЕ ЧАСТЬ ПРОЕКТА.
Т.к. в этой песочнице нет доступа к huggingface.co, реальную модель
all-MiniLM-L6-v2 скачать нельзя. Этот стаб даёт детерминированный
псевдо-эмбеддинг (хэш текста -> вектор), чтобы протестировать логику
build_database.py / main.py (join, sqlite, scoring, API) end-to-end.
На реальном проекте пользователь ставит настоящий sentence-transformers
из requirements.txt, этот файл не используется.
"""
import hashlib
import numpy as np


class SentenceTransformer:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def encode(self, text, normalize_embeddings: bool = False):
        h = hashlib.sha256(text.encode("utf-8")).digest()
        rng = np.random.default_rng(int.from_bytes(h[:8], "little"))
        vec = rng.normal(size=384).astype(np.float32)
        if normalize_embeddings:
            vec = vec / np.linalg.norm(vec)
        return vec
