"""Human-in-the-loop ревью (Спринт-2): оператор разбирает спорные сопоставления
и жалобы «цена неверная». Статус needs_review уже есть в данных — здесь экран и действия.

Очередь = цены с уверенностью ниже порога + новые жалобы. Действия по цене:
- confirm  — подтвердить сопоставление (уверенность → 1.0, выходит из очереди);
- reassign — переназначить на другую услугу (target_service_id) + подтвердить;
- reject   — удалить ошибочную цену.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Clinic, Price, PriceReport, ServiceCatalog

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/queue")
def review_queue(limit: int = 200, db: Session = Depends(get_db)):
    """Очередь на ручную проверку: низкая уверенность + новые жалобы."""
    threshold = settings.match_confidence_threshold
    rows = (
        db.query(Price, Clinic, ServiceCatalog)
        .join(Clinic, Price.clinic_id == Clinic.id)
        .join(ServiceCatalog, Price.service_id == ServiceCatalog.id)
        .filter(Price.match_confidence < threshold)
        .order_by(Price.match_confidence)
        .limit(limit)
        .all()
    )
    low = [
        {
            "price_id": p.id,
            "clinic_id": c.id,
            "clinic_name": c.name,
            "city": c.city,
            "service_id": s.id,
            "canonical_name": s.canonical_name,
            "raw_name": p.raw_name,
            "price": float(p.price),
            "currency": p.currency,
            "match_confidence": p.match_confidence,
        }
        for p, c, s in rows
    ]
    reports = [
        {
            "id": r.id, "clinic_name": r.clinic_name, "service": r.service,
            "price": float(r.price) if r.price is not None else None,
            "note": r.note, "created_at": r.created_at.isoformat(),
        }
        for r in db.query(PriceReport)
        .filter(PriceReport.status == "new")
        .order_by(PriceReport.created_at.desc())
        .limit(limit)
        .all()
    ]
    return {"threshold": threshold, "low_confidence": low, "reports": reports}


class PriceReviewAction(BaseModel):
    action: str  # confirm | reassign | reject
    target_service_id: int | None = None


@router.post("/price/{price_id}")
def review_price(price_id: int, body: PriceReviewAction, db: Session = Depends(get_db)):
    price = db.get(Price, price_id)
    if not price:
        raise HTTPException(404, "Цена не найдена")
    if body.action == "confirm":
        price.match_confidence = 1.0  # подтверждено человеком — высшая уверенность
    elif body.action == "reassign":
        target = db.get(ServiceCatalog, body.target_service_id or 0)
        if not target:
            raise HTTPException(422, "Не указана корректная услуга для переназначения")
        price.service_id = target.id
        price.match_confidence = 1.0
    elif body.action == "reject":
        db.delete(price)
    else:
        raise HTTPException(422, "action: confirm | reassign | reject")
    db.commit()
    return {"ok": True, "action": body.action}


class ReportStatus(BaseModel):
    status: str  # reviewed | fixed


@router.post("/report/{report_id}")
def review_report(report_id: int, body: ReportStatus, db: Session = Depends(get_db)):
    report = db.get(PriceReport, report_id)
    if not report:
        raise HTTPException(404, "Жалоба не найдена")
    if body.status not in ("reviewed", "fixed"):
        raise HTTPException(422, "status: reviewed | fixed")
    report.status = body.status
    db.commit()
    return {"ok": True, "status": body.status}
