"""Семантическая нормализация (эмбеддинги + pgvector) — «ров» поверх онтологии.

Понимает СМЫСЛ названия, а не только буквы: «кровь на сахар» → «Глюкоза»,
«УЗ-исследование почек» → «УЗИ почек» — там, где fuzzy бессилен.

Хранилище двойное:
- Postgres + pgvector → эмбеддинги в `service_embeddings`, поиск `<=>` (cosine).
- иначе (SQLite/dev) → in-process numpy-матрица.

Грациозная деградация: если `fastembed`/модель недоступны или `semantic_enabled=False`,
`available()` вернёт False, и нормализатор остаётся на fuzzy+LLM. Модель ленивая и
кэшируется (в Docker-образе — предзагружается).
"""
from __future__ import annotations

import threading

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ServiceCatalog

_DIM = 384
_lock = threading.Lock()
_model = None
# in-process индекс: {"sig": (count,max_id), "ids": [...], "mat": np.ndarray(n,dim)}
_mem: dict | None = None


def available() -> bool:
    if not settings.semantic_enabled:
        return False
    try:
        import fastembed  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from fastembed import TextEmbedding
            _model = TextEmbedding(model_name=settings.semantic_model)
    return _model


def embed(texts: list[str]):
    import numpy as np
    vecs = list(_get_model().embed(list(texts)))
    out = []
    for v in vecs:
        a = np.asarray(v, dtype="float32")
        n = np.linalg.norm(a)
        out.append(a / n if n else a)  # нормализуем → косинус = скалярное произведение
    return out


def _is_pg(db: Session) -> bool:
    return db.bind is not None and db.bind.dialect.name == "postgresql"


def _vec_literal(v) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v.tolist()) + "]"


# --- Индексация ---
def reindex(db: Session) -> int:
    """Пересчитать эмбеддинги всего каталога. → число услуг."""
    services = db.query(ServiceCatalog).order_by(ServiceCatalog.id).all()
    if not services:
        return 0
    vecs = embed([s.canonical_name for s in services])
    if _is_pg(db):
        for s, v in zip(services, vecs):
            db.execute(
                text(
                    "INSERT INTO service_embeddings (service_id, embedding) "
                    "VALUES (:sid, (:emb)::vector) "
                    "ON CONFLICT (service_id) DO UPDATE SET embedding = (:emb)::vector"
                ),
                {"sid": s.id, "emb": _vec_literal(v)},
            )
        db.commit()
    else:
        import numpy as np
        global _mem
        _mem = {
            "sig": _signature(db),
            "ids": [s.id for s in services],
            "mat": np.vstack(vecs),
        }
    return len(services)


def _signature(db: Session) -> tuple[int, int]:
    cnt = db.query(ServiceCatalog).count()
    mx = db.query(ServiceCatalog.id).order_by(ServiceCatalog.id.desc()).first()
    return (cnt, mx[0] if mx else 0)


def _ensure_mem(db: Session) -> None:
    if _mem is None or _mem.get("sig") != _signature(db):
        reindex(db)


# --- Поиск ---
def match(db: Session, query: str) -> tuple[int | None, float]:
    """Семантически ближайшая услуга к запросу. → (service_id|None, score 0..1)."""
    if not available() or not (query or "").strip():
        return None, 0.0
    qv = embed([query])[0]
    if _is_pg(db):
        row = db.execute(
            text(
                "SELECT service_id, 1 - (embedding <=> (:q)::vector) AS score "
                "FROM service_embeddings ORDER BY embedding <=> (:q)::vector LIMIT 1"
            ),
            {"q": _vec_literal(qv)},
        ).first()
        if not row:
            return None, 0.0
        return int(row[0]), float(row[1])
    # in-process
    import numpy as np
    _ensure_mem(db)
    if not _mem or not _mem["ids"]:
        return None, 0.0
    sims = _mem["mat"] @ qv  # косинус (всё нормализовано)
    i = int(np.argmax(sims))
    return _mem["ids"][i], float(sims[i])


def reset_memory() -> None:
    """Сброс in-process кэша (для тестов)."""
    global _mem
    _mem = None
