"""Роуты приёма данных: загрузка файла (① push) и автосбор web/api (② pull)."""
from __future__ import annotations

import uuid

import io
import re
import zipfile

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..ratelimit import rate_limit
from ..db import get_db
from ..auth import require_admin
from ..models import Clinic, IngestionRun, Price, PriceReport, ServiceCatalog, Source
from ..schemas import IngestionResult, IngestionRunOut
from ..ingestion import api_connector, web_scraper
from ..ingestion.file_parser import detect_and_parse
from ..ingestion.normalizer import Normalizer
from ..ingestion.service import ingest_items
# MedArchive (Кейс 2): архивный пайплайн — резидент/нерезидент, §4.4-валидации,
# сохранение оригиналов. Отдельно от MedPrice-пути (ingest_items), чтобы Кейс 1
# не затрагивался.
from ..ingestion.archive_extractor import detect_and_parse as ae_detect_and_parse
from ..ingestion.archive_service import ingest_archive
from ..ingestion.storage import read_original
from ..archive_ingest import _effective_date, _partner_name

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


def _require_clinic(db: Session, clinic_id: uuid.UUID) -> Clinic:
    clinic = db.get(Clinic, clinic_id)
    if not clinic:
        raise HTTPException(404, "Клиника не найдена")
    return clinic


