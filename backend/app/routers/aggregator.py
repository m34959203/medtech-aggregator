"""Агрегатор (Кейс 2): поиск и сравнение цен по нормализованному справочнику."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Clinic, Price, ServiceCatalog
from ..schemas import PriceOffer, ServiceComparison, ServiceOut

router = APIRouter(prefix="/api", tags=["aggregator"])


@router.get("/categories", response_model=list[str])
def categories(db: Session = Depends(get_db)):
    rows = db.query(distinct(ServiceCatalog.category)).order_by(ServiceCatalog.category).all()
    return [r[0] for r in rows if r[0]]


@router.get("/cities", response_model=list[str])
def cities(db: Session = Depends(get_db)):
    rows = db.query(distinct(Clinic.city)).order_by(Clinic.city).all()
    return [r[0] for r in rows if r[0]]


@router.get("/services", response_model=list[ServiceOut])
def list_services(
    q: str | None = Query(None, description="поиск по названию"),
    category: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(ServiceCatalog)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(func.lower(ServiceCatalog.canonical_name).like(like))
    if category:
        query = query.filter(ServiceCatalog.category == category)
    return query.order_by(ServiceCatalog.canonical_name).limit(limit).all()


def _build_comparison(db: Session, service: ServiceCatalog, city, max_price, sort) -> ServiceComparison:
    q = (
        db.query(Price, Clinic)
        .join(Clinic, Price.clinic_id == Clinic.id)
        .filter(Price.service_id == service.id)
    )
    if city:
        q = q.filter(Clinic.city == city)
    if max_price is not None:
        q = q.filter(Price.price <= max_price)

    offers: list[PriceOffer] = []
    for price, clinic in q.all():
        offers.append(
            PriceOffer(
                clinic_id=clinic.id,
                clinic_name=clinic.name,
                city=clinic.city,
                district=clinic.district,
                address=clinic.address,
                lat=clinic.lat,
                lng=clinic.lng,
                phone=clinic.phone,
                price=float(price.price),
                currency=price.currency,
                raw_name=price.raw_name,
                source_type=price.source_type,
                match_confidence=price.match_confidence,
                valid_from=price.valid_from,
            )
        )

    reverse = sort == "price_desc"
    offers.sort(key=lambda o: o.price, reverse=reverse)
    prices = [o.price for o in offers] or [0.0]
    return ServiceComparison(
        service_id=service.id,
        canonical_name=service.canonical_name,
        category=service.category,
        offers_count=len(offers),
        min_price=min(prices),
        max_price=max(prices),
        offers=offers,
    )


@router.get("/compare/{service_id}", response_model=ServiceComparison)
def compare(
    service_id: int,
    city: str | None = None,
    max_price: float | None = None,
    sort: str = Query("price_asc", pattern="^(price_asc|price_desc)$"),
    db: Session = Depends(get_db),
):
    service = db.get(ServiceCatalog, service_id)
    if not service:
        raise HTTPException(404, "Услуга не найдена")
    return _build_comparison(db, service, city, max_price, sort)


@router.get("/search", response_model=list[ServiceComparison])
def search(
    q: str | None = None,
    city: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    sort: str = "price_asc",
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Поиск услуг + сводка сравнения по каждой (для главной витрины)."""
    query = db.query(ServiceCatalog)
    if q:
        query = query.filter(func.lower(ServiceCatalog.canonical_name).like(f"%{q.lower()}%"))
    if category:
        query = query.filter(ServiceCatalog.category == category)

    # только услуги, у которых есть хотя бы одна цена
    services = query.order_by(ServiceCatalog.canonical_name).limit(limit * 3).all()
    results: list[ServiceComparison] = []
    for svc in services:
        cmp = _build_comparison(db, svc, city, max_price, sort)
        if cmp.offers_count > 0:
            results.append(cmp)
        if len(results) >= limit:
            break
    return results
