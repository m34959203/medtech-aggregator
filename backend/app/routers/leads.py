"""Заявка на приём/услугу (Спринт-2, монетизация): пациент оставляет лид с карточки.

Простая форма «оставить заявку» закрывает воронку и даёт бизнес-модель (лиды клиникам).
Телефон обязателен — иначе лид бесполезен клинике.
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Lead

router = APIRouter(prefix="/api/leads", tags=["leads"])


class LeadIn(BaseModel):
    clinic_id: int | None = None
    clinic_name: str = ""
    service: str = ""
    price: float | None = None
    name: str = ""
    phone: str = ""


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    clinic_id: int | None
    clinic_name: str
    service: str
    price: float | None
    name: str
    phone: str
    status: str
    created_at: datetime


@router.post("", response_model=LeadOut)
def create_lead(payload: LeadIn, db: Session = Depends(get_db)):
    digits = re.sub(r"\D", "", payload.phone)
    if len(digits) < 10:
        raise HTTPException(422, "Укажите корректный телефон для связи.")
    lead = Lead(
        clinic_id=payload.clinic_id,
        clinic_name=payload.clinic_name[:300],
        service=payload.service[:300],
        price=payload.price,
        name=payload.name[:200],
        phone=payload.phone[:40],
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


@router.get("", response_model=list[LeadOut])
def list_leads(status: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(Lead)
    if status:
        q = q.filter(Lead.status == status)
    return q.order_by(Lead.created_at.desc()).limit(limit).all()
