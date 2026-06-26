"""Петля обратной связи «цена неверная» (Tier-1, доверие к данным).

Пользователь жмёт на карточке «цена неверная» → жалоба попадает в очередь на
ручную проверку. Дёшево и резко повышает доверие к агрегатору.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from ..db import get_db
from ..ratelimit import rate_limit
from ..auth import require_admin
from ..models import PriceReport
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class PriceReportIn(BaseModel):
    clinic_id: uuid.UUID | None = None
    clinic_name: str = ""
    service: str = ""
    price: float | None = None
    note: str = ""


class PriceReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    clinic_id: uuid.UUID | None
    clinic_name: str
    service: str
    price: float | None
    note: str
    status: str
    created_at: datetime


@router.post("/price-report", response_model=PriceReportOut, dependencies=[Depends(rate_limit("report", 15))])
def report_price(payload: PriceReportIn, db: Session = Depends(get_db)):
    report = PriceReport(
        clinic_id=payload.clinic_id,
        clinic_name=payload.clinic_name[:300],
        service=payload.service[:300],
        price=payload.price,
        note=payload.note[:1000],
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("/price-reports", response_model=list[PriceReportOut], dependencies=[Depends(require_admin)])
def list_reports(status: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(PriceReport)
    if status:
        q = q.filter(PriceReport.status == status)
    return q.order_by(PriceReport.created_at.desc()).limit(limit).all()
