"""API-контракт MedArchive (Кейс 2) поверх единой платформы.

Эндпоинты ровно по ТЗ: партнёры, их услуги с тарифами резидент/нерезидент,
кто оказывает услугу, очередь несопоставленных позиций и ручное сопоставление.
Партнёр = Clinic, услуга = ServiceCatalog — переиспользуем сущности MedPrice.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..config import settings
from ..db import get_db
from ..models import Clinic, IngestionRun, Price, ServiceCatalog

router = APIRouter(prefix="/api", tags=["partners (MedArchive)"])


def _price_block(p: Price) -> dict:
    return {
        "price": float(p.price) if p.price is not None else None,
        "price_resident": float(p.price_resident) if p.price_resident is not None else None,
        "price_nonresident": float(p.price_nonresident) if p.price_nonresident is not None else None,
        "currency": p.currency,
        "valid_from": p.valid_from.isoformat() if p.valid_from else None,
        "match_confidence": round(p.match_confidence or 0.0, 3),
    }


@router.get("/partners")
def list_partners(city: str | None = None, db: Session = Depends(get_db)):
    """Список партнёров с числом услуг (фильтр по городу)."""
    counts = dict(
        db.query(Price.clinic_id, func.count(Price.id)).group_by(Price.clinic_id).all()
    )
    q = db.query(Clinic)
    if city:
        q = q.filter(Clinic.city.ilike(f"%{city}%"))
    out = []
    for c in q.all():
        out.append({
            "partner_id": c.id, "name": c.name, "city": c.city,
            "address": c.address, "phone": c.phone,
            "services_count": int(counts.get(c.id, 0)),
        })
    out.sort(key=lambda x: -x["services_count"])
    return out


@router.get("/partners/{partner_id}/services")
def partner_services(partner_id: uuid.UUID, db: Session = Depends(get_db)):
    """Все услуги партнёра с ценами резидент/нерезидент."""
    partner = db.get(Clinic, partner_id)
    if not partner:
        raise HTTPException(404, "Партнёр не найден")
    rows = (
        db.query(Price, ServiceCatalog)
        .outerjoin(ServiceCatalog, Price.service_id == ServiceCatalog.id)
        .filter(Price.clinic_id == partner_id)
        .all()
    )
    services = []
    for p, svc in rows:
        services.append({
            "service_id": p.service_id,
            "service_name": svc.canonical_name if svc else p.raw_name,
            "specialty": getattr(svc, "specialty", "") if svc else "",
            "category": svc.category if svc else "",
            "tarificator_code": p.tarificator_code or (getattr(svc, "tarificator_code", "") if svc else ""),
            "service_name_raw": p.raw_name,
            **_price_block(p),
        })
    return {
        "partner_id": partner.id, "name": partner.name, "city": partner.city,
        "address": partner.address, "phone": partner.phone,
        "services": services,
    }


@router.get("/services/{service_id}/partners")
def service_partners(service_id: uuid.UUID, db: Session = Depends(get_db)):
    """Список партнёров, оказывающих услугу, с ценами (от дешёвой к дорогой)."""
    svc = db.get(ServiceCatalog, service_id)
    if not svc:
        raise HTTPException(404, "Услуга не найдена")
    rows = (
        db.query(Price, Clinic)
        .join(Clinic, Price.clinic_id == Clinic.id)
        .filter(Price.service_id == service_id)
        .all()
    )
    partners = []
    for p, c in rows:
        partners.append({
            "partner_id": c.id, "name": c.name, "city": c.city,
            "address": c.address, "phone": c.phone,
            **_price_block(p),
        })
    partners.sort(key=lambda x: (x["price_resident"] or x["price"] or 1e18))
    return {
        "service_id": svc.id, "service_name": svc.canonical_name,
        "category": svc.category, "tarificator_code": getattr(svc, "tarificator_code", ""),
        "partners": partners,
    }


@router.get("/unmatched")
def unmatched_queue(limit: int = 200, db: Session = Depends(get_db)):
    """Очередь несопоставленных позиций (уверенность ниже порога) — для операторов."""
    # unmatched = не замаплено на справочник (service_id IS NULL) — оператору в очередь.
    rows = (
        db.query(Price, Clinic, ServiceCatalog)
        .join(Clinic, Price.clinic_id == Clinic.id)
        .outerjoin(ServiceCatalog, Price.service_id == ServiceCatalog.id)
        .filter(Price.service_id.is_(None))
        .order_by(Price.match_confidence.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "price_id": p.id, "partner_id": c.id, "partner": c.name,
            "service_name_raw": p.raw_name,
            "service_code_source": p.service_code_source,
            "current_service_id": p.service_id,
            "current_service": svc.canonical_name if svc else None,
            "price": float(p.price) if p.price is not None else None,
            "match_confidence": round(p.match_confidence or 0.0, 3),
        }
        for p, c, svc in rows
    ]


class MatchIn(BaseModel):
    price_id: int
    service_id: uuid.UUID


@router.post("/match", dependencies=[Depends(require_admin)])
def manual_match(body: MatchIn, db: Session = Depends(get_db)):
    """Ручное сопоставление позиции прайса с услугой справочника (оператор)."""
    price = db.get(Price, body.price_id)
    if not price:
        raise HTTPException(404, "Позиция не найдена")
    svc = db.get(ServiceCatalog, body.service_id)
    if not svc:
        raise HTTPException(404, "Услуга справочника не найдена")
    # запоминаем сырое имя как синоним → следующий раз сматчится автоматически
    syns = list(svc.synonyms or [])
    if price.raw_name and price.raw_name not in syns:
        syns.append(price.raw_name)
        svc.synonyms = syns
    price.service_id = svc.id
    price.match_confidence = 1.0
    price.tarificator_code = getattr(svc, "tarificator_code", "") or price.tarificator_code
    db.commit()
    return {"ok": True, "price_id": price.id, "service_id": svc.id, "service": svc.canonical_name}


@router.get("/archive/quality")
def archive_quality(db: Session = Depends(get_db)):
    """Метрики качества обработки архива для дашборда (документы, % нормализации, очередь)."""
    total_prices = db.query(func.count(Price.id)).scalar() or 0
    unmatched = db.query(func.count(Price.id)).filter(Price.service_id.is_(None)).scalar() or 0
    docs = db.query(func.count(IngestionRun.id)).filter(IngestionRun.file_name != "").scalar() or 0
    with_codes = db.query(func.count(Price.id)).filter(Price.tarificator_code != "").scalar() or 0
    matched = total_prices - unmatched
    auto_rate = round(100.0 * matched / max(total_prices, 1), 1)
    return {
        "documents": docs,
        "positions": total_prices,
        "auto_normalized": matched,
        "auto_rate_percent": auto_rate,
        "unmatched_queue": unmatched,
        "with_tarificator_code": with_codes,
        "goal_70_met": auto_rate >= 70,
    }
