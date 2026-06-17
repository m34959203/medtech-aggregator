"""CRUD клиник и их источников данных."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

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


@router.get("", response_model=list[ClinicOut])
def list_clinics(city: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Clinic)
    if city:
        q = q.filter(Clinic.city == city)
    return q.order_by(Clinic.name).all()


@router.post("", response_model=ClinicOut)
def create_clinic(payload: ClinicIn, db: Session = Depends(get_db)):
    clinic = Clinic(**payload.model_dump())
    db.add(clinic)
    db.commit()
    db.refresh(clinic)
    return clinic


@router.get("/{clinic_id}", response_model=ClinicOut)
def get_clinic(clinic_id: int, db: Session = Depends(get_db)):
    clinic = db.get(Clinic, clinic_id)
    if not clinic:
        raise HTTPException(404, "Клиника не найдена")
    return clinic


@router.get("/{clinic_id}/prices", response_model=list[PriceOut])
def clinic_prices(clinic_id: int, db: Session = Depends(get_db)):
    return db.query(Price).filter(Price.clinic_id == clinic_id).all()
