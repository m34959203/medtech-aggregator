"""Оркестрация приёма: сырые позиции → нормализация → дедупликация → prices.

Дедупликация (★): одна услуга могла прийти и из файла, и с сайта. При конфликте
для пары (клиника, услуга) приоритет источника: upload > api > web_scrape.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..models import IngestionRun, Price, Source
from ..schemas import IngestionResult
from .file_parser import RawItem
from .normalizer import Normalizer

SOURCE_PRIORITY = {"upload": 3, "api": 2, "web_scrape": 1}


def ingest_items(
    db: Session,
    *,
    clinic_id: int,
    channel: str,            # push / pull
    source_type: str,        # upload / web_scrape / api
    items: list[RawItem],
    fmt: str,
    source_id: int | None = None,
    valid_from: date | None = None,
) -> IngestionResult:
    valid_from = valid_from or date.today()
    run = IngestionRun(
        source_id=source_id,
        channel=channel,
        format=fmt,
        status="started",
        items_found=len(items),
    )
    db.add(run)
    db.flush()

    normalizer = Normalizer(db)
    threshold = settings.match_confidence_threshold

    # схлопываем дубли внутри самой пачки по service_id (берём минимальную цену)
    batch: dict[int, dict] = {}
    matched = needs_review = 0

    for item in items:
        res = normalizer.normalize(item.raw_name)
        if res.confidence >= threshold:
            matched += 1
        else:
            needs_review += 1
        sid = res.service.id
        cur = batch.get(sid)
        if cur is None or item.price < cur["price"]:
            batch[sid] = {
                "price": item.price,
                "raw_name": item.raw_name,
                "confidence": res.confidence,
            }

    new_prio = SOURCE_PRIORITY.get(source_type, 0)

    for sid, data in batch.items():
        existing = (
            db.query(Price)
            .filter(Price.clinic_id == clinic_id, Price.service_id == sid)
            .order_by(Price.valid_from.desc())
            .first()
        )
        if existing:
            old_prio = SOURCE_PRIORITY.get(existing.source_type, 0)
            # обновляем, если новый источник не менее приоритетен (свежие данные)
            if new_prio >= old_prio:
                existing.price = data["price"]
                existing.raw_name = data["raw_name"]
                existing.source_type = source_type
                existing.run_id = run.id
                existing.match_confidence = data["confidence"]
                existing.valid_from = valid_from
            # иначе оставляем официальную загрузку клиники как есть
            continue
        db.add(
            Price(
                clinic_id=clinic_id,
                service_id=sid,
                run_id=run.id,
                source_type=source_type,
                raw_name=data["raw_name"],
                price=data["price"],
                currency="KZT",
                match_confidence=data["confidence"],
                valid_from=valid_from,
            )
        )

    run.status = "normalized"
    run.message = f"Принято {len(items)}, услуг после дедупа {len(batch)}, на проверку {needs_review}"

    if source_id:
        src = db.get(Source, source_id)
        if src:
            src.last_run_at = datetime.utcnow()

    db.commit()
    return IngestionResult(
        run_id=run.id,
        clinic_id=clinic_id,
        channel=channel,
        format=fmt,
        items_found=len(items),
        matched=matched,
        needs_review=needs_review,
        status=run.status,
    )
