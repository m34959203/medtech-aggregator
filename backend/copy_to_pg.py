"""Разовый перенос данных SQLite → Postgres (cutover на прод-рантайм).

Целевая схема должна быть СОЗДАНА ЗАРАНЕЕ миграциями (alembic upgrade head /
python -m app.migrate против целевой БД). Скрипт только копирует строки в
FK-безопасном порядке и сбрасывает sequence автоинкремента (для Postgres).

  python copy_to_pg.py <src_url> <dst_url>
  # пример: python copy_to_pg.py sqlite:////data/medtech.db \
  #         postgresql+psycopg2://medtech:medtech@medtech-db:5432/medtech
"""
from __future__ import annotations

import sys

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Clinic, IngestionRun, Lead, Price, PriceHistory, PriceReport, ServiceCatalog, Source,
)

# Порядок учитывает внешние ключи (родители раньше детей).
ORDER = [Clinic, ServiceCatalog, Source, IngestionRun, Lead, PriceReport, Price, PriceHistory]


def copy(src_url: str, dst_url: str) -> dict[str, int]:
    src = create_engine(src_url, future=True)
    dst = create_engine(dst_url, future=True)
    counts: dict[str, int] = {}

    with Session(src) as ss, Session(dst) as ds:
        for model in ORDER:
            rows = ss.execute(select(model)).scalars().all()
            for r in rows:
                data = {c.name: getattr(r, c.name) for c in model.__table__.columns}
                ds.execute(model.__table__.insert().values(**data))
            ds.commit()
            counts[model.__tablename__] = len(rows)
            print(f"  {model.__tablename__}: {len(rows)}")

    # Postgres: подвинуть sequence id, иначе следующий INSERT упрётся в дубль ключа.
    # Только для таблиц с serial-PK; у clinics/service_catalog PK — uuid (sequence нет).
    if dst_url.startswith("postgres"):
        uuid_pk = {"clinics", "service_catalog"}
        with dst.begin() as conn:
            for model in ORDER:
                t = model.__tablename__
                if t in uuid_pk:
                    continue
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {t}), 1))"
                ))
    return counts


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "sqlite:////data/medtech.db"
    dst = sys.argv[2] if len(sys.argv) > 2 else settings.database_url
    print(f"[copy] {src}  →  {dst}")
    total = copy(src, dst)
    print(f"[copy] готово: {sum(total.values())} строк.")
