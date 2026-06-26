"""CLI приёма архива прайсов партнёров (MedArchive).

    python -m app.archive_ingest <папка|zip> [--catalog "Справочник услуг.xlsx"] \
            [--report docs/quality-report.md]

Шаги: миграция схемы → загрузка официального справочника (если задан) →
обработка каждого документа (партнёр по имени файла) → отчёт о качестве
обработки (документы, позиции, % автонормализации, очередь) против цели ≥70%.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import zipfile
from datetime import date

from .db import SessionLocal
from .ingestion import archive_extractor as ae
from .ingestion.archive_service import ingest_archive
from .ingestion.normalizer import Normalizer
from .ingestion.refcatalog import load_official_catalog
from .models import Clinic

_SUPPORTED = (".pdf", ".docx", ".xlsx", ".xls")
# Не прайсы партнёров: целевой справочник и документы ТЗ — пропускаем при обходе.
_SKIP_PATTERNS = ("справочник услуг", "тз_", "тз ", "techзадание", "readme")


def _is_pricelist(filename: str) -> bool:
    low = os.path.basename(filename).lower()
    return not any(p in low for p in _SKIP_PATTERNS)


def _partner_name(filename: str) -> str:
    """«Клиника 1 прайс 2024.docx» → «Клиника 1» (несколько прайсов = один партнёр)."""
    base = os.path.splitext(os.path.basename(filename))[0]
    m = re.match(r"\s*(Клиника\s*\d+|[А-ЯA-Z][\w\-]+(?:\s+[А-ЯA-Z]?[\w\-]+){0,2})", base)
    name = m.group(1).strip() if m else base
    # отрезаем хвостовые годы/слова «прайс»
    name = re.sub(r"[_\s]*(прайс|price|\d{4}).*$", "", name, flags=re.I).strip(" _-")
    return name or base


def _effective_date(filename: str) -> date:
    m = re.search(r"(20\d{2})", filename)
    if m:
        y = int(m.group(1))
        if y <= date.today().year:
            return date(y, 1, 1)
    return date.today()


def _iter_files(path: str):
    """Отдаёт (filename, bytes) из папки или zip-архива."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.lower().endswith(_SUPPORTED) and not n.startswith("__") and _is_pricelist(n):
                    yield os.path.basename(n), z.read(n)
        return
    if os.path.isdir(path):
        for n in sorted(os.listdir(path)):
            full = os.path.join(path, n)
            if os.path.isfile(full) and n.lower().endswith(_SUPPORTED) and _is_pricelist(n):
                with open(full, "rb") as f:
                    yield n, f.read()
        return
    raise SystemExit(f"Не папка и не .zip: {path}")


def _get_or_create_partner(db, name: str) -> Clinic:
    c = db.query(Clinic).filter(Clinic.name == name).first()
    if c:
        return c
    c = Clinic(name=name, city="", address="")
    db.add(c)
    db.flush()
    return c


