"""
Конфигурация приложения. Всё читается из .env — ничего не хардкодится
(см. раздел 11 ТЗ: "Конфигурация").

ВАЖНО: все пути в .env — ОТНОСИТЕЛЬНЫЕ пути, но резолвятся не относительно
текущей директории запуска (cwd), а относительно корня проекта (папка, где
лежит .env — на уровень выше backend/). Это специально сделано, чтобы
`uvicorn main:app` из backend/ и `python backend/build_database.py` из
корня проекта одинаково находили /data и /fonts, а не падали с
"файл не найден" в зависимости от того, откуда запущена команда.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/config.py -> подняться на уровень выше = корень проекта
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv()

def _resolve(v: Path) -> Path:
    """Относительный путь резолвится от PROJECT_ROOT, абсолютный — как есть."""
    v = Path(v)
    return v if v.is_absolute() else (PROJECT_ROOT / v).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Paths (относительны PROJECT_ROOT, см. докстринг модуля) ---
    data_dir: Path = Path("./data")
    fonts_dir: Path = Path("./fonts")
    frontend_dir: Path = Path("./frontend")
    db_path: Path = Path("./backend/fonts.db")
    synonyms_path: Path = Path("./data/synonyms.json")
    fonts_full_manifest_path: Path = Path("./data/fonts_full_manifest.jsonl")
    fonts_labels_path: Path = Path("./data/fonts.jsonl")

    # --- Embedding model ---
    embedding_model_name: str = os.getenv('EMBEDDING_MODEL_NAME')  # 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'  # "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # --- Scoring weights (section 7.5) ---
    weight_tags: float = 0.45
    weight_embedding: float = 0.45
    weight_premium_bonus: float = 0.10

    # --- Search cache ---
    search_cache_ttl_seconds: int = 900
    search_page_size: int = 10

    # --- CORS ---
    cors_origins: str = "*"

    # --- Static ---
    static_fonts_url_prefix: str = "/static/fonts"

    @field_validator(
        "data_dir", "fonts_dir", "frontend_dir", "db_path", "synonyms_path",
        "fonts_full_manifest_path", "fonts_labels_path",
        mode="after",
    )
    @classmethod
    def _anchor_to_project_root(cls, v: Path) -> Path:
        return _resolve(v)

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# Singleton, импортируется во всех модулях бэкенда
settings = Settings()