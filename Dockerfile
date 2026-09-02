# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# System dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        # Add these if sentence-transformers still has issues:
        # build-essential \
        # python3-dev \
    && rm -rf /var/lib/apt/lists/*

# --- CRITICAL: Install CPU-only PyTorch FIRST ---
# This prevents pip from installing the GPU version with sentence-transformers
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# --- Python dependencies ---
COPY requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# --- Pre-download embedding model ---
ARG EMBEDDING_MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL_NAME}')"

# --- Application code ---
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create directories for volumes
RUN mkdir -p /app/data /app/fonts

# --- Non-privileged user ---
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app

RUN mkdir -p /app/db && chown appuser:appuser /app/db

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/tags || exit 1

WORKDIR /app/backend
ENTRYPOINT ["/app/entrypoint.sh"]