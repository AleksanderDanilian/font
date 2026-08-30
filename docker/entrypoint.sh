#!/bin/sh
# Точка входа контейнера.
#
# Если backend/fonts.db ещё нет (первый запуск на чистом volume, или volume
# с data/ обновили, но забыли пересобрать) — собираем её сами перед стартом
# сервера, чтобы `docker compose up` сразу заработал "из коробки". Если
# fonts.db уже есть — НЕ трогаем её (пересборка — это отдельный осознанный
# шаг, см. DEPLOY.md, не побочный эффект перезапуска контейнера).
set -e

DB_PATH="${DB_PATH:-/app/backend/fonts.db}"

BUILD_ARGS=""
if [ "${FORCE_RECOMPUTE_EMBEDDINGS:-0}" = "1" ]; then
    echo "[entrypoint] FORCE_RECOMPUTE_EMBEDDINGS=1 — пересчитываю все эмбеддинги заново."
    BUILD_ARGS="--force-recompute-embeddings"
fi

if [ ! -f "$DB_PATH" ]; then
    echo "[entrypoint] $DB_PATH не найден — собираю базу перед стартом (первый запуск)..."
    python build_database.py $BUILD_ARGS
else
    echo "[entrypoint] $DB_PATH уже существует, пропускаю сборку (см. DEPLOY.md, как пересобрать вручную)."
fi

echo "[entrypoint] Старт сервера..."
# --workers 1 намеренно, см. комментарий в Dockerfile.
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1