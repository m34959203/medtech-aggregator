"""Миграции схемы (Alembic) — устойчивость к свежей и легаси БД (subprocess)."""
import os
import sqlite3
import subprocess
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EXPECTED = {"alembic_version", "clinics", "service_catalog", "sources",
             "ingestion_runs", "prices", "price_reports", "leads", "price_history"}


def _run_migrate(db_path: str):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    r = subprocess.run([sys.executable, "-m", "app.migrate"], cwd=BACKEND, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r


def _tables(db_path):
    c = sqlite3.connect(db_path)
    try:
        return {row[0] for row in c.execute("select name from sqlite_master where type='table'")}
    finally:
        c.close()


def test_migrate_fresh_db(tmp_path):
    db = str(tmp_path / "fresh.db")
    _run_migrate(db)
    assert _EXPECTED <= _tables(db)


def test_migrate_legacy_db_adopted(tmp_path):
    db = str(tmp_path / "legacy.db")
    c = sqlite3.connect(db)
    c.execute("create table clinics(id integer primary key, name text)")  # без access_token
    c.execute("create table service_catalog(id integer primary key, canonical_name text)")
    c.commit(); c.close()

    _run_migrate(db)
    assert _EXPECTED <= _tables(db)
    cols = [r[1] for r in sqlite3.connect(db).execute("pragma table_info(clinics)")]
    assert "access_token" in cols  # легаси-колонка добавлена
