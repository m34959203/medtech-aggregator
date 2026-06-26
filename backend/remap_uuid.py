"""Перенос данных INT-схемы → UUID-схемы (cutover §2.2: clinic_id/service_id → uuid).

Читает строки из СТАРОЙ БД (int PK clinics/service_catalog), генерирует uuid для
клиник и услуг, переписывает все FK (prices/sources/leads/price_reports/price_history)
и вставляет в НОВУЮ БД (uuid-схема уже создана: create_all/migrate против неё).
service_embeddings НЕ переносим — пересоберётся reindex'ом на старте бэкенда.

  python remap_uuid.py <src_int_url> <dst_uuid_url>
"""
from __future__ import annotations

import sys
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    Clinic, IngestionRun, Lead, Price, PriceHistory, PriceReport, ServiceCatalog, Source,
)


def _rows(ss, model) -> list[dict]:
    out = []
    for r in ss.execute(select(model)).scalars().all():
        out.append({c.name: getattr(r, c.name) for c in model.__table__.columns})
    return out


def remap(src_url: str, dst_url: str) -> dict[str, int]:
    src = create_engine(src_url, future=True)
    dst = create_engine(dst_url, future=True)
    counts: dict[str, int] = {}
    with Session(src) as ss:
        clinics = _rows(ss, Clinic)
        services = _rows(ss, ServiceCatalog)
        sources = _rows(ss, Source)
        runs = _rows(ss, IngestionRun)
        leads = _rows(ss, Lead)
        reports = _rows(ss, PriceReport)
        prices = _rows(ss, Price)
        history = _rows(ss, PriceHistory)

    cmap = {c["id"]: uuid.uuid4() for c in clinics}   # int → uuid (клиники)
    smap = {s["id"]: uuid.uuid4() for s in services}  # int → uuid (услуги)

    def cu(v):  # clinic id remap (nullable)
        return cmap.get(v) if v is not None else None

    def su(v):  # service id remap (nullable)
        return smap.get(v) if v is not None else None

    for c in clinics:
        c["id"] = cmap[c["id"]]
    for s in services:
        s["id"] = smap[s["id"]]
    for s in sources:
        s["clinic_id"] = cu(s["clinic_id"])
    for l in leads:
        l["clinic_id"] = cu(l["clinic_id"])
    for r in reports:
        r["clinic_id"] = cu(r["clinic_id"])
    for p in prices:
        p["clinic_id"] = cu(p["clinic_id"]); p["service_id"] = su(p["service_id"])
        p.setdefault("source_url", "")
    for h in history:
        h["clinic_id"] = cu(h["clinic_id"]); h["service_id"] = su(h["service_id"])

    plan = [(Clinic, clinics), (ServiceCatalog, services), (Source, sources),
            (IngestionRun, runs), (Lead, leads), (PriceReport, reports),
            (Price, prices), (PriceHistory, history)]
    with Session(dst) as ds:
        for model, data in plan:
            for row in data:
                # отбрасываем колонки, которых нет в новой схеме (на всякий случай)
                cols = {c.name for c in model.__table__.columns}
                ds.execute(model.__table__.insert().values(**{k: v for k, v in row.items() if k in cols}))
            ds.commit()
            counts[model.__tablename__] = len(data)
            print(f"  {model.__tablename__}: {len(data)}")
    return counts


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python remap_uuid.py <src_int_url> <dst_uuid_url>"); sys.exit(1)
    print(f"[remap] {sys.argv[1]} → {sys.argv[2]}")
    total = remap(sys.argv[1], sys.argv[2])
    print(f"[remap] готово: {sum(total.values())} строк.")
