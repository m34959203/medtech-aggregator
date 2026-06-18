"""Экспорт нормализованного каталога — осязаемый артефакт Кейса 1.

Кейс 1 («автоматическая обработка архива прайсов») должен давать на выходе не
только витрину, но и единый структурированный каталог-файл. Отдаём весь свод
prices↔service_catalog↔clinics одним xlsx или csv.
"""
from __future__ import annotations

import io
from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Clinic, Price, ServiceCatalog

router = APIRouter(prefix="/api/export", tags=["export"])

COLUMNS = [
    "Услуга", "Категория", "Клиника", "Город", "Район", "Адрес", "Телефон",
    "Цена", "Валюта", "Источник", "Уверенность,%", "Исходное название", "Актуально с",
]

_SOURCE_RU = {"upload": "загрузка клиники", "api": "API", "web_scrape": "веб-сбор"}


def _catalog_rows(db: Session) -> list[dict]:
    q = (
        db.query(Price, ServiceCatalog, Clinic)
        .join(ServiceCatalog, Price.service_id == ServiceCatalog.id)
        .join(Clinic, Price.clinic_id == Clinic.id)
        .order_by(ServiceCatalog.category, ServiceCatalog.canonical_name, Price.price)
    )
    rows = []
    for p, s, c in q.all():
        rows.append({
            "Услуга": s.canonical_name,
            "Категория": s.category,
            "Клиника": c.name,
            "Город": c.city,
            "Район": c.district or "",
            "Адрес": c.address or "",
            "Телефон": c.phone or "",
            "Цена": p.price,
            "Валюта": p.currency,
            "Источник": _SOURCE_RU.get(p.source_type, p.source_type),
            "Уверенность,%": round((p.match_confidence or 0) * 100),
            "Исходное название": p.raw_name,
            "Актуально с": p.valid_from.isoformat() if p.valid_from else "",
        })
    return rows


@router.get("/catalog")
def export_catalog(format: str = "xlsx", db: Session = Depends(get_db)):
    """Единый каталог всех нормализованных позиций. format = xlsx | csv."""
    fmt = (format or "xlsx").lower()
    if fmt not in ("xlsx", "csv"):
        raise HTTPException(422, "format должен быть xlsx или csv")

    df = pd.DataFrame(_catalog_rows(db), columns=COLUMNS)
    stamp = date.today().isoformat()
    fname = f"medtsena-catalog-{stamp}.{fmt}"

    if fmt == "csv":
        # utf-8-sig — чтобы Excel на Windows не ломал кириллицу
        data = df.to_csv(index=False).encode("utf-8-sig")
        return StreamingResponse(
            io.BytesIO(data),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Каталог")
        ws = writer.sheets["Каталог"]
        # авто-ширина по содержимому (с разумным потолком)
        for i, col in enumerate(df.columns, start=1):
            width = max(len(str(col)), *(len(str(v)) for v in df[col].head(200))) if len(df) else len(str(col))
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(width + 2, 60)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
