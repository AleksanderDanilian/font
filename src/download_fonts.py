"""
download_fonts.py

Скачивает шрифты из официального репозитория https://github.com/google/fonts —
это тот же источник, из которого берёт файлы сам сайт fonts.google.com.
Файлы в нём «сырые» и открытые, без танцев с User-Agent (как пришлось бы
при обращении к CSS API Google Fonts).

Что делает скрипт для каждого запрошенного семейства:
    1. Пробует найти METADATA.pb в одной из трёх license-директорий
       (ofl/, apache/, ufl/ — большинство современных шрифтов лежит в ofl).
    2. Парсит METADATA.pb (простой текстовый protobuf, парсим без protoc,
       через регулярки — формат стабильный и простой).
    3. Скачивает сам файл шрифта:
         - если это variable font (у большинства современных шрифтов так) —
           скачивает один .ttf с осями (wght и т.д.), а затем через fontTools
           нарезает статичные инстансы Regular (400) и Bold (700) —
           этого достаточно и для превью, и для показа на сайте;
         - если шрифт статичный — скачивает конкретные Regular/Bold файлы
           (или ближайшие доступные веса, если Bold нет).
    4. Конвертирует все .ttf в .woff2 (в разы легче для веба).
    5. Складывает файлы шрифтов в fonts/{slug}/... и пишет метаданные
       в data/fonts_manifest.json (формат для render_previews.py) и
       data/fonts_full_manifest.jsonl (category/subsets/license — то,
       что дальше пойдёт в таблицу fonts в БД).

ВАЖНО про надёжность манифеста:
    Раньше манифесты писались один раз, в самом конце, после обработки
    ВСЕХ семейств. Если скрипт падал / прерывался (Ctrl+C, рейт-лимит,
    любая сетевая ошибка) на середине списка — все уже скачанные шрифты
    оставались без единой строчки в jsonl, хотя файлы шрифтов лежали
    на диске. Теперь каждая обработанная семья дописывается в манифест
    сразу же (см. append_record_to_manifests), поэтому прогресс не теряется.

Если jsonl-манифест уже потерян (как в случае, когда шрифты скачаны,
а fonts_full_manifest.jsonl пуст/отсутствует) — используй флаг
--rebuild-from-disk, он восстановит манифест по уже скачанным файлам
в fonts/, заново запросив только маленький METADATA.pb (без повторного
скачивания самих шрифтов).

Установка зависимостей:
    pip install -r requirements.txt

Расположение (структура проекта):
    project_root/
        src/download_fonts.py   <- этот файл
        data/                   <- манифесты (families.txt, fonts_metadata.json,
                                   fonts_manifest.json, fonts_full_manifest.jsonl)
        fonts/{slug}/...        <- сами файлы шрифтов (.woff2)

    Пути ниже вычисляются от расположения файла (Path(__file__)), поэтому
    запускать скрипт можно из любой директории — но для удобства
    рекомендуется запускать из корня проекта (см. run_download.sh в корне).

Использование:
    python src/download_fonts.py --families "Montserrat,Playfair Display,Pacifico"
    python src/download_fonts.py --families-file data/families.txt
    python src/download_fonts.py --rebuild-from-disk
"""

import argparse
import json
import re
import time
from pathlib import Path
from typing import Optional, Set

import requests
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

# Корень проекта = родитель директории src/, где лежит этот файл.
# Благодаря этому пути не зависят от того, из какой директории запущен скрипт.
BASE_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = BASE_DIR / "fonts"
DATA_DIR = BASE_DIR / "data"
MANIFEST_PATH = DATA_DIR / "fonts_manifest.json"
FULL_MANIFEST_PATH = DATA_DIR / "fonts_full_manifest.jsonl"

RAW_BASE = "https://raw.githubusercontent.com/google/fonts/main"
LICENSE_DIRS = ["ofl", "apache", "ufl"]

# Веса, которые нам нужны для MVP (Regular + Bold)
TARGET_WEIGHTS = [400, 700]


