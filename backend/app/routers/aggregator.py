"""Агрегатор (Кейс 1 MedPrice): поиск и сравнение цен по нормализованному справочнику."""
from __future__ import annotations

import uuid

from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from statistics import median

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from rapidfuzz import fuzz

from ..config import settings
from ..data import kz_cities
from ..db import get_db
from ..ingestion import category as category_enum
from ..ingestion import ontology, variants
from ..ingestion.normalizer import _clean
from ..models import Clinic, Price, PriceHistory, ServiceCatalog
from ..schemas import (
    ClinicCompareOut,
    CollectedRecord,
    CompareCell,
    CompareColumn,
    PriceOffer,
    ServiceComparison,
    ServiceMini,
    ServiceOut,
    ServiceVariant,
)
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["aggregator"])


def _haversine(lat1, lng1, lat2, lng2) -> float:
    """Расстояние в км между двумя точками (для сортировки по близости §3.3)."""
    r = 6371.0
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _price_trend(db: Session, service_id: uuid.UUID) -> dict | None:
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


_SEARCH_FLOOR = 0.7


def _relevance(svc: ServiceCatalog, q: str) -> float:
    """Релевантность услуги запросу (0..1). Заменяет наивный подстрочный матч,
    который цеплял чужое по буквам ВНУТРИ слова («T4» → аллергокод t4, «TTG» →
    anti-tTG у IgA). Считаем по ТОКЕНАМ (целым словам), а не по подстроке:
    точное совпадение имени/синонима > точный токен-слово > префикс токена
    (автодополнение) > фраза-подстрока (≥5) > опечатки (fuzzy)."""
    ql = _clean(q)
    if not ql:
        return 0.0
    ck = _clean(svc.canonical_name)
    sks = [k for k in (_clean(s) for s in (svc.synonyms or [])) if k]
    ctoks = set(ck.split())
    stoks = {t for k in sks for t in k.split()}
    # Канон весит выше синонима на каждом тире — верная услуга всплывает над той,
    # к которой имя затесалось загрязнённым синонимом (напр. «глюкоза» у «Альбумина»).
    if ql == ck:
        return 1.0
    if ql in sks:                                   # точный синоним
        return 0.97
    if ql in ctoks:                                 # точный токен канона (УЗИ, ОАК)
        return 0.92
    if ql in stoks:                                 # точный токен синонима
        return 0.88
    if len(ql) >= 3:                                # префикс токена (автодополнение)
        if any(t.startswith(ql) for t in ctoks):
            return 0.84
        if any(t.startswith(ql) for t in stoks):
            return 0.78
    if len(ql) >= 5 and (ql in ck or any(ql in k for k in sks)):  # фраза-подстрока
        return 0.72
    if len(ql) >= 4:                                # опечатки (строже — 88)
        best = max((fuzz.token_set_ratio(ql, k) for k in [ck, *sks]), default=0)
        if best >= 88:
            return best / 100.0
    return 0.0


def _matches(svc: ServiceCatalog, q: str) -> bool:
    return _relevance(svc, q) >= _SEARCH_FLOOR


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
            .filter(Clinic.is_public.is_(True))
            .all())
    return sorted(r[0] for r in rows if r[0])


@router.get("/cities/coverage")
def cities_coverage(db: Session = Depends(get_db)):
    """Охват рынка: каждый из 90 городов справочника + флаг наличия данных."""
    rows = (db.query(Clinic.city, func.count(Clinic.id))
            .filter(Clinic.is_public.is_(True))
            .group_by(Clinic.city).all())
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
        .filter(Clinic.is_public.is_(True))  # обезличенные архив-клиники не в публичной выдаче
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
                price_kzt=float(price.price),  # §2.2 дословно
                currency=price.currency,
                service_name_norm=service.canonical_name,  # §2.2: привязка к справочнику
                raw_name=price.raw_name,
                source_type=price.source_type,
                match_confidence=price.match_confidence,
                valid_from=price.valid_from,
                working_hours=clinic.working_hours or "",
                website=clinic.website or "",
                # §2.2: реальный URL источника записи; фолбэк — сайт клиники
                source_url=getattr(price, "source_url", "") or clinic.website or "",
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
        description=service.description or "",
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
    service_id: uuid.UUID,
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


def _fresh_cheapest_by_clinic(db: Session, service_id) -> dict:
    """Для услуги — {clinic_id: (price, clinic)} с самой дешёвой СВЕЖЕЙ ценой клиники."""
    cutoff = datetime.utcnow() - timedelta(days=settings.price_freshness_days)
    date_cutoff = cutoff.date()
    out: dict = {}
    rows = (
        db.query(Price, Clinic)
        .join(Clinic, Price.clinic_id == Clinic.id)
        .filter(Price.service_id == service_id)
        .filter(Clinic.is_public.is_(True))
        .all()
    )
    for price, clinic in rows:
        fresh = getattr(price, "is_active", True) is not False
        pa = getattr(price, "parsed_at", None)
        if pa is not None:
            fresh = fresh and pa >= cutoff
        elif price.valid_from is not None:
            fresh = fresh and price.valid_from >= date_cutoff
        if not fresh:
            continue
        cur = out.get(clinic.id)
        if cur is None or float(price.price) < float(cur[0].price):
            out[clinic.id] = (price, clinic)
    return out


