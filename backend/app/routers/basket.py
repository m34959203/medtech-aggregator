"""Корзина-рецепт (Спринт-3): пациент скидывает направление врача (текст/фото/скан),
система распознаёт нужные анализы и предлагает выгодный вариант где их сдать.

Composв всё ядро: OCR (фото рецепта) → нормализатор (распознать услуги) →
агрегатор (дешевле) → город (ближе). Две стратегии в ответе:
- mixed — минимум по каждой услуге (можно по разным клиникам);
- single — одна клиника, покрывающая максимум услуг (одна поездка).
"""
from __future__ import annotations

import io
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..ratelimit import rate_limit
from ..ingestion import ocr
from ..ingestion.file_parser import _IMAGE_EXT
from ..ingestion.normalizer import Normalizer, _clean
from .aggregator import _build_comparison

router = APIRouter(prefix="/api/basket", tags=["basket"])

_BULLET = re.compile(r"^\s*(?:\d+[.):]\s*|[-•·*]\s*)")
# Пользовательский рецепт строже ингеста: ложное «узнавание» мусора («HemoglobinX»,
# «Test 123») вводит пациента в заблуждение. fuzzy ≥0.72, семантика ≥0.85
# (мед-косинусы 0.72–0.85 ненадёжны — модель путает по смыслу). Ниже — «не распознано».
_MATCH_FLOOR = 0.72
_SEM_FLOOR = 0.85


def extract_service_names(text: str) -> list[str]:
    """Достаёт строки-кандидаты услуг из свободного текста направления."""
    names: list[str] = []
    for raw in re.split(r"[\n;]+", text or ""):
        line = _BULLET.sub("", raw).strip(" .:-—\t")
        line = re.sub(r"\s{2,}", " ", line)
        if len(line) < 3 or not re.search(r"[A-Za-zА-Яа-яЁё]{3,}", line):
            continue
        names.append(line)
    return names[:30]


def _extract_text_any(filename: str, content: bytes) -> str:
    """Текст из направления: картинка/скан → OCR, PDF → слой или OCR, иначе декод."""
    fn = (filename or "").lower()
    is_img = fn.endswith(_IMAGE_EXT) or content[:3] == b"\xff\xd8\xff" or content[:8] == b"\x89PNG\r\n\x1a\n"
    if is_img:
        return ocr.image_to_text(content) if ocr.ocr_available() else ""
    if fn.endswith(".pdf") or content[:4] == b"%PDF":
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            txt = "\n".join(p.extract_text() or "" for p in pdf.pages)
        if txt.strip():
            return txt
        return ocr.pdf_to_text_ocr(content) if ocr.ocr_available() else ""
    return content.decode("utf-8", errors="ignore")


def _recommend(db: Session, names: list[str], city: str | None) -> dict:
    norm = Normalizer(db)
    items: list[dict] = []
    unrecognized: list[str] = []
    seen: dict[int, str] = {}  # service_id → исходная строка (дедуп услуг)
    canon: dict[int, str] = {}
    clinic_cover: dict[int, dict] = {}

    def _add_service(svc, nm: str, conf: float):
        if svc.id in seen:
            return
        seen[svc.id] = nm
        canon[svc.id] = svc.canonical_name
        cmp = _build_comparison(db, svc, city, None, "price_asc")
        cheapest = cmp.offers[0] if cmp.offers else None
        items.append({
            "input": nm, "service_id": svc.id, "canonical": svc.canonical_name,
            "confidence": round(conf, 2), "offers_count": cmp.offers_count,
            "cheapest": None if not cheapest else {
                "clinic_id": cheapest.clinic_id, "clinic_name": cheapest.clinic_name,
                "city": cheapest.city, "address": cheapest.address,
                "phone": cheapest.phone, "price": cheapest.price,
            },
        })
        for o in cmp.offers:
            c = clinic_cover.setdefault(o.clinic_id, {
                "clinic_id": o.clinic_id, "clinic_name": o.clinic_name,
                "city": o.city, "phone": o.phone, "address": o.address, "prices": {},
            })
            if svc.id not in c["prices"] or o.price < c["prices"][svc.id]:
                c["prices"][svc.id] = o.price

    # Каждую строку — через полный разбор: gate шума (ФИО/дата/заголовок не услуги),
    # декомпозиция панелей (липидограмма→4), строгий матч с порогом отказа.
    for nm in names:
        res = norm.analyze(nm, floor=_MATCH_FLOOR, sem_floor=_SEM_FLOOR)
        if res["kind"] == "noise":
            continue  # шум направления — не услуга
        for it in res["items"]:
            # порог рецепта: ниже — честное «не распознано», без принудительной привязки
            if it["status"] != "matched" or float(it.get("confidence") or 0.0) < _MATCH_FLOOR:
                unrecognized.append(nm if it["canonical"] in ("—", None) else it["canonical"])
                continue
            svc = norm.index.get(_clean(it["canonical"]))
            if not svc:  # распознано (панель/новое), но в справочнике/ценах нет
                unrecognized.append(it["canonical"])
                continue
            _add_service(svc, nm, float(it.get("confidence") or 1.0))

    target = [it["service_id"] for it in items if it["cheapest"]]
    total_mixed = round(sum(it["cheapest"]["price"] for it in items if it["cheapest"]), 2)

    # Лучшая одна клиника: покрывает максимум услуг, при равенстве — дешевле.
    best = None
    for c in clinic_cover.values():
        covered = [sid for sid in target if sid in c["prices"]]
        if not covered:
            continue
        total = round(sum(c["prices"][sid] for sid in covered), 2)
        cand = {
            "clinic_id": c["clinic_id"], "clinic_name": c["clinic_name"], "city": c["city"],
            "phone": c["phone"], "address": c["address"],
            "covered": len(covered), "total": total,
            "missing": [canon[sid] for sid in target if sid not in c["prices"]],
        }
        if best is None or (cand["covered"], -cand["total"]) > (best["covered"], -best["total"]):
            best = cand

    # дедуп unrecognized с сохранением порядка
    uniq_unrec = list(dict.fromkeys(unrecognized))
    return {
        "recognized": items, "unrecognized": uniq_unrec,
        "services_found": len(items), "total_cheapest_mixed": total_mixed,
        "best_single_clinic": best, "city": city or None,
    }


class BasketIn(BaseModel):
    text: str | None = None
    names: list[str] | None = None
    city: str | None = None


@router.post("/recommend", dependencies=[Depends(rate_limit("basket", 15))])
def recommend(payload: BasketIn, db: Session = Depends(get_db)):
    """Текст направления (или список услуг) → рекомендация где сдать выгодно."""
    names = payload.names or extract_service_names(payload.text or "")
    if not names:
        raise HTTPException(422, "Не удалось выделить услуги из текста направления.")
    return _recommend(db, names, payload.city)


@router.post("/recommend-file", dependencies=[Depends(rate_limit("basket_file", 10))])
async def recommend_file(
    file: UploadFile = File(...),
    city: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Фото/скан/PDF направления → OCR → рекомендация."""
    content = await file.read()
    text = _extract_text_any(file.filename or "", content)
    names = extract_service_names(text)
    if not names:
        raise HTTPException(
            422,
            "Не удалось распознать услуги. Сфотографируйте направление чётче или введите список вручную.",
        )
    return _recommend(db, names, city)
