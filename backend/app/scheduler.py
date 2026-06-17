"""Планировщик автосбора (② pull): периодически перезапускает все включённые
источники типа web_scrape / api, чтобы цены не устаревали.

Для хакатона — вызывается вручную (эндпоинт /api/ingest/run-scheduled) или из cron:
    */360 * * * *  cd backend && python -m app.scheduler
В проде заменяется на Celery beat + Redis.
"""
from __future__ import annotations

from .db import SessionLocal, init_db
from .ingestion import api_connector, web_scraper
from .ingestion.service import ingest_items
from .models import Source


def run_all_sources() -> list[dict]:
    db = SessionLocal()
    report: list[dict] = []
    try:
        sources = db.query(Source).filter(Source.enabled.is_(True)).all()
        for src in sources:
            try:
                if src.type == "web_scrape":
                    items = web_scraper.scrape_url(src.url_or_endpoint)
                    fmt, st, ch = "html", "web_scrape", "pull"
                elif src.type == "api":
                    items = api_connector.fetch_api(src.url_or_endpoint)
                    fmt, st, ch = "json", "api", "pull"
                else:
                    continue  # upload-источники не автособираются
                res = ingest_items(
                    db, clinic_id=src.clinic_id, channel=ch, source_type=st,
                    items=items, fmt=fmt, source_id=src.id,
                )
                report.append({"source_id": src.id, "status": "ok", "items": res.items_found})
            except Exception as e:
                report.append({"source_id": src.id, "status": "error", "error": str(e)})
        return report
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    for line in run_all_sources():
        print(line)
