#!/bin/sh
set -e

mkdir -p /data

# Демо-сид только по явному флагу SEED_DEMO=1 И только если БД пуста
# (не стирает реальные загрузки при рестарте). По умолчанию прод стартует пустым.
if [ "${SEED_DEMO:-0}" = "1" ] || [ "${SEED_DEMO:-}" = "true" ]; then
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
    echo "[entrypoint] SEED_DEMO=1 и БД пуста — заполняю демо-данными..."
    python -m app.seed
  else
    echo "[entrypoint] БД уже наполнена — пропускаю seed."
  fi
else
  echo "[entrypoint] SEED_DEMO не задан — прод стартует без демо-данных."
  python -c "from app.db import init_db; init_db()"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
