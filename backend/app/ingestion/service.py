"""Оркестрация приёма: сырые позиции → нормализация → дедупликация → prices.

Дедупликация (★): одна услуга могла прийти и из файла, и с сайта. При конфликте
для пары (клиника, услуга) приоритет источника: upload > api > web_scrape.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..models import IngestionRun, Price, PriceHistory, Source
from ..schemas import IngestionResult
from .currency import Currency, normalize as normalize_currency
from .file_parser import RawItem
from .normalizer import Normalizer

SOURCE_PRIORITY = {"upload": 3, "api": 2, "web_scrape": 1}


def to_kzt(price: float, currency: str) -> tuple[float, float | None, str]:
    """§2.2: привести цену к KZT. Возвращает (price_kzt, price_original, currency_original).

    Валюта нормализуется к строгому enum {KZT, USD} (currency.normalize): шум
    «Тенге/₸/$» приводится к канону, неизвестное → KZT (конверсии нет). Так
    currency_original всегда каноничен («USD» или пусто), а хранимая цена — KZT.
    """
    if normalize_currency(currency) is Currency.USD:
        return round(float(price) * settings.usd_kzt_rate, 2), float(price), Currency.USD.value
    return float(price), None, ""


def record_price_history(db: Session, clinic_id: int, service_id: int, price: float) -> None:
    """Логирует цену в историю, только если она ОТЛИЧАЕТСЯ от последней записанной."""
    last = (
        db.query(PriceHistory)
        .filter(PriceHistory.clinic_id == clinic_id, PriceHistory.service_id == service_id)
        .order_by(PriceHistory.recorded_at.desc(), PriceHistory.id.desc())
        .first()
    )
    if last is not None and float(last.price) == float(price):
        return
    db.add(PriceHistory(clinic_id=clinic_id, service_id=service_id, price=price))


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
    raw_content: str = "",
) -> IngestionResult:
    valid_from = valid_from or date.today()
    # §2.2 source_url: URL/реф источника записи (из реестра Source) — прозрачность.
    src_url = ""
    if source_id:
        _s = db.get(Source, source_id)
        if _s:
            src_url = _s.url_or_endpoint or ""
    run = IngestionRun(
        source_id=source_id,
        channel=channel,
        format=fmt,
        status="started",
        items_found=len(items),
        raw_content=(raw_content or "")[:200_000],  # raw-слой (§3.1): сырьё для аудита
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
        price_kzt, price_orig, cur_orig = to_kzt(item.price, getattr(item, "currency", "KZT"))
        cur = batch.get(sid)
        if cur is None or price_kzt < cur["price"]:
            batch[sid] = {
                "price": price_kzt,
                "raw_name": item.raw_name,
                "confidence": res.confidence,
                "duration_days": getattr(item, "duration_days", None),
                "price_original": price_orig,
                "currency_original": cur_orig,
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
                existing.parsed_at = datetime.utcnow()
                existing.is_active = True
                existing.duration_days = data["duration_days"]
                existing.price_original = data["price_original"]
                existing.currency_original = data["currency_original"]
                existing.source_url = src_url or existing.source_url
                record_price_history(db, clinic_id, sid, data["price"])
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
                parsed_at=datetime.utcnow(),
                is_active=True,
                duration_days=data["duration_days"],
                price_original=data["price_original"],
                currency_original=data["currency_original"],
                source_url=src_url,
            )
        )
        record_price_history(db, clinic_id, sid, data["price"])

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
