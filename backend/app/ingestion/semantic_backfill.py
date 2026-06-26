"""Семантический второй проход по несопоставленным позициям архива.

Очередь unmatched — это в основном НАСТОЯЩИЕ услуги, чьи формулировки не совпали
с официальным справочником буквально (синонимов в справочнике нет). Понять смысл —
работа эмбеддингов. Дизайн БАТЧЕВЫЙ (в отличие от per-item в нормализаторе):
эмбеддинги справочника и уникальных сырых имён считаются ОДИН раз, сопоставление —
векторным умножением матриц. Это держит проход в секундах-минутах, а не часах.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Price, ServiceCatalog


# Порог АВТО-применения семантики намеренно ВЫСОКИЙ. На multilingual-MiniLM
# медицинские косинусы сжаты, и в зоне 0.72–0.85 матчи ненадёжны («УЗИ стоп»→
# «УЗИ поджелудочной»). Ложный маппинг хуже, чем unmatched: он портит сравнение
# цен. Поэтому авто — только ≥0.85 (точность > охват), остальное — в очередь
# оператору как подсказка. Это соответствует ТЗ (cosine>0.85 → авто, иначе ревью).
SEMANTIC_AUTO_THRESHOLD = 0.85


def backfill_unmatched(db: Session, *, threshold: float | None = None, batch: int = 256) -> dict:
    """Досопоставляет unmatched ближайшей по СМЫСЛУ услугой — только при высокой уверенности."""
    from . import semantic
    if not semantic.available():
        return {"available": False, "assigned": 0, "checked": 0}
    import numpy as np

    thr = threshold if threshold is not None else SEMANTIC_AUTO_THRESHOLD
    fuzzy_thr = settings.match_confidence_threshold

    catalog = db.query(ServiceCatalog).all()
    if not catalog:
        return {"available": True, "assigned": 0, "checked": 0}
    cat_vecs = np.vstack(semantic.embed([c.canonical_name for c in catalog]))  # (C, dim), L2-норм.

    prices = db.query(Price).filter(Price.match_confidence < fuzzy_thr).all()
    names = sorted({p.raw_name for p in prices if p.raw_name and len(p.raw_name) > 3})
    vecs: dict[str, object] = {}
    for i in range(0, len(names), batch):
        chunk = names[i:i + batch]
        for n, v in zip(chunk, semantic.embed(chunk)):
            vecs[n] = v

    assigned = 0
    for p in prices:
        v = vecs.get(p.raw_name)
        if v is None:
            continue
        sims = cat_vecs @ v                 # косинус (векторы нормированы)
        j = int(sims.argmax())
        score = float(sims[j])
        if score >= thr:
            svc = catalog[j]
            p.service_id = svc.id
            p.match_confidence = round(score, 3)
            if getattr(svc, "tarificator_code", "") and not p.tarificator_code:
                p.tarificator_code = svc.tarificator_code
            assigned += 1
    db.commit()
    return {"available": True, "assigned": assigned, "checked": len(prices), "unique_names": len(names)}