def _write_report(path: str, stats: list[dict], catalog_stat: dict | None,
                  db=None, semantic_stat: dict | None = None) -> None:
    docs = len(stats)
    items = sum(s["items"] for s in stats)
    services = sum(s["services"] for s in stats)
    matched = sum(s["matched"] for s in stats)
    review = sum(s["needs_review"] for s in stats)
    skipped = sum(s["skipped"] for s in stats)
    anomalies = sum(s["anomalies"] for s in stats)
    # Позиционная метрика (как в ТЗ — «% позиций нормализуются»): на уровне документов
    # matched/(matched+review). Дедуп НЕ применяем к знаменателю: matched схлопывается
    # по service_id, а unmatched — нет, и DB-доля исказила бы картину.
    auto = round(100.0 * matched / max(matched + review, 1), 1)
    queue_live = None
    if db is not None:
        from .models import Price
        queue_live = db.query(Price).filter(Price.service_id.is_(None)).count()
    goal = "✅ цель ≥70% достигнута" if auto >= 70 else "⚠️ ниже цели 70% — растёт с пополнением синонимов/кодов (см. ниже)"

    lines = [
        "# Отчёт о качестве обработки архива (MedArchive)",
        "",
        f"_Сгенерировано: `python -m app.archive_ingest`. Дата: {date.today().isoformat()}_",
        "",
        "## Сводка",
        "",
        f"- Обработано документов: **{docs}**",
        f"- Извлечено позиций: **{items}**",
        f"- Услуг после дедупликации: **{services}**",
        f"- **Автонормализация позиций (код тарификатора + нечётко): {auto}%** — {goal}",
        f"- В очереди на ревью (unmatched, позиций): **{review}**",
        f"- Пропущено (битые/пустые): **{skipped}**",
        f"- Аномалий цены (>50% к прошлой версии): **{anomalies}**",
    ]
    if queue_live is not None:
        lines.append(f"- Уникальных позиций в очереди оператора (живая БД): **{queue_live}**")
    if semantic_stat and semantic_stat.get("available"):
        lines.append(
            f"- Семантический 2-й проход (порог ≥0.85, высокая точность): "
            f"досопоставлено **{semantic_stat.get('assigned', 0)}** услуг "
            f"(из {semantic_stat.get('checked', 0)} проверенных по смыслу; "
            f"менее уверенные — оператору как подсказка, не авто, чтобы не портить сравнение цен)"
        )
    if catalog_stat:
        lines += [
            f"- Целевой справочник: **{catalog_stat['rows']}** услуг "
            f"(с кодом тарификатора: {catalog_stat['with_code']})",
        ]
    lines += [
        "",
        "## По документам",
        "",
        "| Документ | Формат | Позиций | Услуг | Auto-match | На ревью | Пропущено | С кодом |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for s in stats:
        lines.append(
            f"| {s['file']} | {s['format']} | {s['items']} | {s['services']} | "
            f"{s['matched']} ({s['auto_rate']}%) | {s['needs_review']} | {s['skipped']} | {s['with_code']} |"
        )
    lines += [
        "",
        "## Методика",
        "",
        "1. **Извлечение** — DOCX (с принятием tracked changes), XLSX/XLS "
        "(автодетект строки-заголовка, многострочная шапка, все листы), "
        "PDF (таблицы → реконструкция по координатам слов), резидент/нерезидент раздельно.",
        "2. **Нормализация** — code-first по коду тарификатора (точное совпадение → 100%), "
        "иначе нечётко (rapidfuzz) + семантика (offline-эмбеддинги) + LLM при неоднозначности.",
        "3. **Валидации** — цена>0, нерезидент≥резидент, имя не пустое, аномалия >50% к прошлой версии; "
        "версионирование цен (история не удаляется).",
        "4. **Очередь ревью** — позиции ниже порога уверенности уходят оператору "
        "(`/api/unmatched`, экран `/admin/review`).",
    ]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Приём архива прайсов партнёров (MedArchive)")
    ap.add_argument("path", help="папка с прайсами или .zip")
    ap.add_argument("--catalog", help="официальный Справочник услуг.xlsx (загрузить целевой справочник)")
    ap.add_argument("--report", default="docs/quality-report.md", help="путь к отчёту качества")
    ap.add_argument("--no-migrate", action="store_true", help="не запускать миграцию схемы")
    ap.add_argument("--semantic-pass", action="store_true",
                    help="второй проход: досопоставить unmatched по смыслу (эмбеддинги)")
    args = ap.parse_args(argv)

    # Bulk-приём идёт code-first + fuzzy (+LLM при ключе). Семантику (fastembed)
    # на тысячах позиций НЕ гоняем — она O(N×каталог) и душит CPU; это фишка
    # live-демо одиночных запросов, не пакетной обработки архива.
    from .config import settings as _settings
    _settings.semantic_enabled = False

    if not args.no_migrate:
        from .migrate import run as migrate_run
        migrate_run()

    db = SessionLocal()
    catalog_stat = None
    try:
        if args.catalog:
            with open(args.catalog, "rb") as f:
                catalog_stat = load_official_catalog(db, f.read())
            db.commit()
            print(f"[catalog] справочник: {catalog_stat}")

        nz = Normalizer(db)  # один общий нормализатор (общий рост синонимов/индекса)
        stats = []
        for fname, content in _iter_files(args.path):
            partner = _get_or_create_partner(db, _partner_name(fname))
            try:
                fmt, items = ae.detect_and_parse(fname, content)
            except Exception as e:
                print(f"[error] {fname}: {type(e).__name__}: {e}")
                continue
            st = ingest_archive(
                db, clinic_id=partner.id, file_name=fname, fmt=fmt,
                items=items, valid_from=_effective_date(fname), normalizer=nz,
            )
            stats.append(st)
            print(f"[doc] {fname:34} {fmt:5} pos={st['items']:5} svc={st['services']:4} "
                  f"auto={st['matched']:4}({st['auto_rate']}%) review={st['needs_review']:4}")

        semantic_stat = None
        if args.semantic_pass:
            _settings.semantic_enabled = True  # включаем только для второго прохода
            from .ingestion.semantic_backfill import backfill_unmatched
            print("[semantic] второй проход по unmatched (эмбеддинги)…")
            semantic_stat = backfill_unmatched(db)
            print(f"[semantic] {semantic_stat}")

        _write_report(args.report, stats, catalog_stat, db=db, semantic_stat=semantic_stat)
        tot_m = sum(s["matched"] for s in stats)
        tot_r = sum(s["needs_review"] for s in stats)
        auto = round(100.0 * tot_m / max(tot_m + tot_r, 1), 1)
        msg = f"\n[report] {args.report} — {len(stats)} док., автонормализация позиций {auto}%"
        if semantic_stat and semantic_stat.get("assigned"):
            msg += f"; семантикой (≥0.85) досопоставлено ещё {semantic_stat['assigned']} услуг"
        print(msg)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
