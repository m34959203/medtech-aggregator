"""Приём архива партнёрских прайсов (MedArchive): документ → позиции →
валидации → нормализация (code-first) → цены с тарифами резидент/нерезидент.

Параллелен single-price пути MedPrice (ingestion/service.py) и не ломает его:
пишет те же таблицы Price/IngestionRun, но заполняет MedArchive-поля.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..config import settings
from ..models import IngestionRun, Price
from .archive_extractor import ArchiveItem
from .normalizer import Normalizer
from .service import record_price_history
from .storage import store_original


def _validate(item: ArchiveItem, today: date) -> list[str]:
    """Проверки ТЗ MedArchive. → список предупреждений (пустой = чисто)."""
    warns: list[str] = []
    primary = item.price_resident or item.price_original
    if not primary or primary <= 0:
        warns.append("price<=0")
    if not item.name or not item.name.strip():
        warns.append("empty_name")
    if (item.price_resident and item.price_nonresident
            and item.price_nonresident < item.price_resident):
        warns.append("nonresident<resident")
    return warns


def ingest_archive(
    db: Session,
    *,
    clinic_id: int,
    file_name: str,
    fmt: str,
    items: list[ArchiveItem],
    raw_content: str = "",
    valid_from: date | None = None,
    normalizer: Normalizer | None = None,
    content: bytes | None = None,
) -> dict:
    """Принимает позиции ОДНОГО документа-прайса. → метрики качества по документу.

    Если передан `content` (байты оригинала) — сохраняет исходный файл на диск
    (§2.1/§5: оригиналы не удаляются) и проставляет `IngestionRun.file_path`.
    """
    valid_from = valid_from or date.today()
    today = date.today()
    run = IngestionRun(
        channel="push", format=fmt, status="started",
        items_found=len(items), file_name=file_name,
        raw_content=(raw_content or "")[:200_000],
        # §3.2 PriceDocument: партнёр-источник и дата вступления прайса в силу.
        clinic_id=clinic_id, effective_date=valid_from,
    )
    db.add(run)
    db.flush()
    # §2.1/§5: сохраняем ОРИГИНАЛ под run_id для повторной обработки и аудита.
    if content is not None:
        try:
            run.file_path = store_original(run.id, file_name, content)
        except OSError as e:  # хранилище недоступно — не валим приём, помечаем в логе
            run.file_path = ""
            run.message = f"storage_error: {type(e).__name__}"

    nz = normalizer or Normalizer(db)
    threshold = settings.match_confidence_threshold

    matched = needs_review = skipped = anomalies = warned = 0
    # дедуп внутри документа: сопоставленные — по service_id, несопоставленные —
    # по сырому имени (берём минимальный резидентский тариф).
    batch: dict[object, dict] = {}

    for item in items:
        warns = _validate(item, today)
        primary = item.price_resident or item.price_original
        if "price<=0" in warns or "empty_name" in warns or primary is None:
            skipped += 1
            continue
        if warns:
            warned += 1
        svc, conf = nz.match_archive(item.name, item.code)
        if svc is not None and conf >= threshold:
            matched += 1
        else:
            needs_review += 1
        key = svc.id if svc is not None else f"raw::{item.name.lower()}"
        cur = batch.get(key)
        if cur is None or primary < cur["price"]:
            batch[key] = {
                "service_id": svc.id if svc is not None else None,
                "price": float(primary),
                "resident": float(item.price_resident) if item.price_resident else None,
                "nonresident": float(item.price_nonresident) if item.price_nonresident else None,
                "raw_name": item.name,
                "code_source": item.code or "",
                "tarif_code": (getattr(svc, "tarificator_code", "") if svc is not None else "") or (item.code or ""),
                "confidence": conf if svc is not None else 0.0,
            }

    for data in batch.values():
        sid = data["service_id"]
        existing = None
        if sid is not None:
            existing = (
                db.query(Price)
                .filter(Price.clinic_id == clinic_id, Price.service_id == sid)
                .order_by(Price.valid_from.desc())
                .first()
            )
        # аномалия: цена изменилась >50% относительно предыдущей версии
        if existing and existing.price and float(existing.price) > 0:
            if abs(data["price"] - float(existing.price)) / float(existing.price) > 0.5:
                anomalies += 1
        if existing:
            # версионирование: старую цену — в историю, актуальную обновляем
            existing.price = data["price"]
            existing.price_resident = data["resident"]
            existing.price_nonresident = data["nonresident"]
            existing.raw_name = data["raw_name"]
            existing.source_type = "upload"
            existing.run_id = run.id
            existing.service_code_source = data["code_source"]
            existing.tarificator_code = data["tarif_code"]
            existing.match_confidence = data["confidence"]
            existing.valid_from = valid_from
            record_price_history(db, clinic_id, sid, data["price"])
        else:
            db.add(Price(
                clinic_id=clinic_id, service_id=sid, run_id=run.id,
                source_type="upload", raw_name=data["raw_name"],
                price=data["price"], price_resident=data["resident"],
                price_nonresident=data["nonresident"],
                service_code_source=data["code_source"],
                tarificator_code=data["tarif_code"],
                currency="KZT", match_confidence=data["confidence"],
                valid_from=valid_from,
            ))
            if sid is not None:
                record_price_history(db, clinic_id, sid, data["price"])

    deduped = len(batch)
    auto_rate = round(100.0 * matched / max(matched + needs_review, 1), 1)
    run.status = "needs_review" if needs_review > matched else "normalized"
    run.matched = matched
    run.needs_review = needs_review
    run.message = (
        f"Документ '{file_name}': позиций {len(items)}, услуг {deduped}, "
        f"auto-match {matched} ({auto_rate}%), на проверку {needs_review}, "
        f"пропущено {skipped}, аномалий {anomalies}, предупреждений {warned}"
    )
    db.commit()
    return {
        "file": file_name, "format": fmt, "run_id": run.id,
        "items": len(items), "services": deduped,
        "matched": matched, "needs_review": needs_review,
        "skipped": skipped, "anomalies": anomalies, "warned": warned,
        "auto_rate": auto_rate,
        "with_code": sum(1 for it in items if it.code),
        "parse_status": run.status, "stored": bool(run.file_path),
    }
