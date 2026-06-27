"""CRUD клиник и их источников данных."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..models import Clinic, Price, Source
from ..schemas import ClinicOut, PriceOut

router = APIRouter(prefix="/api/clinics", tags=["clinics"])


class ClinicIn(BaseModel):
    name: str
    city: str = ""
    district: str = ""
    address: str = ""
    lat: float | None = None
    lng: float | None = None
    phone: str = ""
    working_hours: str = ""
    website: str = ""
    rating: float | None = None
    online_booking: bool | None = None


@router.get("", response_model=list[ClinicOut])
def list_clinics(city: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Clinic)
    if city:
        q = q.filter(Clinic.city == city)
    return q.order_by(Clinic.name).all()


@router.post("", response_model=ClinicOut, dependencies=[Depends(require_admin)])
def create_clinic(payload: ClinicIn, db: Session = Depends(get_db)):
    clinic = Clinic(**payload.model_dump())
    db.add(clinic)
    db.commit()
    db.refresh(clinic)
    return clinic


@router.get("/{clinic_id}", response_model=ClinicOut)
def get_clinic(clinic_id: uuid.UUID, db: Session = Depends(get_db)):
    clinic = db.get(Clinic, clinic_id)
    if not clinic:
        raise HTTPException(404, "Клиника не найдена")
    return clinic


@router.get("/{clinic_id}/prices", response_model=list[PriceOut])
def clinic_prices(clinic_id: uuid.UUID, db: Session = Depends(get_db)):
    return db.query(Price).filter(Price.clinic_id == clinic_id).all()


@router.get("/{clinic_id}/profile")
def clinic_profile(clinic_id: uuid.UUID, db: Session = Depends(get_db)):
    """§3.3 карточка клиники: контакты, сайт, режим работы + ВСЕ услуги с ценами
    (нормализованное имя, срок, источник, дата обновления)."""
    from ..models import ServiceCatalog
    clinic = db.get(Clinic, clinic_id)
    if not clinic:
        raise HTTPException(404, "Клиника не найдена")
    rows = (db.query(Price, ServiceCatalog)
            .outerjoin(ServiceCatalog, Price.service_id == ServiceCatalog.id)
            .filter(Price.clinic_id == clinic_id)
            .all())
    services = [{
        "service_id": p.service_id,
        "name": (svc.canonical_name if svc else p.raw_name),
        "raw_name": p.raw_name,
        "price": float(p.price),
        "currency": p.currency,
        "duration_days": getattr(p, "duration_days", None),
        "source_type": p.source_type,
        "valid_from": p.valid_from.isoformat() if p.valid_from else None,
        "is_active": getattr(p, "is_active", True) is not False,  # NULL легаси → активна
    } for p, svc in rows]
    services.sort(key=lambda s: s["price"])
    # §3.3 «ссылка на сайт»: если у клиники нет website — фолбэк на URL источника,
    # откуда снят прайс (Price.source_url), чтобы пользователь мог перейти к первоисточнику.
    website = clinic.website or ""
    if not website:
        website = next((getattr(p, "source_url", "") for p, _ in rows
                        if getattr(p, "source_url", "")), "")
    return {
        "id": clinic.id, "name": clinic.name, "city": clinic.city,
        "district": clinic.district, "address": clinic.address, "phone": clinic.phone,
        "working_hours": clinic.working_hours or "", "website": website,
        "rating": clinic.rating, "online_booking": clinic.online_booking,
        "lat": clinic.lat, "lng": clinic.lng,
        "services_count": len(services), "services": services,
    }
