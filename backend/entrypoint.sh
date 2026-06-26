#!/bin/sh
set -e

mkdir -p /data

# Схема — через Alembic-миграции (устойчиво к свежей / мигрированной / легаси БД),
# вместо create_all. Идемпотентно: повторный старт = no-op.
echo "[entrypoint] применяю миграции схемы..."
python -m app.migrate

# Демо-сид только по явному флагу SEED_DEMO=1 И только если БД пуста
# (не стирает реальные загрузки при рестарте). По умолчанию прод стартует пустым.
if [ "${SEED_DEMO:-0}" = "1" ] || [ "${SEED_DEMO:-}" = "true" ]; then
  if python - <<'PY'
import sys
from app.db import SessionLocal
from app.models import Clinic
s = SessionLocal()
empty = s.query(Clinic).count() == 0
s.close()
sys.exit(0 if empty else 1)
PY
  then
    echo "[entrypoint] SEED_DEMO=1 и БД пуста — заполняю демо-данными..."
    python -m app.seed
  else
    echo "[entrypoint] БД уже наполнена — пропускаю seed."
  fi
fi

# Семантический индекс (pgvector) — лучшее усилие, не валит старт при отсутствии модели.
python - <<'PY' || echo "[entrypoint] семантика пропущена"
from app.db import SessionLocal
from app.ingestion import semantic
if semantic.available():
    db = SessionLocal()
    try:
        n = semantic.reindex(db)
        print(f"[entrypoint] семантика: проиндексировано услуг — {n}")
    finally:
        db.close()
else:
    print("[entrypoint] семантика выключена/недоступна — пропуск индексации")
PY

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