class ClinicCompareIn(BaseModel):
    service_ids: list[uuid.UUID]
    clinic_ids: list[uuid.UUID] | None = None   # 2–4 клиники; пусто → автоподбор
    city: str | None = None
    user_lat: float | None = None
    user_lng: float | None = None
    require_all: bool = False                    # только клиники со ВСЕМИ услугами


@router.post("/compare-clinics", response_model=ClinicCompareOut)
def compare_clinics(body: ClinicCompareIn, db: Session = Depends(get_db)):
    """§3.4: сравнительная таблица клиник по набору услуг (цена/итог/экономия/
    расстояние/рейтинг/свежесть/источник) + рекомендации. «Не найдено» вместо 0."""
    # услуги: валидируем, дедуп, сохраняем порядок (≤8)
    seen, services = set(), []
    for sid in body.service_ids[:8]:
        if sid in seen:
            continue
        svc = db.get(ServiceCatalog, sid)
        if svc:
            seen.add(sid)
            services.append(svc)
    if not services:
        raise HTTPException(422, "Не передано ни одной валидной услуги")

    # {service_id: {clinic_id: (price, clinic)}}
    by_service = {s.id: _fresh_cheapest_by_clinic(db, s.id) for s in services}

    # пул клиник: либо заданные, либо автоподбор (покрытие↓, затем суммарная цена↑)
    if body.clinic_ids:
        clinic_ids = list(dict.fromkeys(body.clinic_ids))[:4]
    else:
        coverage: dict = {}
        for sid, m in by_service.items():
            for cid, (price, clinic) in m.items():
                if body.city and clinic.city != body.city:
                    continue
                c = coverage.setdefault(cid, {"cov": 0, "total": 0.0})
                c["cov"] += 1
                c["total"] += float(price.price)
        ranked = sorted(coverage.items(), key=lambda kv: (-kv[1]["cov"], kv[1]["total"]))
        clinic_ids = [cid for cid, _ in ranked[:4]]
    if not clinic_ids:
        return ClinicCompareOut(services=[ServiceMini(service_id=s.id, canonical_name=s.canonical_name) for s in services],
                                clinics=[], max_total=0.0, recommendations={})

    # лучшая (минимальная) цена по каждой услуге среди выбранных клиник → 🏆
    best_price = {}
    for s in services:
        prices = [float(by_service[s.id][cid][0].price) for cid in clinic_ids if cid in by_service[s.id]]
        best_price[s.id] = min(prices) if prices else None

    now = datetime.utcnow()
    columns: list[CompareColumn] = []
    for cid in clinic_ids:
        clinic = db.get(Clinic, cid)
        if not clinic or not clinic.is_public:
            continue
        cells, total, found = [], 0.0, 0
        for s in services:
            hit = by_service[s.id].get(cid)
            if hit:
                price, _ = hit
                p = float(price.price)
                total += p
                found += 1
                pa = getattr(price, "parsed_at", None)
                fdays = (now - pa).days if pa else None
                cells.append(CompareCell(
                    service_id=s.id, found=True, price=p,
                    is_best=best_price[s.id] is not None and abs(p - best_price[s.id]) < 1e-6,
                    source_url=getattr(price, "source_url", "") or clinic.website or "",
                    source_type=price.source_type, parsed_at=pa, freshness_days=fdays,
                ))
            else:
                cells.append(CompareCell(service_id=s.id, found=False))
        dist = None
        if body.user_lat is not None and body.user_lng is not None and clinic.lat is not None and clinic.lng is not None:
            dist = round(_haversine(body.user_lat, body.user_lng, clinic.lat, clinic.lng), 1)
        columns.append(CompareColumn(
            clinic_id=clinic.id, clinic_name=clinic.name, city=clinic.city or "",
            address=clinic.address or "", phone=clinic.phone or "",
            lat=clinic.lat, lng=clinic.lng, rating=clinic.rating,
            online_booking=clinic.online_booking, working_hours=clinic.working_hours or "",
            website=clinic.website or "", distance_km=dist, cells=cells,
            total=round(total, 2), found_count=found, covers_all=(found == len(services)),
        ))

    if body.require_all:
        columns = [c for c in columns if c.covers_all]

    max_total = max((c.total for c in columns), default=0.0)
    for c in columns:
        c.savings_vs_max = round(max_total - c.total, 2)

    # рекомендации: дешевле / ближе / лучший баланс
    rec = {}
    full = [c for c in columns if c.covers_all] or columns
    if full:
        cheapest = min(full, key=lambda c: c.total)
        rec["cheapest"] = {"clinic_id": str(cheapest.clinic_id), "clinic_name": cheapest.clinic_name,
                           "label": f"Самый дешёвый набор — {int(cheapest.total)} ₸"}
    with_dist = [c for c in columns if c.distance_km is not None]
    if with_dist:
        nearest = min(with_dist, key=lambda c: c.distance_km)
        rec["nearest"] = {"clinic_id": str(nearest.clinic_id), "clinic_name": nearest.clinic_name,
                          "label": f"Ближайшая — {nearest.distance_km} км"}
        # лучший баланс: нормированные цена и расстояние (только среди покрывающих набор)
        pool = [c for c in (full if any(c.distance_km is not None for c in full) else columns)
                if c.distance_km is not None]
        if pool and max_total > 0:
            dmax = max(c.distance_km for c in pool) or 1.0
            balanced = min(pool, key=lambda c: 0.6 * (c.total / max_total) + 0.4 * (c.distance_km / dmax))
            rec["best_balance"] = {"clinic_id": str(balanced.clinic_id), "clinic_name": balanced.clinic_name,
                                   "label": "Лучший баланс цены и расстояния"}

    return ClinicCompareOut(
        services=[ServiceMini(service_id=s.id, canonical_name=s.canonical_name) for s in services],
        clinics=columns, max_total=round(max_total, 2), recommendations=rec,
    )


