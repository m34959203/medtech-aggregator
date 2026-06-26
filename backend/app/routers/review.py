"""Human-in-the-loop ревью (Спринт-2): оператор разбирает спорные сопоставления
и жалобы «цена неверная». Статус needs_review уже есть в данных — здесь экран и действия.

Очередь = цены с уверенностью ниже порога + новые жалобы. Действия по цене:
- confirm  — подтвердить сопоставление (уверенность → 1.0, выходит из очереди);
- reassign — переназначить на другую услугу (target_service_id) + подтвердить;
- reject   — удалить ошибочную цену.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from .. import llm
from ..config import settings
from ..db import get_db
from ..models import Clinic, Price, PriceReport, ServiceCatalog

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/queue")
def review_queue(limit: int = 200, db: Session = Depends(get_db)):
    """Очередь на ручную проверку: низкая уверенность + новые жалобы."""
    threshold = settings.match_confidence_threshold
    rows = (
        db.query(Price, Clinic, ServiceCatalog)
        .join(Clinic, Price.clinic_id == Clinic.id)
        .join(ServiceCatalog, Price.service_id == ServiceCatalog.id)
        .filter(Price.match_confidence < threshold)
        .order_by(Price.match_confidence)
        .limit(limit)
        .all()
    )
    low = [
        {
            "price_id": p.id,
            "clinic_id": c.id,
            "clinic_name": c.name,
            "city": c.city,
            "service_id": s.id,
            "canonical_name": s.canonical_name,
            "raw_name": p.raw_name,
            "price": float(p.price),
            "currency": p.currency,
            "match_confidence": p.match_confidence,
        }
        for p, c, s in rows
    ]
    reports = [
        {
            "id": r.id, "clinic_name": r.clinic_name, "service": r.service,
            "price": float(r.price) if r.price is not None else None,
            "note": r.note, "created_at": r.created_at.isoformat(),
        }
        for r in db.query(PriceReport)
        .filter(PriceReport.status == "new")
        .order_by(PriceReport.created_at.desc())
        .limit(limit)
        .all()
    ]
    return {"threshold": threshold, "low_confidence": low, "reports": reports}


class PriceReviewAction(BaseModel):
    action: str  # confirm | reassign | reject | new
    target_service_id: int | None = None


def _new_service_from_raw(db: Session, raw_name: str) -> ServiceCatalog:
    """Создать (или найти) услугу из сырого имени — для «реальная услуга, но в
    справочнике её нет». Имя чистим минимально; категория 'Прочее' (оператор/каталог
    уточнит). Идемпотентно по canonical_name."""
    name = (raw_name or "").strip()[:255] or "Без названия"
    existing = db.query(ServiceCatalog).filter(ServiceCatalog.canonical_name == name).first()
    if existing:
        return existing
    svc = ServiceCatalog(canonical_name=name, category="Прочее", synonyms=[])
    db.add(svc)
    db.flush()  # нужен id до reassign
    return svc


def _apply_review(db: Session, price: Price, action: str, target_service_id: int | None) -> bool:
    """Применить одно действие к цене. True — применено, False — нечего/невалидно."""
    if action == "confirm":
        price.match_confidence = 1.0
    elif action == "reassign":
        target = db.get(ServiceCatalog, target_service_id or 0)
        if not target:
            return False
        price.service_id = target.id
        price.match_confidence = 1.0
    elif action == "new":
        svc = _new_service_from_raw(db, price.raw_name)
        price.service_id = svc.id
        price.match_confidence = 1.0
    elif action == "reject":
        db.delete(price)
    else:
        return False
    return True


@router.post("/price/{price_id}")
def review_price(price_id: int, body: PriceReviewAction, db: Session = Depends(get_db)):
    price = db.get(Price, price_id)
    if not price:
        raise HTTPException(404, "Цена не найдена")
    if not _apply_review(db, price, body.action, body.target_service_id):
        raise HTTPException(422, "action: confirm | reassign | reject | new (для reassign нужен target_service_id)")
    db.commit()
    return {"ok": True, "action": body.action}


# ---- ИИ-разбор очереди (retrieval-injection: справочник = источник истины) ----
def _ai_candidates(db: Session, raw: str, current_id: int, k: int = 8) -> list[ServiceCatalog]:
    """Top-K кандидатов справочника под сырое имя (fuzzy) + текущая привязка."""
    cats = db.query(ServiceCatalog).all()
    if not cats:
        return []
    names = {c.id: c.canonical_name for c in cats}
    scored = process.extract(raw, names, scorer=fuzz.token_set_ratio, limit=k)
    ids = [m[2] for m in scored]
    if current_id and current_id not in ids:
        ids.append(current_id)
    by_id = {c.id: c for c in cats}
    return [by_id[i] for i in ids if i in by_id]


def _ai_decide(raw: str, current: ServiceCatalog, candidates: list[ServiceCatalog]) -> dict | None:
    """LLM выбирает действие, ВЫБИРАЯ из кандидатов справочника (не выдумывает)."""
    lines = "\n".join(f"{c.id}) {c.canonical_name} [{c.category}]" for c in candidates)
    prompt = (
        "Ты — медицинский нормализатор прайсов клиник Казахстана. Справочник услуг — "
        "ИСТОЧНИК ИСТИНЫ; не придумывай услуги вне списка кандидатов.\n"
        f'Позиция из прайса: "{raw}"\n'
        f'Текущая привязка: id={current.id} "{current.canonical_name}"\n'
        f"Кандидаты справочника:\n{lines}\n\n"
        "Действия:\n"
        "- confirm: текущая привязка — та же услуга (просто низкая fuzzy-оценка).\n"
        "- reassign: правильная услуга есть среди кандидатов под ДРУГИМ id (укажи service_id).\n"
        "- new: это реальная мед.услуга/анализ, но подходящей среди кандидатов нет — оставить отдельной услугой.\n"
        "- junk: это НЕ медицинская услуга (рекламный заголовок/пакет/мусор) — удалить.\n"
        'Ответ СТРОГО JSON: {"action":"confirm|reassign|new|junk",'
        '"service_id":<id из кандидатов или null>,"reason":"кратко","confidence":<число 0..1>}'
    )
    return llm.json_completion(prompt)


class AiResolveBody(BaseModel):
    limit: int = 25            # сколько позиций обработать за вызов (батч < CF-таймаута)
    apply: bool = False        # применять ли уверенные решения сразу
    min_confidence: float = 0.8


@router.post("/ai-resolve")
def ai_resolve(body: AiResolveBody, db: Session = Depends(get_db)):
    """ИИ-разбор очереди: для каждой спорной цены LLM предлагает действие (выбор из
    кандидатов справочника). apply=true применяет решения с confidence ≥ min_confidence;
    остальные возвращаются как предложения для оператора. Без LLM-ключа — graceful skip."""
    threshold = settings.match_confidence_threshold
    rows = (
        db.query(Price, ServiceCatalog)
        .join(ServiceCatalog, Price.service_id == ServiceCatalog.id)
        .filter(Price.match_confidence < threshold)
        .order_by(Price.match_confidence)
        .limit(max(1, min(body.limit, 50)))
        .all()
    )
    remaining = db.query(Price).filter(Price.match_confidence < threshold).count()
    proposals: list[dict] = []
    applied = 0
    for price, current in rows:
        cands = _ai_candidates(db, price.raw_name, current.id)
        decision = _ai_decide(price.raw_name, current, cands)
        if not decision:
            proposals.append({"price_id": price.id, "raw_name": price.raw_name,
                              "action": "skip", "reason": "ИИ недоступен/не ответил", "confidence": 0.0})
            continue
        action = decision.get("action")
        sid = decision.get("service_id")
        conf = float(decision.get("confidence") or 0.0)
        prop = {"price_id": price.id, "raw_name": price.raw_name, "action": action,
                "service_id": sid, "reason": decision.get("reason", ""), "confidence": conf}
        if action == "reassign" and sid:
            t = db.get(ServiceCatalog, sid)
            prop["target_name"] = t.canonical_name if t else None
        if body.apply and action in ("confirm", "reassign", "new", "junk") and conf >= body.min_confidence:
            mapped = "reject" if action == "junk" else action
            if _apply_review(db, price, mapped, sid):
                applied += 1
                prop["applied"] = True
        proposals.append(prop)
    if body.apply:
        db.commit()
        remaining = db.query(Price).filter(Price.match_confidence < threshold).count()
    return {"processed": len(rows), "applied": applied, "remaining": remaining, "proposals": proposals}


class ReportStatus(BaseModel):
    status: str  # reviewed | fixed


@router.post("/report/{report_id}")
def review_report(report_id: int, body: ReportStatus, db: Session = Depends(get_db)):
    report = db.get(PriceReport, report_id)
    if not report:
        raise HTTPException(404, "Жалоба не найдена")
    if body.status not in ("reviewed", "fixed"):
        raise HTTPException(422, "status: reviewed | fixed")
    report.status = body.status
    db.commit()
    return {"ok": True, "status": body.status}
