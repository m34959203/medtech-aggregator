"""Агрегатор (Кейс 1 MedPrice): поиск и сравнение цен по нормализованному справочнику."""
from __future__ import annotations

from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from statistics import median

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from ..config import settings
from ..data import kz_cities
from ..db import get_db
from ..ingestion import category as category_enum
from ..ingestion import ontology, variants
from ..models import Clinic, Price, PriceHistory, ServiceCatalog
from ..schemas import PriceOffer, ServiceComparison, ServiceOut, ServiceVariant

router = APIRouter(prefix="/api", tags=["aggregator"])


def _haversine(lat1, lng1, lat2, lng2) -> float:
    """Расстояние в км между двумя точками (для сортировки по близости §3.3)."""
    r = 6371.0
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))


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
    """§2.2: категории как ENUM ТЗ (лаборатория/приём врача/диагностика/процедура),
    но только те, что реально присутствуют в справочнике."""
    present: set[str] = set()
    for s in db.query(ServiceCatalog.category, ServiceCatalog.specialty,
                      ServiceCatalog.canonical_name).all():
        present.add(category_enum.to_enum(s[0], s[1], s[2]))
    return [c for c in category_enum.ENUM if c in present]


@router.get("/cities", response_model=list[str])
def cities(db: Session = Depends(get_db)):
    """Города для фильтра — ТОЛЬКО те, где реально есть цены (без пустых).

    Полный охват всех 90 городов РК (вкл. «зарегистрирован, данных нет») —
    в отдельном `/cities/coverage`; фильтр не засоряем пустыми городами.
    """
    rows = (db.query(distinct(Clinic.city))
            .join(Price, Price.clinic_id == Clinic.id)
            .all())
    return sorted(r[0] for r in rows if r[0])


@router.get("/cities/coverage")
def cities_coverage(db: Session = Depends(get_db)):
    """Охват рынка: каждый из 90 городов справочника + флаг наличия данных."""
    rows = db.query(Clinic.city, func.count(Clinic.id)).group_by(Clinic.city).all()
    counts: dict[str, int] = {c: n for c, n in rows if c}
    out = []
    for c in kz_cities.all_cities():
        out.append({**c, "clinics": counts.get(c["name"], 0),
                    "has_data": counts.get(c["name"], 0) > 0})
    # города с данными, но вне справочника 90 (формально шире рынка) — не теряем
    extra = sorted(set(counts) - {c["name"] for c in out})
    for name in extra:
        out.append({"name": name, "region": "", "status": 0, "status_label": "",
                    "slug": kz_cities.slugify(name), "clinics": counts[name],
                    "has_data": True})
    return out


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
                      *, min_price=None, min_rating=None, online_booking=None,
                      user_lat=None, user_lng=None, include_stale: bool = False,
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
    if min_price is not None:
        q = q.filter(Price.price >= min_price)
    if min_rating is not None:
        q = q.filter(Clinic.rating >= min_rating)
    if online_booking is not None:
        q = q.filter(Clinic.online_booking.is_(online_booking))

    # §4: не выдавать данные старше N дней как актуальные. Цена считается свежей,
    # если is_active И время парсинга/действия в окне свежести.
    cutoff = datetime.utcnow() - timedelta(days=settings.price_freshness_days)
    date_cutoff = cutoff.date()

    offers: list[PriceOffer] = []
    for price, clinic in q.all():
        # NULL (легаси/перенесённые строки) трактуем как активную — колоночный
        # default=True не применяется к ALTER-добавленным колонкам на старых строках;
        # неактивной считаем ТОЛЬКО явный False (scheduler.mark_stale_inactive).
        fresh = getattr(price, "is_active", True) is not False
        pa = getattr(price, "parsed_at", None)
        if pa is not None:
            fresh = fresh and pa >= cutoff
        elif price.valid_from is not None:
            fresh = fresh and price.valid_from >= date_cutoff
        if not include_stale and not fresh:
            continue
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
                working_hours=clinic.working_hours or "",
                website=clinic.website or "",
                source_url=clinic.website or "",
                rating=clinic.rating,
                online_booking=clinic.online_booking,
                duration_days=getattr(price, "duration_days", None),
                is_active=fresh,
                parsed_at=pa,
                price_original=float(price.price_original) if getattr(price, "price_original", None) is not None else None,
                currency_original=getattr(price, "currency_original", "") or "",
            )
        )

    # сортировка §3.3: цена возр/убыв, дата обновления, расстояние (при гео)
    if sort == "updated":
        offers.sort(key=lambda o: o.parsed_at or datetime.min, reverse=True)
    elif sort == "distance" and user_lat is not None and user_lng is not None:
        offers.sort(key=lambda o: _haversine(user_lat, user_lng, o.lat, o.lng)
                    if o.lat is not None and o.lng is not None else 1e9)
    else:
        offers.sort(key=lambda o: o.price, reverse=(sort == "price_desc"))

    prices = [o.price for o in offers] or [0.0]
    return ServiceComparison(
        service_id=service.id,
        canonical_name=service.canonical_name,
        category=service.category,
        category_enum=category_enum.to_enum(service.category, service.specialty, service.canonical_name),
        offers_count=len(offers),
        min_price=min(prices),
        max_price=max(prices),
        offers=offers,
        attributes=variants.attributes(service.canonical_name),
        variants=_variants_of(db, service) if with_variants else [],
        price_trend=_price_trend(db, service.id) if with_variants else None,
        ontology=ontology.info(service.canonical_name),
    )