@router.get("/records", response_model=list[CollectedRecord])
def records(
    city: str | None = None,
    service_id: uuid.UUID | None = None,
    active_only: bool = False,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """§2.2: плоская выгрузка «структуры собираемых данных» — кортежи
    (клиника × услуга × цена) дословно по полям/типам ТЗ. Строгие enum
    `category`/`currency`, нормализованное имя из привязки к справочнику."""
    cutoff = datetime.utcnow() - timedelta(days=settings.price_freshness_days)
    date_cutoff = cutoff.date()

    q = (
        db.query(Price, Clinic, ServiceCatalog)
        .join(Clinic, Price.clinic_id == Clinic.id)
        .join(ServiceCatalog, Price.service_id == ServiceCatalog.id)
        .filter(Clinic.is_public.is_(True))
    )
    if city:
        q = q.filter(Clinic.city == city)
    if service_id:
        q = q.filter(Price.service_id == service_id)
    q = q.order_by(Price.id.desc())  # портативно (SQLite/PG); свежесть — в is_active

    out: list[CollectedRecord] = []
    for price, clinic, service in q.offset(offset).limit(limit).all():
        pa = getattr(price, "parsed_at", None)
        fresh = getattr(price, "is_active", True) is not False
        if pa is not None:
            fresh = fresh and pa >= cutoff
        elif price.valid_from is not None:
            fresh = fresh and price.valid_from >= date_cutoff
        if active_only and not fresh:
            continue
        out.append(
            CollectedRecord(
                clinic_id=clinic.id,
                clinic_name=clinic.name,
                city=clinic.city or "",
                address=clinic.address or "",
                phone=clinic.phone or "",
                working_hours=clinic.working_hours or "",
                source_url=getattr(price, "source_url", "") or clinic.website or "",
                service_id=service.id,
                service_name_raw=price.raw_name,
                service_name_norm=service.canonical_name,
                category=category_enum.to_enum(service.category, service.specialty, service.canonical_name),
                price_kzt=price.price,
                currency=price.currency,
                duration_days=getattr(price, "duration_days", None),
                parsed_at=pa or datetime.utcnow(),
                is_active=fresh,
            )
        )
    return out


@router.get("/suggest", response_model=list[str])
def suggest(
    q: str = Query("", description="префикс запроса для автодополнения"),
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """§3.3: автодополнение по справочнику — только РЕЛЕВАНТНЫЕ услуги (токен/префикс,
    не подстрока внутри слова), отсортированные по релевантности, затем по короткому имени."""
    if len(_clean(q)) < 2:
        return []
    scored = []
    for s in db.query(ServiceCatalog).all():
        r = _relevance(s, q)
        if r >= _SEARCH_FLOOR:
            scored.append((r, len(s.canonical_name), s.canonical_name))
    scored.sort(key=lambda t: (-t[0], t[1]))
    out, seen = [], set()
    for _r, _ln, name in scored:
        if name.lower() not in seen:
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
def service_history(service_id: uuid.UUID, db: Session = Depends(get_db)):
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
        scored = [(_relevance(s, q), s) for s in services]
        services = [s for r, s in sorted((p for p in scored if p[0] >= _SEARCH_FLOOR),
                                         key=lambda p: -p[0])]

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
