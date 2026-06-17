#!/bin/sh
set -e

mkdir -p /data

# Засеять демо-данными только если БД пуста (чтобы не стирать загрузки при рестарте).
# python-проверка возвращает 0 (БД пуста → нужен seed) или 1 (уже наполнена).
if python - <<'PY'
import sys
from app.db import init_db, SessionLocal
from app.models import Clinic
init_db()
s = SessionLocal()
empty = s.query(Clinic).count() == 0
s.close()
sys.exit(0 if empty else 1)
PY
then
  echo "[entrypoint] БД пуста — заполняю демо-данными..."
  python -m app.seed
else
  echo "[entrypoint] БД уже наполнена — пропускаю seed."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
