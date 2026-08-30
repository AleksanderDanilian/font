# Деплой на VPS (Docker + Caddy)

Схема: один контейнер с приложением (FastAPI-бэкенд, он же отдаёт
фронтенд — см. `main.py`) + Caddy перед ним для авто-HTTPS. Данные шрифтов
(`data/`, `fonts/`, сама `fonts.db`) живут в volume'ах, не в образе — код
и данные обновляются независимо друг от друга.

## 0. Предварительно

- VPS с Docker + Docker Compose (`apt install docker.io docker-compose-plugin`, либо по [офиц. инструкции](https://docs.docker.com/engine/install/))
- Домен, A-запись которого указывает на IP вашего VPS (в Cloudflare — можно
  сразу с оранжевым облаком/проксированием, Caddy получит сертификат через
  HTTP-01 challenge, который Cloudflare пропускает по умолчанию)
- Клонированный/скопированный на сервер этот проект целиком

## 1. Конфигурация

```bash
cp .env.example .env
nano .env   # минимум: укажите DOMAIN=ваш-домен.ру
```

Остальные переменные в `.env` можно оставить дефолтными — `docker-compose.yml`
прокидывает их в контейнер приложения явно через `environment:` (сам `.env`
контейнер не монтирует и не читает — так принято в Docker, см. комментарии
в `docker-compose.yml`).

## 2. Первый запуск

```bash
docker compose up -d --build
```

Первая сборка образа дольше обычного — модель эмбеддингов
(`sentence-transformers/all-MiniLM-L6-v2`, ~90MB) скачивается и кэшируется
прямо в образ на этапе `docker build`, чтобы контейнер не лез в интернет за
ней при каждом старте.

При самом первом старте контейнера (когда `db_data` volume ещё пустой)
`entrypoint.sh` сам запустит `build_database.py` перед стартом сервера —
это может занять время, если у эмбеддингов из `data/fonts.jsonl` не для
всех шрифтов посчитан `embedding` заранее (досчитывает на лету). Смотрите
прогресс:

```bash
docker compose logs -f app
```

## 3. Проверка

```bash
curl -I https://ваш-домен.ру/api/tags
```

Должно быть `200 OK`. Откройте `https://ваш-домен.ру/` в браузере —
получите `index.html` (или другой вариант дизайна — `/index_3.html` и т.д.,
см. README про layout variants).

## 4. Обновление данных (`data/`, `fonts/`) без пересборки образа

Раз `data/` и `fonts/` — bind mount на хостовые директории, а не часть
образа, обновлять их можно прямо на сервере (через `scp`/`rsync`/git pull
в отдельном репо с данными — как вам удобнее), а затем пересобрать БД
**внутри уже работающего контейнера**, без `docker compose build`:

```bash
docker compose exec app python build_database.py
docker compose restart app   # чтобы FontStore перечитал БД в память — см. db.py, грузится при старте
```

Сюда же относится: обновили `synonyms.json`, перегенерировали `description`
через `enrich_descriptions.py`, обновили `fonts_metadata.json` через
`fetch_google_fonts_metadata.py` — во всех случаях та же команда.

## 5. Обновление кода (после `git pull` / правок в `backend/` или `frontend/`)

```bash
docker compose up -d --build app
```

Данные (`data/`, `fonts/`, `fonts.db` в volume `db_data`) не затрагиваются —
пересобирается только код.

## 6. Бэкапы

Единственное, что реально стоит бэкапить регулярно — `data/` (исходная
разметка, которую жалко потерять) и, при желании, сам volume `db_data`
(хотя её всегда можно пересобрать заново командой из шага 4, если жалко
только времени на пересчёт эмбеддингов):

```bash
docker run --rm -v fontasize_db_data:/db -v $(pwd):/backup alpine \
  tar czf /backup/fonts_db_backup.tar.gz -C /db .
```

(имя volume может отличаться — `docker volume ls`, обычно
`<имя-папки-проекта>_db_data`)

## Диагностика

- **502/503 от Caddy** — приложение ещё не готово (не прошло `HEALTHCHECK`)
  или упало при старте. `docker compose logs app` — почти всегда там будет
  явная причина (например, `fonts.db` не собралась из-за отсутствия
  `data/fonts.jsonl`).
- **Сертификат не выпускается** — проверьте, что DNS-запись домена уже
  указывает на IP сервера (`dig +short ваш-домен.ру`) и что 80/443 порты
  реально доступны снаружи (не заблокированы firewall/security group
  провайдера).
- **`/api/fonts/search/{id}/more` иногда 404 "истёк"** — если вы вручную
  меняли `--workers` в `entrypoint.sh` на больше 1, верните обратно.
  Поисковый кэш — в памяти одного процесса, см. комментарий в `Dockerfile`.


rsync -avz --delete \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='venv' \
  --exclude='.venv' \
  --exclude='preview' \
  ./ deploy@49.12.190.47:/opt/fontasize/

wsl rsync -avz --delete --exclude='.git' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='venv' --exclude='.venv' --exclude='preview' /mnt/c/Users/Alex/PycharmProjects/fontosyntez/ deploy@49.12.190.47:/opt/fontasize/
