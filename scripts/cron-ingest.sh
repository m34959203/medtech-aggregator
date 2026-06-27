#!/usr/bin/env bash
# §3.1 MedPrice: плановый автосбор прайсов по расписанию (cron + flock).
# Запускает scheduler ВНУТРИ работающего backend-контейнера: run_all_sources()
# (web_scrape/api по включённым источникам) + purge_expired_raw + mark_stale_inactive.
# flock не даёт прогонам наслаиваться (долгий парсинг переживёт следующий тик).
set -euo pipefail

CONTAINER="medtech-backend"
LOCK="/tmp/medtech-cron-ingest.lock"
LOG_DIR="/home/ubuntu/medtech-platform/backups"
LOG="${LOG_DIR}/cron-ingest.log"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date '+%F %T') SKIP: предыдущий прогон ещё идёт" >>"$LOG"
  exit 0
fi

mkdir -p "$LOG_DIR"
echo "=== $(date '+%F %T') START ===" >>"$LOG"
if /usr/bin/docker exec "$CONTAINER" python -m app.scheduler >>"$LOG" 2>&1; then
  echo "=== $(date '+%F %T') OK ===" >>"$LOG"
else
  echo "=== $(date '+%F %T') FAIL (exit $?) ===" >>"$LOG"
fi
