"""Планировщик автосбора (② pull): периодически перезапускает все включённые
источники типа web_scrape / api, чтобы цены не устаревали.

Для хакатона — вызывается вручную (эндпоинт /api/ingest/run-scheduled) или из cron
(§4: данные обновляются не реже 1 раза в сутки):
    0 */6 * * *  cd backend && python -m app.scheduler   # каждые 6 часов
В проде заменяется на Celery beat + Redis.

§4 отказоустойчивость: каждый источник в своём try/except — падение одного НЕ
останавливает сбор с остальных; ошибка пишется в журнал IngestionRun (status=error)
с источником и причиной (§3.1 журналирование).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .config import settings
from .db import SessionLocal, init_db
from .ingestion import api_connector, web_scraper
from .ingestion.service import ingest_items
from .models import IngestionRun, Source


def _log_error(db, src: Source, fmt: str, reason: str) -> None:
    """§3.1: журналируем ошибку парсинга с источником и причиной."""
    db.add(IngestionRun(
        source_id=src.id, channel="pull", format=fmt, status="error",
        items_found=0, message=f"{src.type} {src.url_or_endpoint}: {reason}"[:2000],
    ))
    db.commit()


def run_all_sources() -> list[dict]:
    db = SessionLocal()
    report: list[dict] = []
    try:
        sources = db.query(Source).filter(Source.enabled.is_(True)).all()
        for src in sources:
            fmt = "html" if src.type == "web_scrape" else "json"
            try:
                raw = ""
                if src.type == "web_scrape":
                    raw, items = web_scraper.scrape_url_raw(src.url_or_endpoint)
                    st, ch = "web_scrape", "pull"
                elif src.type == "api":
                    items = api_connector.fetch_api(src.url_or_endpoint)
                    st, ch = "api", "pull"
                else:
                    continue  # upload-источники не автособираются
                res = ingest_items(
                    db, clinic_id=src.clinic_id, channel=ch, source_type=st,
                    items=items, fmt=fmt, source_id=src.id, raw_content=raw,
                )
                report.append({"source_id": src.id, "status": "ok", "items": res.items_found})
            except web_scraper.RobotsDisallowed as e:
                _log_error(db, src, fmt, f"robots.txt запрещает: {e.url}")
                report.append({"source_id": src.id, "status": "skipped_robots", "url": e.url})
            except Exception as e:  # отказоустойчивость: не валим остальные источники
                _log_error(db, src, fmt, str(e))
                report.append({"source_id": src.id, "status": "error", "error": str(e)})
        return report
    finally:
        db.close()


def purge_expired_raw() -> int:
    """§4: сырые данные хранятся не менее raw_retention_days; старше — чистим
    raw_content (сам журнал запуска оставляем для аудита метрик)."""
    cutoff = datetime.utcnow() - timedelta(days=settings.raw_retention_days)
    db = SessionLocal()
    try:
        rows = (db.query(IngestionRun)
                .filter(IngestionRun.created_at < cutoff, IngestionRun.raw_content != "")
                .all())
        for r in rows:
            r.raw_content = ""
        db.commit()
        return len(rows)
    finally:
        db.close()


def mark_stale_inactive() -> int:
    """§4: цены старше price_freshness_days перестают считаться актуальными
    (is_active=False), чтобы не выдавать устаревшие данные как свежие."""
    from .models import Price
    cutoff = datetime.utcnow() - timedelta(days=settings.price_freshness_days)
    db = SessionLocal()
    try:
        rows = (db.query(Price)
                .filter(Price.parsed_at < cutoff, Price.is_active.is_(True))
                .all())
        for p in rows:
            p.is_active = False
        db.commit()
        return len(rows)
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    for line in run_all_sources():
        print(line)
    print({"raw_purged": purge_expired_raw(), "stale_deactivated": mark_stale_inactive()})
