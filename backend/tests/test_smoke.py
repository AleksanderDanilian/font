"""
Смоук-тест сквозного пайплайна: build_database.py -> main.py (API),
на маленьком наборе фикстур (4 шрифта) и БЕЗ сети — sentence-transformers
подменяется стабом (stub_sentence_transformers.py), т.к. реальная модель
качается с huggingface.co и в CI/песочнице без сети это недоступно.

Реальный проект должен использовать настоящий sentence-transformers из
requirements.txt — стаб нужен только для быстрой проверки логики.

Пути передаются через переменные окружения, а не через .env-файл: начиная
с версии config.py, где относительные пути из .env резолвятся к реальному
PROJECT_ROOT на диске (см. докстринг config.py), подсунуть временный .env
во временную tmp-папку и заставить его прочитаться вместо настоящего уже
нельзя. Env-переменные читаются pydantic-settings с приоритетом над .env
в любом случае, и, будучи уже абсолютными путями, проходят валидатор
_anchor_to_project_root без изменений.

Запуск:
    cd backend
    PYTHONPATH=. python -m pytest tests/test_smoke.py -v
"""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Собирает временный проект: data/ + fonts/, копирует фикстуры,
    создаёт dummy woff2-файлы по путям из манифеста."""
    root = tmp_path_factory.mktemp("project")
    (root / "data").mkdir()
    (root / "fonts").mkdir()
    (root / "backend").mkdir()

    shutil.copy(FIXTURES / "fonts_full_manifest.jsonl", root / "data" / "fonts_full_manifest.jsonl")
    shutil.copy(FIXTURES / "fonts.jsonl", root / "data" / "fonts.jsonl")
    shutil.copy(Path(__file__).parents[2] / "data" / "tags.json", root / "data" / "tags.json")
    shutil.copy(Path(__file__).parents[2] / "data" / "synonyms.json", root / "data" / "synonyms.json")

    manifest = [json.loads(l) for l in open(FIXTURES / "fonts_full_manifest.jsonl", encoding="utf-8")]
    for rec in manifest:
        for key in ("regular", "bold"):
            rel = rec[key].replace("\\", "/")
            if rel.startswith("fonts/"):
                rel = rel[len("fonts/"):]
            p = root / "fonts" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()

    return root


def _set_env(monkeypatch, project_root: Path):
    monkeypatch.setenv("DATA_DIR", str(project_root / "data"))
    monkeypatch.setenv("FONTS_DIR", str(project_root / "fonts"))
    monkeypatch.setenv("DB_PATH", str(project_root / "backend" / "fonts.db"))
    monkeypatch.setenv("SYNONYMS_PATH", str(project_root / "data" / "synonyms.json"))
    monkeypatch.setenv("FONTS_FULL_MANIFEST_PATH", str(project_root / "data" / "fonts_full_manifest.jsonl"))
    monkeypatch.setenv("FONTS_LABELS_PATH", str(project_root / "data" / "fonts.jsonl"))
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "stub-model")
    monkeypatch.setenv("EMBEDDING_DIM", "384")


def _install_stub_embedder():
    """Регистрирует стаб под именем "sentence_transformers" напрямую в
    sys.modules — реальный пакет не установлен/недоступен в тестовом
    окружении без сети до huggingface.co."""
    stub_path = Path(__file__).parent / "stub_sentence_transformers.py"
    spec = importlib.util.spec_from_file_location("sentence_transformers", stub_path)
    stub_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stub_module)
    sys.modules["sentence_transformers"] = stub_module


def test_build_and_search(project, monkeypatch):
    monkeypatch.chdir(project)
    _set_env(monkeypatch, project)
    _install_stub_embedder()

    # backend/-модули читают config.settings при импорте — форсируем
    # свежий импорт, чтобы подхватить env-переменные, выставленные выше.
    for mod in ("config", "build_database", "db", "scoring", "models", "text_parser", "main"):
        sys.modules.pop(mod, None)

    import build_database
    build_database.build(skip_fonts_dir_check=False)
    assert (project / "backend" / "fonts.db").exists()

    from fastapi.testclient import TestClient
    import main as main_module

    with TestClient(main_module.app) as client:
        r = client.get("/api/tags")
        assert r.status_code == 200
        assert len(r.json()["tags"]) == 14

        r = client.get("/api/languages")
        assert r.status_code == 200
        codes = {l["code"] for l in r.json()["languages"]}
        assert "latin" in codes and "cyrillic" in codes

        r = client.post("/api/fonts/search", json={
            "text": "elegant luxury wedding brand",
            "tags": [],
            "languages": ["latin"],
        })
        assert r.status_code == 200
        body = r.json()
        assert len(body["fonts"]) > 0
        assert "search_id" in body

        r = client.post("/api/fonts/search", json={
            "tags": ["corporate", "cold"],
            "languages": ["latin", "cyrillic"],
        })
        assert r.status_code == 200
        names = [f["family_name"] for f in r.json()["fonts"]]
        assert names[0] == "Roboto Mono"  # единственный шрифт с обоими тегами

        r = client.get("/api/fonts/search/nonexistent-id/more?offset=10")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "search_expired"
