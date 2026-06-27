"""§3.4 (опц.): подписки на снижение цены. Пользователь оставляет номер +
услугу (и опц. клинику/город); планировщик уведомляет в WhatsApp при снижении.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..config import settings
from ..db import get_db
from ..ingestion import notify
from ..models import Clinic, Price, PriceSubscription, ServiceCatalog
from ..ratelimit import rate_limit

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def current_min_price(db: Session, service_id, clinic_id=None, city: str = "") -> float | None:
    """Текущая минимальная СВЕЖАЯ цена услуги (опц. в клинике/городе)."""
    cutoff = datetime.utcnow() - timedelta(days=settings.price_freshness_days)
    date_cutoff = cutoff.date()
    q = (db.query(Price, Clinic)
         .join(Clinic, Price.clinic_id == Clinic.id)
         .filter(Price.service_id == service_id))
    if clinic_id:
        q = q.filter(Price.clinic_id == clinic_id)
    elif city:
        q = q.filter(Clinic.city == city)
    best = None
    for price, _clinic in q.all():
        fresh = getattr(price, "is_active", True) is not False
        pa = getattr(price, "parsed_at", None)
        if pa is not None:
            fresh = fresh and pa >= cutoff
        elif price.valid_from is not None:
            fresh = fresh and price.valid_from >= date_cutoff
        if not fresh:
            continue
        p = float(price.price)
        if best is None or p < best:
            best = p
    return best


class SubscribeIn(BaseModel):
    service_id: uuid.UUID
    clinic_id: uuid.UUID | None = None
    city: str | None = None
    phone: str


@router.post("", dependencies=[Depends(rate_limit("subscribe", 10))])
def subscribe(body: SubscribeIn, db: Session = Depends(get_db)):
    """Подписаться на снижение цены. Номер — для уведомления в WhatsApp."""
    if not db.get(ServiceCatalog, body.service_id):
        raise HTTPException(404, "Услуга не найдена")
    phone = re.sub(r"[^\d+]", "", body.phone or "")
    if len(re.sub(r"\D", "", phone)) < 10:
        raise HTTPException(422, "Укажите корректный номер телефона")
    # идемпотентно: одна активная подписка на (телефон, услуга, клиника)
    existing = (db.query(PriceSubscription)
                .filter(PriceSubscription.phone == phone,
                        PriceSubscription.service_id == body.service_id,
                        PriceSubscription.clinic_id == body.clinic_id,
                        PriceSubscription.active.is_(True))
                .first())
    if existing:
        return {"ok": True, "id": existing.id, "already": True}
    sub = PriceSubscription(
        service_id=body.service_id, clinic_id=body.clinic_id,
        city=(body.city or "") if not body.clinic_id else "",
        phone=phone,
        last_price=current_min_price(db, body.service_id, body.clinic_id, body.city or ""),
    )
    db.add(sub)
    db.commit()
    return {"ok": True, "id": sub.id, "tracking_price": float(sub.last_price) if sub.last_price else None}


@router.delete("/{sub_id}")
def unsubscribe(sub_id: int, db: Session = Depends(get_db)):
    sub = db.get(PriceSubscription, sub_id)
    if not sub:
        raise HTTPException(404, "Подписка не найдена")
    sub.active = False
    db.commit()
    return {"ok": True}


@router.get("", dependencies=[Depends(require_admin)])
def list_subscriptions(db: Session = Depends(get_db)):
    """Список подписок (админ)."""
    subs = db.query(PriceSubscription).order_by(PriceSubscription.created_at.desc()).all()
    out = []
    for s in subs:
        svc = db.get(ServiceCatalog, s.service_id)
        cl = db.get(Clinic, s.clinic_id) if s.clinic_id else None
        out.append({
            "id": s.id, "phone": s.phone, "active": s.active,
            "service": svc.canonical_name if svc else None,
            "clinic": cl.name if cl else None, "city": s.city or None,
            "last_price": float(s.last_price) if s.last_price is not None else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "last_notified_at": s.last_notified_at.isoformat() if s.last_notified_at else None,
        })
    return out


def check_subscriptions(db: Session) -> dict:
    """Планировщик: сверить цены, уведомить о снижениях в WhatsApp.
    first-run — фиксируем baseline без уведомления; рост — обновляем baseline вверх."""
    subs = db.query(PriceSubscription).filter(PriceSubscription.active.is_(True)).all()
    checked = notified = 0
    for s in subs:
        checked += 1
        cur = current_min_price(db, s.service_id, s.clinic_id, s.city)
        if cur is None:
            continue
        if s.last_price is None:
            s.last_price = cur
            continue
        old = float(s.last_price)
        if cur < old - 0.001:                       # снижение → уведомляем
            svc = db.get(ServiceCatalog, s.service_id)
            cl = db.get(Clinic, s.clinic_id) if s.clinic_id else None
            where = f" в «{cl.name}»" if cl else (f" в г. {s.city}" if s.city else "")
            msg = (f"💰 MedPrice: цена снизилась!\n«{svc.canonical_name if svc else 'услуга'}»{where}: "
                   f"{int(old)} → {int(cur)} ₸ (−{int(old - cur)} ₸).\n"
                   f"Отписаться — ответьте СТОП.")
            if notify.send_whatsapp(s.phone, msg):
                notified += 1
                s.last_notified_at = datetime.utcnow()
            s.last_price = cur
        elif cur > old + 0.001:                     # рост → двигаем baseline вверх
            s.last_price = cur
    db.commit()
    return {"checked": checked, "notified": notified}
