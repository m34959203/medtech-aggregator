"""Применение схемы через Alembic — устойчиво к трём состояниям БД.

1. Свежая БД (нет таблиц)         → alembic upgrade head (создаёт всё).
2. Уже под Alembic                → alembic upgrade head (применяет новое).
3. Легаси (create_all без версии) → добиваем недостающие таблицы/колонки и
   штампуем head, чтобы дальше жить на миграциях.

Запуск: python -m app.migrate
"""
from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from .db import Base, engine
from . import models  # noqa: F401  — регистрируем таблицы


# MedArchive: аддитивные nullable-колонки. Добавляются «по месту» (ALTER ADD COLUMN,
# только если колонки нет), чтобы не плодить Alembic-ревизии и работать на уже живых
# SQLite/PG без даунтайма. Существующий путь MedPrice (одна цена) не затрагивается.
_ADDITIVE_COLUMNS = {
    "service_catalog": [("tarificator_code", "VARCHAR(32)"), ("specialty", "TEXT")],
    "ingestion_runs": [("file_name", "TEXT"), ("raw_content", "TEXT")],
    "clinics": [
        ("working_hours", "TEXT"),
        ("website", "TEXT"),
        ("rating", "FLOAT"),
        ("online_booking", "BOOLEAN"),
    ],
    "prices": [
        ("price_resident", "NUMERIC(12,2)"),
        ("price_nonresident", "NUMERIC(12,2)"),
        ("service_code_source", "VARCHAR(48)"),
        ("tarificator_code", "VARCHAR(32)"),
        # §2.2 MedPrice
        ("parsed_at", "TIMESTAMP"),
        ("is_active", "BOOLEAN"),
        ("duration_days", "INTEGER"),
        ("price_original", "NUMERIC(12,2)"),
        ("currency_original", "VARCHAR(8)"),
    ],
}


def _ensure_additive_columns() -> None:
    """Идемпотентно добавляет недостающие MedArchive-колонки в существующие таблицы."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    for table, cols in _ADDITIVE_COLUMNS.items():
        if table not in tables:
            continue
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols:
            if name not in have:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                print(f"[migrate] +{table}.{name}")


def run() -> None:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    cfg = Config("alembic.ini")

    if "alembic_version" in tables or "clinics" not in tables:
        # уже под Alembic, либо совсем свежая БД — миграции делают всё сами
        command.upgrade(cfg, "head")
        _ensure_additive_columns()
        print("[migrate] alembic upgrade head — готово.")
        return

    # Легаси-БД (создавалась через create_all без Alembic): добиваем схему и штампуем.
    legacy_cols = {c["name"] for c in insp.get_columns("clinics")}
    Base.metadata.create_all(engine)  # создаёт недостающие НОВЫЕ таблицы
    if "access_token" not in legacy_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE clinics ADD COLUMN access_token VARCHAR(64)"))
        print("[migrate] легаси: добавлена колонка clinics.access_token.")
    _ensure_additive_columns()
    command.stamp(cfg, "head")
    print("[migrate] легаси-БД адаптирована и помечена head.")


if __name__ == "__main__":
    run()