def slugify(family_name: str) -> str:
    """Конвенция именования директорий в репозитории google/fonts:
    нижний регистр, без пробелов и дефисов. Например,
    "Playfair Display" -> "playfairdisplay"."""
    return re.sub(r"[^a-z0-9]", "", family_name.lower())


def load_existing_manifests() -> tuple[Set[str], list[dict]]:
    """Читает уже накопленный data/fonts_full_manifest.jsonl (если он есть)
    и возвращает:
      - множество slug'ов, которые уже обработаны (для пропуска повторов);
      - список самих записей (чтобы дописать к ним новые и пересохранить
        оба манифеста).

    Если файла нет (например, он был потерян) — возвращает пустые
    множество/список; в этом случае используй --rebuild-from-disk, чтобы
    восстановить манифест по файлам, которые уже лежат в fonts/.
    """
    processed_slugs: Set[str] = set()
    existing_records: list[dict] = []

    if FULL_MANIFEST_PATH.exists():
        with open(FULL_MANIFEST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if "slug" in record:
                            processed_slugs.add(record["slug"])
                            existing_records.append(record)
                    except json.JSONDecodeError:
                        continue

    return processed_slugs, existing_records


def existing_font_files(slug: str) -> dict:
    """Проверяет, какие .woff2-файлы для данного slug уже лежат на диске
    в fonts/{slug}/, независимо от того, есть ли о них запись в манифесте.
    Возвращает словарь вида {"400": "fonts/slug/slug-400.woff2", ...}.

    Используется и для --rebuild-from-disk, и как дополнительная защита
    от повторной загрузки: даже если запись в jsonl отсутствует, но файлы
    уже скачаны, мы их не перекачиваем.
    """
    family_dir = FONTS_DIR / slug
    found = {}
    if not family_dir.exists():
        return found
    for weight in TARGET_WEIGHTS:
        path = family_dir / f"{slug}-{weight}.woff2"
        if path.exists():
            found[str(weight)] = str(path.relative_to(BASE_DIR))
    return found


def fetch_metadata(family_name: str) -> Optional[tuple[str, str]]:
    """Пробует найти METADATA.pb семейства среди трёх license-директорий
    репозитория google/fonts. METADATA.pb — маленький текстовый файл
    (никаких шрифтов внутри), поэтому его можно безопасно перезапрашивать
    даже для уже скачанных семейств (используется в --rebuild-from-disk).

    Возвращает (license_dir, raw_text) или None, если ни в одной из
    директорий (ofl/apache/ufl) файл не найден."""
    slug = slugify(family_name)
    for license_dir in LICENSE_DIRS:
        url = f"{RAW_BASE}/{license_dir}/{slug}/METADATA.pb"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return license_dir, resp.text
    return None


def parse_metadata(raw_text: str) -> dict:
    """Простой парсер текстового protobuf-формата METADATA.pb.
    Не претендует на универсальность, но покрывает все поля,
    которые реально встречаются в этом репозитории:
      - name: официальное имя семейства;
      - category: категория (sans-serif, serif, display, ...);
      - subsets: список поддерживаемых наборов символов (latin, cyrillic, ...);
      - fonts: список начертаний (style/weight/filename);
      - is_variable: True, если хотя бы один файл — variable font
        (у таких имя файла содержит квадратные скобки с осями, например
        "Font[wght].ttf")."""

    def scalar(field: str) -> Optional[str]:
        m = re.search(rf'^{field}:\s*"([^"]*)"', raw_text, re.MULTILINE)
        return m.group(1) if m else None

    subsets = re.findall(r'^subsets:\s*"([^"]*)"', raw_text, re.MULTILINE)

    fonts = []
    for block in re.findall(r"fonts\s*\{([^}]*)\}", raw_text):
        style = re.search(r'style:\s*"([^"]*)"', block)
        weight = re.search(r"weight:\s*(\d+)", block)
        filename = re.search(r'filename:\s*"([^"]*)"', block)
        fonts.append({
            "style": style.group(1) if style else "normal",
            "weight": int(weight.group(1)) if weight else 400,
            "filename": filename.group(1) if filename else None,
        })

    is_variable = any("[" in (f["filename"] or "") for f in fonts)

    return {
        "name": scalar("name"),
        "category": scalar("category"),
        "subsets": subsets,
        "fonts": fonts,
        "is_variable": is_variable,
    }


def download_file(license_dir: str, slug: str, filename: str, dest_path: Path) -> bool:
    """Скачивает один файл (шрифт) из репозитория google/fonts по прямому
    raw.githubusercontent.com URL и сохраняет его по указанному пути."""
    url = f"{RAW_BASE}/{license_dir}/{slug}/{filename}"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        print(f"  [error] не удалось скачать {url} (код {resp.status_code})")
        return False
    dest_path.write_bytes(resp.content)
    return True


def ttf_to_woff2(ttf_path: Path, woff2_path: Path) -> None:
    """Конвертирует .ttf в .woff2 через fontTools (в разы легче для веба)."""
    font = TTFont(str(ttf_path))
    font.flavor = "woff2"
    font.save(str(woff2_path))


def process_variable_font(slug: str, license_dir: str, filename: str, family_dir: Path) -> dict:
    """Скачивает variable-шрифт (один .ttf со всеми осями) и нарезает из
    него статичные инстансы Regular (400) и Bold (700) через
    fontTools.varLib.instancer. Каждый инстанс сохраняется как .ttf,
    конвертируется в .woff2, а промежуточные .ttf удаляются.

    Возвращает {"400": "относительный/путь.woff2", "700": "..."} —
    только для тех весов, которые удалось нарезать."""
    raw_ttf_path = family_dir / "_variable_source.ttf"
    if not download_file(license_dir, slug, filename, raw_ttf_path):
        return {}

    result_files = {}
    for weight in TARGET_WEIGHTS:
        try:
            font = TTFont(str(raw_ttf_path))
            instance = instantiateVariableFont(font, {"wght": weight})
            static_ttf = family_dir / f"{slug}-{weight}.ttf"
            instance.save(str(static_ttf))

            woff2_path = family_dir / f"{slug}-{weight}.woff2"
            ttf_to_woff2(static_ttf, woff2_path)
            static_ttf.unlink()  # промежуточный ttf больше не нужен

            result_files[str(weight)] = str(woff2_path.relative_to(BASE_DIR))
        except Exception as e:
            print(f"  [warn] не удалось создать инстанс веса {weight}: {e}")

    raw_ttf_path.unlink()
    return result_files


def process_static_font(slug: str, license_dir: str, fonts_meta: list[dict], family_dir: Path) -> dict:
    """Для нестатичных (не variable) семейств — скачивает конкретные файлы
    для нужных весов (400/700). Если запрошенного веса нет в списке
    начертаний — берёт ближайший доступный normal-стиль (например, вместо
    Bold 700 может подойти Medium 500, если Bold в семье не существует).

    Возвращает {"400": "относительный/путь.woff2", "700": "..."}."""
    normal_fonts = [f for f in fonts_meta if f["style"] == "normal" and f["filename"]]

    result_files = {}
    for target_weight in TARGET_WEIGHTS:
        candidate = min(
            normal_fonts,
            key=lambda f: abs(f["weight"] - target_weight),
            default=None,
        )
        if candidate is None:
            continue

        ttf_path = family_dir / candidate["filename"]
        if not download_file(license_dir, slug, candidate["filename"], ttf_path):
            continue

        woff2_path = family_dir / f"{slug}-{target_weight}.woff2"
        ttf_to_woff2(ttf_path, woff2_path)
        ttf_path.unlink()

        result_files[str(target_weight)] = str(woff2_path.relative_to(BASE_DIR))

    return result_files


def build_full_record(family_name: str, slug: str, license_dir: str, meta: dict, weight_files: dict) -> Optional[dict]:
    """Собирает итоговую запись манифеста из уже посчитанных данных.
    Возвращает None, если даже Regular (400) не удалось получить —
    такую запись в манифест писать нет смысла."""
    if "400" not in weight_files:
        return None

    # Если Bold не удалось получить отдельно — используем Regular и там,
    # и там (лучше, чем совсем не иметь превью).
    bold_path = weight_files.get("700", weight_files["400"])

    return {
        "family_name": meta.get("name") or family_name,
        "slug": slug,
        "category": meta.get("category"),
        "subsets": meta.get("subsets", []),
        "license": license_dir,
        "is_variable": meta.get("is_variable", False),
        "regular": weight_files["400"],
        "bold": bold_path,
    }


def process_family(family_name: str, existing_slugs: Set[str]) -> Optional[dict]:
    """Полный цикл обработки одного семейства: METADATA.pb -> парсинг ->
    скачивание нужных начертаний -> конвертация в woff2 -> запись манифеста.

    Пропускает семейство (возвращает None), если:
      - slug уже есть в existing_slugs (уже обработан ранее);
      - METADATA.pb не найден ни в одной license-директории;
      - в семействе нет subset'а "latin" (минимальное требование проекта);
      - не удалось скачать даже Regular (400) начертание.
    """
    print(f"[{family_name}]")
    slug = slugify(family_name)

    if slug in existing_slugs:
        print(f"  [skip] шрифт уже есть в манифесте")
        return None

    found = fetch_metadata(family_name)
    if found is None:
        print(f"  [skip] METADATA.pb не найден ни в одной license-директории")
        return None

    license_dir, raw_text = found
    meta = parse_metadata(raw_text)

    if "latin" not in meta["subsets"]:
        print(f"  [skip] нет subset 'latin' — минимальное требование не выполнено")
        return None

    family_dir = FONTS_DIR / slug
    family_dir.mkdir(parents=True, exist_ok=True)

    if meta["is_variable"]:
        variable_filename = next(
            (f["filename"] for f in meta["fonts"] if f["style"] == "normal" and f["filename"]),
            None,
        )
        if variable_filename is None:
            print(f"  [skip] не нашли normal-файл variable-шрифта")
            return None
        weight_files = process_variable_font(slug, license_dir, variable_filename, family_dir)
    else:
        weight_files = process_static_font(slug, license_dir, meta["fonts"], family_dir)

    record = build_full_record(family_name, slug, license_dir, meta, weight_files)
    if record is None:
        print(f"  [skip] не удалось получить даже Regular (400) начертание")
        return None

    print(f"  [ok] скачано, weights: {list(weight_files.keys())}, subsets: {meta['subsets']}")
    return record


def rebuild_manifest_from_disk(existing_slugs: Set[str]) -> list[dict]:
    """Восстанавливает манифест по уже скачанным файлам в fonts/, БЕЗ
    повторного скачивания самих шрифтов. Для каждой папки fonts/{slug}/,
    у которой ещё нет записи в манифесте, заново запрашивает маленький
    METADATA.pb (чтобы получить family_name/category/subsets/license) и
    смотрит, какие *-400.woff2 / *-700.woff2 уже лежат на диске.

    Нужен для ситуации "шрифты скачаны, а fonts_full_manifest.jsonl
    пуст/отсутствует" — так восстанавливаются метаданные без повторной
    загрузки самих файлов шрифтов."""
    if not FONTS_DIR.exists():
        print("[rebuild] директория fonts/ не найдена — восстанавливать нечего")
        return []

    slugs_on_disk = sorted(p.name for p in FONTS_DIR.iterdir() if p.is_dir())
    to_rebuild = [s for s in slugs_on_disk if s not in existing_slugs]

    if not to_rebuild:
        print("[rebuild] все шрифты на диске уже есть в манифесте, нечего восстанавливать")
        return []

    print(f"[rebuild] найдено {len(to_rebuild)} шрифтов на диске без записи в манифесте")

    rebuilt_records = []
    for slug in to_rebuild:
        weight_files = existing_font_files(slug)
        if "400" not in weight_files:
            print(f"  [{slug}] [skip] нет даже файла -400.woff2, пропускаем")
            continue

        # METADATA.pb ищем по slug напрямую (family_name нам неизвестно,
        # но конвенция именования директорий в google/fonts — это и есть slug).
        found = None
        for license_dir in LICENSE_DIRS:
            url = f"{RAW_BASE}/{license_dir}/{slug}/METADATA.pb"
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                found = (license_dir, resp.text)
                break

        if found is None:
            print(f"  [{slug}] [warn] METADATA.pb не найден, запись будет без category/subsets/license")
            record = {
                "family_name": slug,
                "slug": slug,
                "category": None,
                "subsets": [],
                "license": None,
                "is_variable": None,
                "regular": weight_files["400"],
                "bold": weight_files.get("700", weight_files["400"]),
            }
        else:
            license_dir, raw_text = found
            meta = parse_metadata(raw_text)
            record = build_full_record(slug, slug, license_dir, meta, weight_files)

        if record:
            print(f"  [{slug}] [ok] метаданные восстановлены")
            rebuilt_records.append(record)

        time.sleep(0.2)

    return rebuilt_records


def append_record_to_manifests(record: dict, all_records: list[dict]) -> None:
    """Дописывает ОДНУ новую запись сразу в оба манифеста:
      - data/fonts_full_manifest.jsonl — построчным append (дёшево,
        не требует перечитывания всего файла);
      - data/fonts_manifest.json — этот файл целиком перезаписывается,
        т.к. это JSON-массив (но он маленький, это не проблема).

    Вызывается сразу после каждого успешно обработанного семейства —
    именно это защищает от потери прогресса при обрыве скрипта
    посередине списка."""
    with open(FULL_MANIFEST_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    manifest_entries = [
        {
            "family_name": r["family_name"],
            "slug": r["slug"],
            "regular": r["regular"],
            "bold": r["bold"],
        }
        for r in all_records
    ]
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest_entries, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--families", type=str, help="Список семейств через запятую")
    parser.add_argument("--families-file", type=str, help="Путь к файлу со списком семейств (по одному на строку)")
    parser.add_argument("--force", action="store_true", help="Принудительно перезаписать существующие записи манифеста")
    parser.add_argument(
        "--rebuild-from-disk",
        action="store_true",
        help="Восстановить манифест по уже скачанным файлам в fonts/ (без повторного скачивания шрифтов) и выйти",
    )
    args = parser.parse_args()

    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    processed_slugs, existing_records = load_existing_manifests()

    if args.force:
        processed_slugs = set()
        existing_records = []
        print("⚠️  Режим принудительной перезаписи включен")

    # Режим восстановления манифеста по файлам на диске — не требует --families
    if args.rebuild_from_disk:
        rebuilt = rebuild_manifest_from_disk(processed_slugs)
        all_records = existing_records
        for record in rebuilt:
            all_records.append(record)
            append_record_to_manifests(record, all_records)
        print(f"\n✅ Восстановлено записей: {len(rebuilt)}")
        print(f"📊 Итого в манифесте: {len(all_records)}")
        return

    if args.families:
        family_list = [f.strip() for f in args.families.split(",") if f.strip()]
    elif args.families_file:
        with open(args.families_file, "r", encoding="utf-8") as f:
            family_list = [line.strip() for line in f if line.strip()]
    else:
        parser.error("Укажи --families, --families-file или --rebuild-from-disk")
        return

    all_records = existing_records
    new_count = 0
    skipped_count = 0

    for family_name in family_list:
        record = process_family(family_name, processed_slugs)
        if record:
            processed_slugs.add(record["slug"])
            all_records.append(record)
            append_record_to_manifests(record, all_records)  # пишем сразу, не ждём конца списка
            new_count += 1
        else:
            skipped_count += 1
        time.sleep(0.3)  # вежливая пауза, не долбим raw.githubusercontent.com слишком часто

    if new_count:
        print(f"\n✅ Добавлено {new_count} новых шрифтов")
    else:
        print(f"\nℹ️  Новых шрифтов для добавления не найдено")

    print(f"📊 Итог: {new_count}/{len(family_list)} семейств успешно обработано.")
    print(f"⏭️  Пропущено (уже существуют или ошибки): {skipped_count}")
    print(f"→ {MANIFEST_PATH.relative_to(BASE_DIR)} — для render_previews.py")
    print(f"→ {FULL_MANIFEST_PATH.relative_to(BASE_DIR)} — полные метаданные для загрузки в БД")


if __name__ == "__main__":
    main()
