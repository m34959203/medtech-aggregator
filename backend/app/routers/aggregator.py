"""Агрегатор (Кейс 2): поиск и сравнение цен по нормализованному справочнику."""
from __future__ import annotations

from statistics import median

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from ..db import get_db
from ..ingestion import variants
from ..models import Clinic, Price, PriceHistory, ServiceCatalog
from ..schemas import PriceOffer, ServiceComparison, ServiceOut, ServiceVariant

router = APIRouter(prefix="/api", tags=["aggregator"])


def _price_trend(db: Session, service_id: int) -> dict | None:
    """Динамика медианной цены по дням из истории. None, если точек < 2."""
    rows = (
        db.query(PriceHistory.recorded_at, PriceHistory.price)
        .filter(PriceHistory.service_id == service_id)
        .all()
    )
    if not rows:
        return None
    by_date: dict = {}
    for d, p in rows:
        by_date.setdefault(d, []).append(float(p))
    points = [
        {"date": d.isoformat(), "median": round(median(v), 2)}
        for d, v in sorted(by_date.items())
    ]
    if len(points) < 2:
        return None
    first, last = points[0]["median"], points[-1]["median"]
    change = round((last - first) / first * 100, 1) if first else 0.0
    return {
        "points": points,
        "change_pct": change,
        "direction": "up" if change > 1 else "down" if change < -1 else "flat",
    }


def _variants_of(db: Session, service: ServiceCatalog) -> list[ServiceVariant]:
    """Другие варианты той же базовой услуги (с ценами) — для перелинковки."""
    bk = variants.base_key(service.canonical_name)
    out: list[ServiceVariant] = []
    for s in db.query(ServiceCatalog).all():
        if s.id == service.id or variants.base_key(s.canonical_name) != bk:
            continue
        prices = [float(p[0]) for p in db.query(Price.price).filter(Price.service_id == s.id).all()]
        if not prices:
            continue
        out.append(ServiceVariant(
            service_id=s.id, canonical_name=s.canonical_name,
            label=variants.variant_label(s.canonical_name),
            offers_count=len(prices), min_price=min(prices),
        ))
    return sorted(out, key=lambda v: v.min_price)


def _matches(svc: ServiceCatalog, q: str) -> bool:
    """Совпадение запроса по эталону ИЛИ синонимам (сокращения/народные названия,
    сырые имена). Фильтруем в Python: SQLite хранит JSON-синонимы в \\uXXXX-эскейпе,
    поэтому SQL-LIKE по ним не работает с кириллицей. Справочник мал (~30 услуг)."""
    ql = q.lower().strip()
    if ql in svc.canonical_name.lower():
        return True
    return any(ql in str(syn).lower() for syn in (svc.synonyms or []))


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
    if category:
        query = query.filter(ServiceCatalog.category == category)
    items = query.order_by(ServiceCatalog.canonical_name).all()
    if q:
        items = [s for s in items if _matches(s, q)]
    return items[:limit]


def _build_comparison(db: Session, service: ServiceCatalog, city, max_price, sort,
                      with_variants: bool = False) -> ServiceComparison:
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
        attributes=variants.attributes(service.canonical_name),
        variants=_variants_of(db, service) if with_variants else [],
        price_trend=_price_trend(db, service.id) if with_variants else None,
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
    return _build_comparison(db, service, city, max_price, sort, with_variants=True)


@router.get("/services/{service_id}/history")
def service_history(service_id: int, db: Session = Depends(get_db)):
    """История/тренд медианной цены услуги — уникальный контент и SEO-магнит."""
    svc = db.get(ServiceCatalog, service_id)
    if not svc:
        raise HTTPException(404, "Услуга не найдена")
    return {"service_id": svc.id, "canonical_name": svc.canonical_name,
            "trend": _price_trend(db, svc.id)}


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
    if category:
        query = query.filter(ServiceCatalog.category == category)
    services = query.order_by(ServiceCatalog.canonical_name).all()
    if q:
        services = [s for s in services if _matches(s, q)]

    # только услуги, у которых есть хотя бы одна цена
    results: list[ServiceComparison] = []
    for svc in services:
        cmp = _build_comparison(db, svc, city, max_price, sort)
        if cmp.offers_count > 0:
            results.append(cmp)
        if len(results) >= limit:
            break
    return results