@router.get("/compare/{service_id}", response_model=ServiceComparison)
def compare(
    service_id: int,
    city: str | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    min_rating: float | None = None,
    online_booking: bool | None = None,
    user_lat: float | None = None,
    user_lng: float | None = None,
    sort: str = Query("price_asc", pattern="^(price_asc|price_desc|updated|distance)$"),
    db: Session = Depends(get_db),
):
    service = db.get(ServiceCatalog, service_id)
    if not service:
        raise HTTPException(404, "Услуга не найдена")
    return _build_comparison(
        db, service, city, max_price, sort, min_price=min_price, min_rating=min_rating,
        online_booking=online_booking, user_lat=user_lat, user_lng=user_lng,
        with_variants=True,
    )


@router.get("/suggest", response_model=list[str])
def suggest(
    q: str = Query("", description="префикс запроса для автодополнения"),
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """§3.3: автодополнение строки поиска по справочнику (канонические имена + синонимы)."""
    ql = q.lower().strip()
    if len(ql) < 2:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for s in db.query(ServiceCatalog).order_by(ServiceCatalog.canonical_name).all():
        name = s.canonical_name
        hay = [name] + [str(x) for x in (s.synonyms or [])]
        if any(ql in h.lower() for h in hay) and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
        if len(out) >= limit:
            break
    return out


@router.get("/ontology")
def ontology_map(db: Session = Depends(get_db)):
    """Онтология справочника: клинические группы + код/группа/ОСМС по каждой услуге."""
    out = []
    for s in db.query(ServiceCatalog).order_by(ServiceCatalog.canonical_name).all():
        info = ontology.info(s.canonical_name)
        if info:
            out.append({"service_id": s.id, "canonical_name": s.canonical_name, **info})
    return {"groups": ontology.groups(), "services": out}


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
    min_price: float | None = None,
    min_rating: float | None = None,
    online_booking: bool | None = None,
    user_lat: float | None = None,
    user_lng: float | None = None,
    sort: str = "price_asc",
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Поиск услуг + сводка сравнения по каждой (для главной витрины)."""
    services = db.query(ServiceCatalog).order_by(ServiceCatalog.canonical_name).all()
    # категория §3.3: матчим по enum-категории ТЗ (а не по сырому тексту справочника)
    if category:
        cl = category.lower()
        services = [s for s in services
                    if category_enum.to_enum(s.category, s.specialty, s.canonical_name) == cl
                    or cl in (s.category or "").lower()]
    if q:
        services = [s for s in services if _matches(s, q)]

    # только услуги, у которых есть хотя бы одна цена
    results: list[ServiceComparison] = []
    for svc in services:
        cmp = _build_comparison(
            db, svc, city, max_price, sort, min_price=min_price, min_rating=min_rating,
            online_booking=online_booking, user_lat=user_lat, user_lng=user_lng,
        )
        if cmp.offers_count > 0:
            results.append(cmp)
        if len(results) >= limit:
            break
    return results
