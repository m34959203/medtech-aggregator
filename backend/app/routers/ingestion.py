"""Роуты приёма данных: загрузка файла (① push) и автосбор web/api (② pull)."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Clinic, IngestionRun, Source
from ..schemas import IngestionResult, IngestionRunOut
from ..ingestion import api_connector, web_scraper
from ..ingestion.file_parser import detect_and_parse
from ..ingestion.service import ingest_items

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


def _require_clinic(db: Session, clinic_id: int) -> Clinic:
    clinic = db.get(Clinic, clinic_id)
    if not clinic:
        raise HTTPException(404, "Клиника не найдена")
    return clinic


@router.post("/upload", response_model=IngestionResult)
async def upload_pricelist(
    clinic_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """① Push: клиника загружает прайс (xlsx/csv/pdf)."""
    _require_clinic(db, clinic_id)
    content = await file.read()
    fmt, items = detect_and_parse(file.filename or "", content)
    if not items:
        raise HTTPException(422, f"Не удалось извлечь позиции из файла ({fmt}). Проверьте формат.")
    return ingest_items(
        db, clinic_id=clinic_id, channel="push", source_type="upload",
        items=items, fmt=fmt,
    )


class ScrapeIn(BaseModel):
    clinic_id: int
    url: str
    dynamic: bool = False


@router.post("/scrape", response_model=IngestionResult)
def scrape_site(payload: ScrapeIn, db: Session = Depends(get_db)):
    """② Pull: снять прайс с сайта клиники."""
    _require_clinic(db, payload.clinic_id)
    src = _ensure_source(db, payload.clinic_id, "web_scrape", payload.url)
    try:
        items = (web_scraper.scrape_dynamic if payload.dynamic else web_scraper.scrape_url)(payload.url)
    except Exception as e:
        raise HTTPException(502, f"Ошибка автосбора: {e}")
    if not items:
        raise HTTPException(422, "С сайта не извлечено ни одной позиции прайса.")
    return ingest_items(
        db, clinic_id=payload.clinic_id, channel="pull", source_type="web_scrape",
        items=items, fmt="html", source_id=src.id,
    )


class ScrapeHtmlIn(BaseModel):
    clinic_id: int
    html: str


@router.post("/scrape-html", response_model=IngestionResult)
def scrape_html(payload: ScrapeHtmlIn, db: Session = Depends(get_db)):
    """② Pull (демо без сети): распарсить переданный HTML прайса."""
    _require_clinic(db, payload.clinic_id)
    items = web_scraper.scrape_html(payload.html)
    if not items:
        raise HTTPException(422, "В HTML не найдено позиций прайса.")
    return ingest_items(
        db, clinic_id=payload.clinic_id, channel="pull", source_type="web_scrape",
        items=items, fmt="html",
    )


class ApiIn(BaseModel):
    clinic_id: int
    endpoint: str


@router.post("/api", response_model=IngestionResult)
def ingest_from_api(payload: ApiIn, db: Session = Depends(get_db)):
    """② Pull: тянем прайс из REST/JSON API клиники или агрегатора."""
    _require_clinic(db, payload.clinic_id)
    src = _ensure_source(db, payload.clinic_id, "api", payload.endpoint)
    try:
        items = api_connector.fetch_api(payload.endpoint)
    except Exception as e:
        raise HTTPException(502, f"Ошибка API-коннектора: {e}")
    if not items:
        raise HTTPException(422, "API не вернул распознаваемых позиций.")
    return ingest_items(
        db, clinic_id=payload.clinic_id, channel="pull", source_type="api",
        items=items, fmt="json", source_id=src.id,
    )


def _ensure_source(db: Session, clinic_id: int, type_: str, url: str) -> Source:
    src = (
        db.query(Source)
        .filter(Source.clinic_id == clinic_id, Source.type == type_, Source.url_or_endpoint == url)
        .first()
    )
    if not src:
        src = Source(clinic_id=clinic_id, type=type_, url_or_endpoint=url, enabled=True)
        db.add(src)
        db.flush()
    return src


@router.post("/run-scheduled")
def run_scheduled():
    """Запустить автосбор по всем включённым pull-источникам (web_scrape/api)."""
    from ..scheduler import run_all_sources

    return {"report": run_all_sources()}


@router.get("/runs", response_model=list[IngestionRunOut])
def list_runs(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(IngestionRun).order_by(IngestionRun.created_at.desc()).limit(limit).all()
