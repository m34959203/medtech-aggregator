"""Self-service портал клиники (Спринт-3) — мостик «автосбор → партнёрский актив».

Клиника заходит по выданной ссылке /clinic/<token> (passwordless, без паролей),
видит, какие её цены мы собрали, и **подтверждает или правит** их. Подтверждённая
клиникой цена помечается source_type=upload (приоритет над автосбором) и
уверенностью 1.0 — автосбор перестаёт её перетирать. Так юридический риск
парсинга превращается в партнёрский актив.
"""
from __future__ import annotations

import secrets
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..ingestion.file_parser import detect_and_parse
from ..ingestion.service import ingest_items
from ..models import Clinic, Price, ServiceCatalog

router = APIRouter(prefix="/api/portal", tags=["portal"])


def _clinic_by_token(db: Session, token: str) -> Clinic:
    clinic = db.query(Clinic).filter(Clinic.access_token == token).first()
    if not clinic or not token:
        raise HTTPException(404, "Доступ не найден. Проверьте ссылку.")
    return clinic


def ensure_token(db: Session, clinic: Clinic) -> str:
    if not clinic.access_token:
        clinic.access_token = secrets.token_urlsafe(24)
        db.commit()
    return clinic.access_token


@router.post("/issue/{clinic_id}")
def issue_access(clinic_id: int, db: Session = Depends(get_db)):
    """Админ выдаёт клинике ссылку доступа (генерит токен при первом вызове)."""
    clinic = db.get(Clinic, clinic_id)
    if not clinic:
        raise HTTPException(404, "Клиника не найдена")
    token = ensure_token(db, clinic)
    return {"clinic_id": clinic.id, "clinic_name": clinic.name, "token": token,
            "portal_path": f"/clinic/{token}"}


def _serialize(db: Session, clinic: Clinic) -> dict:
    rows = (
        db.query(Price, ServiceCatalog)
        .join(ServiceCatalog, Price.service_id == ServiceCatalog.id)
        .filter(Price.clinic_id == clinic.id)
        .order_by(ServiceCatalog.category, ServiceCatalog.canonical_name)
        .all()
    )
    prices = [
        {
            "price_id": p.id, "service": s.canonical_name, "category": s.category,
            "raw_name": p.raw_name, "price": float(p.price), "currency": p.currency,
            "source_type": p.source_type, "confirmed": p.source_type == "upload",
            "valid_from": p.valid_from.isoformat() if p.valid_from else "",
        }
        for p, s in rows
    ]
    return {
        "clinic": {"id": clinic.id, "name": clinic.name, "city": clinic.city,
                   "district": clinic.district, "address": clinic.address, "phone": clinic.phone},
        "prices": prices,
        "confirmed_count": sum(1 for p in prices if p["confirmed"]),
    }


@router.get("/{token}")
def portal_view(token: str, db: Session = Depends(get_db)):
    return _serialize(db, _clinic_by_token(db, token))


class PriceEdit(BaseModel):
    price: float


@router.patch("/{token}/price/{price_id}")
def edit_price(token: str, price_id: int, body: PriceEdit, db: Session = Depends(get_db)):
    clinic = _clinic_by_token(db, token)
    price = db.get(Price, price_id)
    if not price or price.clinic_id != clinic.id:
        raise HTTPException(404, "Цена не найдена у этой клиники")
    if body.price <= 0:
        raise HTTPException(422, "Цена должна быть больше нуля")
    price.price = body.price
    price.source_type = "upload"        # подтверждено клиникой → приоритет над автосбором
    price.match_confidence = 1.0
    price.valid_from = date.today()
    db.commit()
    return {"ok": True, "price_id": price_id, "price": body.price}


@router.post("/{token}/confirm-all")
def confirm_all(token: str, db: Session = Depends(get_db)):
    """Клиника подтверждает все свои цены как актуальные (автосбор → upload)."""
    clinic = _clinic_by_token(db, token)
    n = 0
    for price in db.query(Price).filter(Price.clinic_id == clinic.id).all():
        price.source_type = "upload"
        price.match_confidence = 1.0
        price.valid_from = date.today()
        n += 1
    db.commit()
    return {"ok": True, "confirmed": n}


@router.post("/{token}/upload")
async def portal_upload(token: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Клиника сама грузит свой прайс — официальный канал поверх автосбора."""
    clinic = _clinic_by_token(db, token)
    content = await file.read()
    fmt, items = detect_and_parse(file.filename or "", content)
    if not items:
        raise HTTPException(422, f"Не удалось извлечь позиции из файла ({fmt}).")
    return ingest_items(
        db, clinic_id=clinic.id, channel="push", source_type="upload", items=items, fmt=fmt,
    )