@router.post("/upload", response_model=IngestionResult, dependencies=[Depends(require_admin)])
async def upload_pricelist(
    clinic_id: uuid.UUID = Form(...),
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


def _resolve_clinic_id(db: Session, filename: str, default: uuid.UUID | None) -> uuid.UUID | None:
    """Клиника для файла из архива: префикс «<uuid>_имя.ext», иначе общий clinic_id.
    §2.2: id клиник — uuid, поэтому префикс — uuid (36 символов hex+дефисы)."""
    m = re.match(r"^\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                 r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})[ _\-]", filename)
    if m:
        try:
            cid = uuid.UUID(m.group(1))
        except ValueError:
            cid = None
        if cid and db.get(Clinic, cid):
            return cid
    return default if (default and db.get(Clinic, default)) else None


@router.post("/upload-batch", dependencies=[Depends(require_admin)])
async def upload_batch(
    clinic_id: uuid.UUID | None = Form(None),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """① Push (пакетно): архив прайсов клиник-партнёров → один отчёт по всем файлам.

    Принимает несколько файлов и/или .zip. Клиника для каждого файла берётся из
    префикса имени «<clinic_id>_прайс.xlsx», иначе из общего поля clinic_id.
    Прямой ответ на формулировку Кейса 1 — «обработка архива прайсов».
    """
    # Собираем (filename, bytes), разворачивая zip-архивы.
    entries: list[tuple[str, bytes]] = []
    for up in files:
        raw = await up.read()
        name = up.filename or "file"
        if name.lower().endswith(".zip"):
            try:
                zf = zipfile.ZipFile(io.BytesIO(raw))
            except zipfile.BadZipFile:
                entries.append((name, raw))
                continue
            for zi in zf.infolist():
                base = zi.filename.split("/")[-1]
                if zi.is_dir() or not base or base.startswith(".") or "__MACOSX" in zi.filename:
                    continue
                entries.append((base, zf.read(zi)))
        else:
            entries.append((name, raw))

    if not entries:
        raise HTTPException(422, "Архив пуст — не найдено файлов прайсов.")

    results: list[dict] = []
    tot_items = tot_matched = tot_review = ok = 0
    for fname, content in entries[:200]:
        entry: dict = {"file": fname}
        cid = _resolve_clinic_id(db, fname, clinic_id)
        if cid is None:
            entry.update(status="error", error="Клиника не определена: задайте clinic_id или префикс «<id>_».")
            results.append(entry)
            continue
        try:
            fmt, items = detect_and_parse(fname, content)
        except Exception as e:  # noqa: BLE001 — отчёт по файлу, не валим весь архив
            entry.update(status="error", error=f"Парсинг не удался ({type(e).__name__}).")
            results.append(entry)
            continue
        if not items:
            entry.update(status="empty", clinic_id=cid, format=fmt, items=0)
            results.append(entry)
            continue
        res = ingest_items(
            db, clinic_id=cid, channel="push", source_type="upload", items=items, fmt=fmt,
        )
        entry.update(
            status="ok", clinic_id=cid, format=fmt, items=res.items_found,
            matched=res.matched, needs_review=res.needs_review, run_id=res.run_id,
        )
        tot_items += res.items_found
        tot_matched += res.matched
        tot_review += res.needs_review
        ok += 1
        results.append(entry)

    return {
        "files": results,
        "totals": {
            "files": len(entries), "ok": ok, "items": tot_items,
            "matched": tot_matched, "needs_review": tot_review,
        },
    }


_ARCHIVE_MAX_FILES = 1000  # верхняя граница на один приём (защита от мусора)


def _unpack_entries(files_bytes: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Разворачивает .zip в (имя, байты); обычные файлы пропускает как есть."""
    out: list[tuple[str, bytes]] = []
    for name, raw in files_bytes:
        if name.lower().endswith(".zip"):
            try:
                zf = zipfile.ZipFile(io.BytesIO(raw))
            except zipfile.BadZipFile:
                out.append((name, raw))
                continue
            for zi in zf.infolist():
                base = zi.filename.split("/")[-1]
                if zi.is_dir() or not base or base.startswith(".") or "__MACOSX" in zi.filename:
                    continue
                out.append((base, zf.read(zi)))
        else:
            out.append((name, raw))
    return out


@router.post("/archive", dependencies=[Depends(require_admin)])
async def ingest_archive_upload(
    clinic_id: uuid.UUID | None = Form(None),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Кейс 2 (MedArchive): приём архива прайсов партнёров полным пайплайном.

    Отличие от `/upload-batch` (Кейс 1, single-price): резидент/нерезидент раздельно,
    §4.4-валидации (нерезидент≥резидент, аномалия >50%), code-first нормализация и
    **сохранение оригиналов** (§2.1/§5) для повторной обработки. Партнёр берётся из
    префикса «<uuid>_», общего поля `clinic_id`, либо из имени файла (авто-создание).
    """
    raw_files: list[tuple[str, bytes]] = [(up.filename or "file", await up.read()) for up in files]
    entries = _unpack_entries(raw_files)
    if not entries:
        raise HTTPException(422, "Архив пуст — не найдено файлов прайсов.")
    truncated = len(entries) > _ARCHIVE_MAX_FILES
    entries = entries[:_ARCHIVE_MAX_FILES]

    nz = Normalizer(db)  # общий нормализатор на весь архив (общий рост индекса)
    results: list[dict] = []
    tot_items = tot_matched = tot_review = tot_anom = ok = stored = 0
    for fname, content in entries:
        entry: dict = {"file": fname}
        # партнёр: префикс/форма → иначе из имени файла (§2.1 «имя содержит клинику»)
        cid = _resolve_clinic_id(db, fname, clinic_id)
        if cid is None:
            partner = db.query(Clinic).filter(Clinic.name == _partner_name(fname)).first()
            if partner is None:
                partner = Clinic(name=_partner_name(fname), city="", address="")
                db.add(partner)
                db.flush()
            cid = partner.id
        try:
            fmt, items = ae_detect_and_parse(fname, content)
        except Exception as e:  # noqa: BLE001 — отчёт по файлу, не валим архив
            entry.update(status="error", parse_status="error", error=f"Парсинг не удался ({type(e).__name__}).")
            results.append(entry)
            continue
        if not items:
            entry.update(status="empty", parse_status="error", clinic_id=str(cid), format=fmt, items=0)
            results.append(entry)
            continue
        st = ingest_archive(
            db, clinic_id=cid, file_name=fname, fmt=fmt, items=items,
            valid_from=_effective_date(fname), normalizer=nz, content=content,
        )
        entry.update(
            status="ok", clinic_id=str(cid), format=fmt, run_id=st["run_id"],
            items=st["items"], services=st["services"], matched=st["matched"],
            needs_review=st["needs_review"], skipped=st["skipped"],
            anomalies=st["anomalies"], parse_status=st["parse_status"], stored=st["stored"],
        )
        tot_items += st["items"]
        tot_matched += st["matched"]
        tot_review += st["needs_review"]
        tot_anom += st["anomalies"]
        stored += 1 if st["stored"] else 0
        ok += 1
        results.append(entry)

    return {
        "files": results,
        "totals": {
            "files": len(entries), "ok": ok, "items": tot_items,
            "matched": tot_matched, "needs_review": tot_review,
            "anomalies": tot_anom, "stored": stored,
        },
        "truncated": truncated,
    }


@router.post("/archive/{run_id}/reprocess", dependencies=[Depends(require_admin)])
def reprocess_archive_document(run_id: int, db: Session = Depends(get_db)):
    """§2.1/§4.1: повторная обработка документа из сохранённого ОРИГИНАЛА.

    Перечитывает исходный файл (`IngestionRun.file_path`) и прогоняет архивный
    пайплайн заново (новый прогон, текущий справочник). 404 если оригинал не сохранён.
    """
    run = db.get(IngestionRun, run_id)
    if run is None:
        raise HTTPException(404, "Прогон не найден.")
    if not run.file_path:
        raise HTTPException(404, "Оригинал документа не сохранён — повторная обработка недоступна.")
    try:
        content = read_original(run.file_path)
    except OSError:
        raise HTTPException(410, "Файл оригинала недоступен на диске.")
    fmt, items = ae_detect_and_parse(run.file_name, content)
    st = ingest_archive(
        db, clinic_id=run.clinic_id, file_name=run.file_name, fmt=fmt, items=items,
        valid_from=run.effective_date, normalizer=Normalizer(db), content=content,
    )
    return st


@router.get("/stats", dependencies=[Depends(require_admin)])
def ingest_stats(db: Session = Depends(get_db)):
    """Сводка для админ-дашборда: объём каталога и качество приёма."""
    threshold = settings.match_confidence_threshold
    by_source = dict(
        db.query(Price.source_type, func.count(Price.id)).group_by(Price.source_type).all()
    )
    return {
        "clinics": db.query(func.count(Clinic.id)).scalar() or 0,
        # distinct city без пустых: иначе '' анонимных архив-клиник считался «городом» (+1).
        "cities": db.query(func.count(func.distinct(Clinic.city)))
        .filter(func.coalesce(Clinic.city, "") != "").scalar() or 0,
        "services": db.query(func.count(ServiceCatalog.id)).scalar() or 0,
        "prices": db.query(func.count(Price.id)).scalar() or 0,
        "runs": db.query(func.count(IngestionRun.id)).scalar() or 0,
        "needs_review": db.query(func.count(Price.id))
        .filter(Price.match_confidence < threshold).scalar() or 0,
        # Мониторинг скраперов: прогоны, отдавшие 0 позиций или упавшие — источник
        # тихо ломается при редизайне сайта, иначе данные деградируют незаметно.
        "empty_runs": db.query(func.count(IngestionRun.id))
        .filter(IngestionRun.items_found == 0).scalar() or 0,
        "failed_runs": db.query(func.count(IngestionRun.id))
        .filter(IngestionRun.status == "error").scalar() or 0,
        "reports_new": db.query(func.count(PriceReport.id))
        .filter(PriceReport.status == "new").scalar() or 0,
        "by_source": by_source,
    }


class ScrapeIn(BaseModel):
    clinic_id: uuid.UUID
    url: str
    dynamic: bool = False


@router.post("/scrape", response_model=IngestionResult, dependencies=[Depends(require_admin)])
def scrape_site(payload: ScrapeIn, db: Session = Depends(get_db)):
    """② Pull: снять прайс с сайта клиники."""
    _require_clinic(db, payload.clinic_id)
    src = _ensure_source(db, payload.clinic_id, "web_scrape", payload.url)
    raw = ""
    try:
        if payload.dynamic:
            items = web_scraper.scrape_dynamic(payload.url)
        else:
            raw, items = web_scraper.scrape_url_raw(payload.url)
    except web_scraper.RobotsDisallowed as e:
        raise HTTPException(403, f"robots.txt сайта запрещает автосбор этого URL: {e.url}")
    except Exception as e:
        raise HTTPException(502, f"Ошибка автосбора: {e}")
    if not items:
        raise HTTPException(422, "С сайта не извлечено ни одной позиции прайса.")
    return ingest_items(
        db, clinic_id=payload.clinic_id, channel="pull", source_type="web_scrape",
        items=items, fmt="html", source_id=src.id, raw_content=raw,
    )


class ScrapeHtmlIn(BaseModel):
    clinic_id: uuid.UUID
    html: str


@router.post("/scrape-html", response_model=IngestionResult, dependencies=[Depends(require_admin)])
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
    clinic_id: uuid.UUID
    endpoint: str


@router.post("/api", response_model=IngestionResult, dependencies=[Depends(require_admin)])
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


def _ensure_source(db: Session, clinic_id: uuid.UUID, type_: str, url: str) -> Source:
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


class PreviewIn(BaseModel):
    names: list[str]


@router.post("/preview", dependencies=[Depends(require_admin), Depends(rate_limit("preview", 20))])
def preview_normalization(payload: PreviewIn, db: Session = Depends(get_db)):
    """Сухой прогон умной нормализации БЕЗ записи в БД (admin-инструмент).

    Полный разбор строк направления: входной фильтр шума (gate) → декомпозиция
    панелей → строгий матч с порогом отказа. Ничего не мутирует. Возвращает на
    каждую строку {raw, kind, reason, items[]} (см. Normalizer.analyze)."""
    names = [n.strip() for n in payload.names if n and n.strip()][:30]
    if not names:
        raise HTTPException(422, "Передайте хотя бы одну строку.")
    norm = Normalizer(db)  # snapshot справочника; analyze() ничего не мутирует
    return {"results": [norm.analyze(n) for n in names]}


@router.post("/preview-file", dependencies=[Depends(require_admin), Depends(rate_limit("preview_file", 10))])
async def preview_normalization_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Фото/скан/PDF направления → OCR → разбор строк (gate + панели + матч).

    Распознаёт услуги/анализы с фотографии рецепта. Тот же контракт, что /preview
    ({results:[{raw,kind,reason,items[]}]}); ничего не мутирует."""
    from .basket import _extract_text_any, extract_service_names

    content = await file.read()
    text = _extract_text_any(file.filename or "", content)
    lines = extract_service_names(text)
    if not lines:
        raise HTTPException(
            422, "Не удалось распознать текст. Сфотографируйте направление чётче "
                 "(хорошее освещение, без бликов) или введите строки вручную.",
        )
    norm = Normalizer(db)
    return {"results": [norm.analyze(n) for n in lines], "ocr_text": text[:4000]}


@router.post("/run-scheduled", dependencies=[Depends(require_admin)])
def run_scheduled(background: BackgroundTasks):
    """Запустить автосбор по всем включённым pull-источникам (web_scrape/api).

    Десятки источников сканируются минутами → синхронный ответ рвался по таймауту
    прокси (500). Запускаем В ФОНЕ (Starlette гонит sync-таск в threadpool) и сразу
    отвечаем; результат виден в журнале прогонов (дашборд авто-обновляется)."""
    from ..scheduler import run_all_sources

    background.add_task(run_all_sources)
    return {"status": "started"}


@router.get("/runs", response_model=list[IngestionRunOut], dependencies=[Depends(require_admin)])
def list_runs(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(IngestionRun).order_by(IngestionRun.created_at.desc()).limit(limit).all()


# --- §3.1: управление источниками автосбора (список сайтов для парсинга) ---
class SourceIn(BaseModel):
    clinic_id: uuid.UUID
    type: str = "web_scrape"  # web_scrape | api
    url: str
    schedule: str | None = None


class SourcePatch(BaseModel):
    enabled: bool | None = None
    url: str | None = None
    schedule: str | None = None


def _source_dict(db: Session, s: Source, counts: dict) -> dict:
    clinic = db.get(Clinic, s.clinic_id)
    return {
        "id": s.id,
        "clinic_id": str(s.clinic_id),
        "clinic_name": clinic.name if clinic else None,
        "type": s.type,
        "url_or_endpoint": s.url_or_endpoint,
        "schedule": s.schedule or "",
        "enabled": bool(s.enabled),
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "runs": int(counts.get(s.id, 0)),
    }


@router.get("/sources", dependencies=[Depends(require_admin)])
def list_sources(db: Session = Depends(get_db)):
    """Источники автосбора (web_scrape/api) — для управления списком сайтов."""
    counts = dict(
        db.query(IngestionRun.source_id, func.count(IngestionRun.id))
        .group_by(IngestionRun.source_id).all()
    )
    srcs = (
        db.query(Source)
        .filter(Source.type != "upload")  # upload — не автосбор
        .order_by(Source.enabled.desc(), Source.id)
        .all()
    )
    return [_source_dict(db, s, counts) for s in srcs]


@router.post("/sources", dependencies=[Depends(require_admin)])
def create_source(body: SourceIn, db: Session = Depends(get_db)):
    if body.type not in ("web_scrape", "api"):
        raise HTTPException(400, "type: web_scrape | api")
    if not body.url.strip():
        raise HTTPException(400, "url обязателен")
    if not db.get(Clinic, body.clinic_id):
        raise HTTPException(404, "Клиника не найдена")
    exists = (
        db.query(Source)
        .filter(Source.clinic_id == body.clinic_id, Source.type == body.type,
                Source.url_or_endpoint == body.url.strip())
        .first()
    )
    if exists:
        raise HTTPException(409, "Такой источник уже есть")
    src = Source(clinic_id=body.clinic_id, type=body.type,
                 url_or_endpoint=body.url.strip(), schedule=(body.schedule or ""), enabled=True)
    db.add(src)
    db.commit()
    db.refresh(src)
    return _source_dict(db, src, {})


@router.patch("/sources/{source_id}", dependencies=[Depends(require_admin)])
def patch_source(source_id: int, body: SourcePatch, db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if not src:
        raise HTTPException(404, "Источник не найден")
    if body.enabled is not None:
        src.enabled = body.enabled
    if body.url is not None:
        src.url_or_endpoint = body.url.strip()
    if body.schedule is not None:
        src.schedule = body.schedule
    db.commit()
    return _source_dict(db, src, {})


@router.delete("/sources/{source_id}", dependencies=[Depends(require_admin)])
def delete_source(source_id: int, db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if not src:
        raise HTTPException(404, "Источник не найден")
    # отвязываем прогоны (history сохраняем), затем удаляем источник
    db.query(IngestionRun).filter(IngestionRun.source_id == source_id).update(
        {IngestionRun.source_id: None}, synchronize_session=False)
    db.delete(src)
    db.commit()
    return {"ok": True, "deleted": source_id}


@router.get("/runs/{run_id}", dependencies=[Depends(require_admin)])
def run_detail(run_id: int, db: Session = Depends(get_db)):
    """Деталь прогона: метаданные + все позиции (raw → нормализованное, статус,
    цена резидент/нерезидент). Для страницы /admin/runs/{id} и панели завершения."""
    run = db.get(IngestionRun, run_id)
    if not run:
        raise HTTPException(404, "Прогон не найден")
    threshold = settings.match_confidence_threshold
    rows = (
        db.query(Price, ServiceCatalog)
        .outerjoin(ServiceCatalog, Price.service_id == ServiceCatalog.id)
        .filter(Price.run_id == run_id)
        .order_by(Price.match_confidence)
        .all()
    )
    clinic = None
    if rows:
        clinic = db.get(Clinic, rows[0][0].clinic_id)
    positions = [
        {
            "price_id": p.id,
            "raw_name": p.raw_name,
            "canonical_name": s.canonical_name if s else None,
            "service_id": str(s.id) if s else None,
            "match_confidence": round(p.match_confidence, 2),
            "status": "needs_review" if p.match_confidence < threshold else "matched",
            "is_anomaly": bool(p.is_anomaly),
            "price": float(p.price) if p.price is not None else None,
            "price_resident": float(p.price_resident) if p.price_resident is not None else None,
            "price_nonresident": float(p.price_nonresident) if p.price_nonresident is not None else None,
            "currency": p.currency,
        }
        for p, s in rows
    ]
    matched = sum(1 for x in positions if x["status"] == "matched")
    anomalies = sum(1 for x in positions if x["is_anomaly"])
    return {
        "run_id": run.id,
        "channel": run.channel,
        "format": run.format,
        "status": run.status,
        "message": run.message,
        "items_found": run.items_found,
        "created_at": run.created_at.isoformat(),
        "clinic_id": str(clinic.id) if clinic else None,
        "clinic_name": clinic.name if clinic else None,
        "has_original": bool(getattr(run, "file_path", None)),
        "counts": {
            "positions": len(positions),
            "matched": matched,
            "needs_review": len(positions) - matched,
            "anomalies": anomalies,
            "threshold": threshold,
        },
        "positions": positions,
    }


@router.post("/runs/{run_id}/rollback", dependencies=[Depends(require_admin)])
def rollback_run(run_id: int, db: Session = Depends(get_db)):
    """Откат прогона: удалить цены, добавленные этим прогоном (целостность каталога
    при дублях/ошибочной загрузке). Прогон помечается `rolled_back` для аудита.
    Деструктивно — фронт спрашивает подтверждение."""
    run = db.get(IngestionRun, run_id)
    if not run:
        raise HTTPException(404, "Прогон не найден")
    prices = db.query(Price).filter(Price.run_id == run_id).all()
    deleted = len(prices)
    for p in prices:
        db.delete(p)
    run.status = "rolled_back"
    run.message = f"[откат] {run.message}"
    db.commit()
    return {"run_id": run_id, "deleted_prices": deleted, "status": "rolled_back"}
