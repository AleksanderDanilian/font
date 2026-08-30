#!/usr/bin/env bash
# Запуск скачивания шрифтов.
#
# Запускать можно из ЛЮБОЙ директории — скрипт сам переходит в корень
# проекта (там, где лежит этот файл), поэтому файлы всегда сохраняются
# в data/ и fonts/ внутри проекта, и никакие лишние папки в других местах
# не создаются.
#
# Примеры:
#   ./run_download.sh --families "Montserrat,Pacifico"
#   ./run_download.sh --families-file data/families.txt
#   ./run_download.sh --rebuild-from-disk

set -euo pipefail

# Переходим в директорию, где лежит сам скрипт (= корень проекта)
cd "$(dirname "${BASH_SOURCE[0]}")"

# Создаём/активируем виртуальное окружение (один раз)
if [ ! -d ".venv" ]; then
    echo "→ Создаю виртуальное окружение .venv ..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
else
    source .venv/bin/activate
fi

python3 src/download_fonts.py "$@"
