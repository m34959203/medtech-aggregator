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


def run() -> None:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    cfg = Config("alembic.ini")

    if "alembic_version" in tables or "clinics" not in tables:
        # уже под Alembic, либо совсем свежая БД — миграции делают всё сами
        command.upgrade(cfg, "head")
        print("[migrate] alembic upgrade head — готово.")
        return

    # Легаси-БД (создавалась через create_all без Alembic): добиваем схему и штампуем.
    legacy_cols = {c["name"] for c in insp.get_columns("clinics")}
    Base.metadata.create_all(engine)  # создаёт недостающие НОВЫЕ таблицы
    if "access_token" not in legacy_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE clinics ADD COLUMN access_token VARCHAR(64)"))
        print("[migrate] легаси: добавлена колонка clinics.access_token.")
    command.stamp(cfg, "head")
    print("[migrate] легаси-БД адаптирована и помечена head.")


if __name__ == "__main__":
    run()
