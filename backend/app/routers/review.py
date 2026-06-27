"""Human-in-the-loop ревью (Спринт-2): оператор разбирает спорные сопоставления
и жалобы «цена неверная». Статус needs_review уже есть в данных — здесь экран и действия.

Очередь = цены с уверенностью ниже порога + новые жалобы. Действия по цене:
- confirm  — подтвердить сопоставление (уверенность → 1.0, выходит из очереди);
- reassign — переназначить на другую услугу (target_service_id) + подтвердить;
- reject   — удалить ошибочную цену.
"""
from __future__ import annotations

import uuid

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
def review_queue(limit: int = 200, run_id: int | None = None, db: Session = Depends(get_db)):
    """Очередь на ручную проверку: низкая уверенность + новые жалобы.

    `run_id` — отфильтровать позиции конкретного прогона приёма (переход из
    панели завершения «Проверить N»).
    """
    threshold = settings.match_confidence_threshold
    # OUTER JOIN: нераспознанные позиции (service_id IS NULL) — тоже на проверку.
    # INNER их прятал → счётчик «на проверке» рос, а очередь была почти пустой.
    base = (
        db.query(Price, Clinic, ServiceCatalog)
        .join(Clinic, Price.clinic_id == Clinic.id)
        .outerjoin(ServiceCatalog, Price.service_id == ServiceCatalog.id)
        .filter(Price.match_confidence < threshold)
    )
    if run_id is not None:
        base = base.filter(Price.run_id == run_id)
    total = base.count()
    rows = base.order_by(Price.match_confidence).limit(limit).all()
    low = [
        {
            "price_id": p.id,
            "clinic_id": c.id,
            "clinic_name": c.name,
            "city": c.city,
            "service_id": s.id if s else None,
            "canonical_name": s.canonical_name if s else None,
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
    return {"threshold": threshold, "total": total, "run_id": run_id,
            "low_confidence": low, "reports": reports}


class PriceReviewAction(BaseModel):
    action: str  # confirm | reassign | reject | new
    target_service_id: uuid.UUID | None = None


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


def _apply_review(db: Session, price: Price, action: str, target_service_id: uuid.UUID | None) -> bool:
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
def _ai_candidates(db: Session, raw: str, current_id, k: int = 8) -> list[ServiceCatalog]:
    """Top-K кандидатов справочника под сырое имя — ОБЪЕДИНЕНИЕ сигналов:
    fuzzy по каноническому имени, fuzzy по синонимам, семантика (эмбеддинги) +
    текущая привязка. Слабость одного сигнала (fuzzy не видит «ОАК»≈«Общий анализ
    крови»; семантика путает мед-термины) компенсируется другими — верную услугу
    в пул вытащит хотя бы один, а финальный выбор делает LLM + verify."""
    cats = db.query(ServiceCatalog).all()
    if not cats:
        return []
    by_id = {c.id: c for c in cats}
    ordered: list = []  # сохраняем порядок, без дублей

    def _push(cid):
        if cid in by_id and cid not in ordered:
            ordered.append(cid)

    # 1) fuzzy по каноническому имени
    names = {c.id: c.canonical_name for c in cats}
    for m in process.extract(raw, names, scorer=fuzz.token_set_ratio, limit=k):
        _push(m[2])
    # 2) fuzzy по синонимам (аббревиатуры/варианты написания клиник)
    syn_index = {c.id: " ".join(c.synonyms or []) for c in cats if c.synonyms}
    if syn_index:
        for m in process.extract(raw, syn_index, scorer=fuzz.token_set_ratio, limit=max(3, k // 2)):
            if m[1] >= 60:
                _push(m[2])
    # 3) семантика (эмбеддинги) — ловит смысл там, где буквы расходятся
    try:
        from ..ingestion import semantic
        if semantic.available():
            for sid, _score in semantic.match_topk(db, raw, max(3, k // 2)):
                _push(sid)
    except Exception:
        pass  # семантика опциональна — без неё остаёмся на fuzzy
    # 4) текущая привязка всегда в пуле (для choice=confirm)
    _push(current_id)
    return [by_id[i] for i in ordered]


def _ai_decide(raw: str, current: ServiceCatalog, candidates: list[ServiceCatalog]) -> dict | None:
    """LLM выбирает действие, ВЫБИРАЯ из кандидатов справочника (не выдумывает).

    Кандидаты нумеруются ПОРЯДКОВО (1..N) — LLM не умеет надёжно повторять uuid;
    выбранный номер маппим обратно в uuid услуги. Возвращает {action, service_id(uuid|None),
    reason, confidence}."""
    lines = "\n".join(f"{i}) {c.canonical_name} [{c.category}]" for i, c in enumerate(candidates, 1))
    prompt = (
        "Ты — медицинский нормализатор прайсов клиник Казахстана. Справочник услуг — "
        "ИСТОЧНИК ИСТИНЫ; не придумывай услуги вне списка кандидатов.\n"
        f'Позиция из прайса: "{raw}"\n'
        f'Текущая привязка (№1): "{current.canonical_name}"\n'
        f"Кандидаты справочника:\n{lines}\n\n"
        "Действия:\n"
        "- confirm: текущая привязка (№1) — та же услуга (просто низкая fuzzy-оценка).\n"
        "- reassign: правильная услуга есть среди кандидатов под ДРУГИМ номером (укажи choice).\n"
        "- new: это реальная мед.услуга/анализ, но подходящей среди кандидатов нет.\n"
        "- junk: это НЕ медицинская услуга (рекламный заголовок/пакет/мусор) — удалить.\n"
        'Ответ СТРОГО JSON: {"action":"confirm|reassign|new|junk",'
        '"choice":<номер кандидата или null>,"reason":"кратко","confidence":<число 0..1>}'
    )
    d = llm.json_completion(prompt)
    if not d:
        return None
    sid = None
    choice = d.get("choice")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(candidates):
            sid = candidates[idx].id
    except (TypeError, ValueError):
        sid = None
    return {"action": d.get("action"), "service_id": sid,
            "reason": d.get("reason", ""), "confidence": d.get("confidence")}


def _ai_verify_same(raw: str, target: ServiceCatalog) -> bool:
    """Независимый verify-проход: точно ли raw — ТА ЖЕ услуга, что target.

    Срезает главную ошибку reassign (~40%): ИИ путает услуги по общему слову
    («Токсокароз IgG»→«Трихомониаз IgG»). Отдельный строгий yes/no с акцентом на
    биоматериал/метод/аналит/панель. По умолчанию НЕТ (без явного да — не применяем)."""
    prompt = (
        "Ты — медицинский эксперт-нормализатор. Ответь, описывают ли две строки "
        "ОДНУ И ТУ ЖЕ медицинскую услугу/анализ. Будь строг: различия по аналиту, "
        "биоматериалу (кровь/моча/сыворотка), методу, составу панели или органу — "
        "это РАЗНЫЕ услуги.\n"
        f'Строка из прайса: "{raw}"\n'
        f'Услуга справочника: "{target.canonical_name}"\n'
        'Ответ СТРОГО JSON: {"same": true|false, "reason": "кратко"}'
    )
    d = llm.json_completion(prompt)
    return bool(d and d.get("same") is True)


class AiResolveBody(BaseModel):
    limit: int = 25            # сколько позиций обработать за вызов (батч < CF-таймаута)
    apply: bool = False        # применять ли уверенные решения сразу
    min_confidence: float = 0.8
    # Какие действия авто-применять. ВАЖНО: reassign ненадёжен (ИИ уверенно путает
    # услуги по общему слову: «арт. давление»→глазная тонометрия, «Токсокароз IgG»→
    # «Трихомониаз IgG»), поэтому по умолчанию авто-применяем только высокоточные
    # confirm/junk; reassign/new возвращаем оператору как предложения. Боевой прогон.
    auto_actions: list[str] = ["confirm", "junk"]


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
        if body.apply and action in body.auto_actions and conf >= body.min_confidence:
            # reassign — только после независимого verify (срез 40%-ошибки путаницы)
            ok_to_apply = True
            if action == "reassign":
                t = db.get(ServiceCatalog, sid) if sid else None
                ok_to_apply = bool(t) and _ai_verify_same(price.raw_name, t)
                prop["verified"] = ok_to_apply
            if ok_to_apply:
                mapped = "reject" if action == "junk" else action
                if _apply_review(db, price, mapped, sid):
                    applied += 1
                    prop["applied"] = True
        proposals.append(prop)
    if body.apply:
        db.commit()
        remaining = db.query(Price).filter(Price.match_confidence < threshold).count()
    return {"processed": len(rows), "applied": applied, "remaining": remaining, "proposals": proposals}


# ---- Перепроверка ПОДОЗРИТЕЛЬНЫХ привязок (высокая уверенность, но мимо) ----
def _suspect_bindings(db: Session, threshold: float, floor: float, scan_limit: int, offset: int):
    """Привязки с conf ≥ threshold, но семантически далёкие от своего канона.

    Сигнал — низкий косинус(raw, canonical): ошибочный reassign/fuzzy выставил
    высокую уверенность, и в обычную очередь (conf<threshold) такая запись не
    попадает. Эмбеддинги дешёвы → батч-скан; сам выбор цели — за LLM в recheck.
    Возвращает [(price, current_service, bound_cos)] по возрастанию сходства."""
    from ..ingestion import semantic
    if not semantic.available():
        return []
    rows = (
        db.query(Price, ServiceCatalog)
        .join(ServiceCatalog, Price.service_id == ServiceCatalog.id)
        .filter(Price.match_confidence >= threshold)
        .order_by(Price.id)
        .offset(max(0, offset))
        .limit(max(1, scan_limit))
        .all()
    )
    if not rows:
        return []
    import numpy as np
    raw_vecs = semantic.embed([p.raw_name for p, _ in rows])
    can_vecs = semantic.embed([s.canonical_name for _, s in rows])
    out = []
    for (p, s), rv, cv in zip(rows, raw_vecs, can_vecs):
        rv, cv = np.array(rv), np.array(cv)
        denom = (rv @ rv) ** 0.5 * (cv @ cv) ** 0.5
        bound_cos = float(rv @ cv / denom) if denom else 0.0
        if bound_cos < floor:
            out.append((p, s, bound_cos))
    out.sort(key=lambda t: t[2])
    return out


class RecheckBody(BaseModel):
    scan_limit: int = 300       # сколько привязок просканировать эмбеддингами за вызов
    offset: int = 0             # для прохода по всей базе батчами
    suspect_floor: float = 0.55 # ниже косинуса raw↔canonical — подозрительно
    apply: bool = False         # применять ли уверенные reassign (после verify)
    min_confidence: float = 0.8
    max_llm: int = 40           # потолок LLM-вызовов за один проход (стоимость/время)


@router.post("/recheck")
def recheck_bindings(body: RecheckBody, db: Session = Depends(get_db)):
    """Найти и (опц.) починить ОШИБОЧНЫЕ привязки с высокой уверенностью —
    которых нет в обычной очереди. Дёшево детектим эмбеддингами, target выбирает
    LLM из усиленного пула кандидатов, reassign применяется ТОЛЬКО после verify.
    Идемпотентно и безопасно: ложный подозреваемый просто подтверждается."""
    threshold = settings.match_confidence_threshold
    suspects = _suspect_bindings(db, threshold, body.suspect_floor, body.scan_limit, body.offset)
    proposals: list[dict] = []
    applied = 0
    llm_used = 0
    for price, current, bound_cos in suspects:
        if llm_used >= body.max_llm:
            break
        cands = _ai_candidates(db, price.raw_name, current.id)
        decision = _ai_decide(price.raw_name, current, cands)
        llm_used += 1
        if not decision:
            proposals.append({"price_id": price.id, "raw_name": price.raw_name,
                              "bound_cos": round(bound_cos, 3), "action": "skip",
                              "reason": "ИИ недоступен/не ответил"})
            continue
        action = decision.get("action")
        sid = decision.get("service_id")
        conf = float(decision.get("confidence") or 0.0)
        t = db.get(ServiceCatalog, sid) if sid else None
        prop = {"price_id": price.id, "raw_name": price.raw_name,
                "bound_cos": round(bound_cos, 3), "current_name": current.canonical_name,
                "action": action, "service_id": sid,
                "target_name": t.canonical_name if t else None,
                "reason": decision.get("reason", ""), "confidence": conf}
        if body.apply and action == "reassign" and t and conf >= body.min_confidence:
            llm_used += 1
            verified = _ai_verify_same(price.raw_name, t)
            prop["verified"] = verified
            if verified and _apply_review(db, price, "reassign", sid):
                applied += 1
                prop["applied"] = True
        proposals.append(prop)
    if body.apply:
        db.commit()
    return {"scanned_from": body.offset, "scan_limit": body.scan_limit,
            "suspects": len(suspects), "llm_used": llm_used,
            "applied": applied, "proposals": proposals}


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
