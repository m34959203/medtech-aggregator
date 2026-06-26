"""Семантический поиск услуг (pgvector/in-process) — управление и эндпоинт.

reindex — пересчёт эмбеддингов каталога (админ). search — публичный семантический
поиск услуги по смыслу (для отладки/демо и как API).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..ingestion import semantic
from ..models import ServiceCatalog

router = APIRouter(prefix="/api/semantic", tags=["semantic"])


@router.post("/reindex", dependencies=[Depends(require_admin)])
def reindex(db: Session = Depends(get_db)):
    if not semantic.available():
        raise HTTPException(503, "Семантика недоступна (нет fastembed/модели или отключена).")
    n = semantic.reindex(db)
    return {"ok": True, "indexed": n, "backend": "pgvector" if semantic._is_pg(db) else "in-process"}


@router.get("/match")
def semantic_match(q: str, db: Session = Depends(get_db)):
    """Ближайшая по смыслу услуга к запросу (semantic). Для демо/отладки."""
    if not semantic.available():
        raise HTTPException(503, "Семантика недоступна.")
    sid, score = semantic.match(db, q)
    if not sid:
        return {"query": q, "match": None, "score": 0.0}
    svc = db.get(ServiceCatalog, sid)
    return {"query": q, "match": svc.canonical_name if svc else None,
            "service_id": sid, "score": round(score, 3)}
