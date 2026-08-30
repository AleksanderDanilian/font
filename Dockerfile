# syntax=docker/dockerfile:1

# ==============================================================================
# Font Matcher — production image.
#
# Важные решения, зафиксированные тут намеренно (не менять не разобравшись):
#
# 1. WORKDIR = /app/backend, а не /app. backend/*.py написаны с плоскими
#    импортами ("from config import settings", а не "from .config import
#    settings" / "from backend.config import settings") — это значит, что
#    backend/ должен быть КОРНЕМ sys.path. Если запускать как "uvicorn
#    backend.main:app" из /app — упадёт с ModuleNotFoundError: No module
#    named 'config' (проверено). Правильно — "uvicorn main:app" из /app/backend.
#
# 2. --workers 1 в CMD — не опечатка и не временное решение. FontStore
#    (эмбеддинги всех шрифтов) и search_cache грузятся/живут В ПАМЯТИ
#    ПРОЦЕССА (см. main.py/db.py) — не в Redis и не в БД. Несколько
#    воркеров = несколько независимых копий кэша поиска, из-за чего
#    /api/fonts/search/{id}/more будет случайно возвращать 404 "истёк",
#    если запрос попадёт в другой процесс. При вашей нагрузке (1-2 тыс.
#    визитов/день) один процесс на asyncio спокойно тянет всё — это не
#    предел производительности, а осознанное архитектурное ограничение.
#
# 3. Модель эмбеддингов (sentence-transformers/all-MiniLM-L6-v2, см.
#    EMBEDDING_MODEL_NAME в .env) скачивается и кэшируется ПРЯМО В ОБРАЗ на
#    этапе сборки — чтобы контейнер не лез в интернет за моделью при
#    каждом старте (и не падал, если сеть недоступна/HuggingFace лежит).
# ==============================================================================

FROM python:3.11-slim AS base

# HF_HOME — куда sentence-transformers кладёт скачанную модель; фиксируем
# путь, чтобы предзагрузка на этапе сборки и рантайм смотрели в одно место.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# Системные зависимости: curl нужен для HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# --- Python-зависимости отдельным слоем (кэшируется, пока requirements.txt не меняется) ---
COPY requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# --- Предзагрузка embedding-модели в образ ---
# ARG, а не ENV — значение видно только на этапе сборки; сама модель имени
# читается из .env через сам build_database.py в рантайме, тут дублируем
# дефолт из .env.example специально, чтобы кэш модели точно совпал с тем,
# что реально запросит EMBEDDING_MODEL_NAME. Если меняете модель в .env —
# передайте новое имя через --build-arg EMBEDDING_MODEL_NAME=...
ARG EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL_NAME}')"

# --- Код приложения ---
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# data/ и fonts/ НЕ копируются в образ — это volume'ы (см. docker-compose.yml).
# Они меняются независимо от кода (разметка шрифтов, локальные фолбэк-файлы,
# сама fonts.db) и не должны требовать пересборки образа при каждом
# обновлении данных. Создаём пустые директории, чтобы volume было куда
# монтировать даже при самом первом запуске.
RUN mkdir -p /app/data /app/fonts

# --- Непривилегированный пользователь ---
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/tags || exit 1

WORKDIR /app/backend
ENTRYPOINT ["/app/entrypoint.sh"]
