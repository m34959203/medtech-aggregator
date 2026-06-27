"""Тесты MedArchive: извлечение тарифов резидент/нерезидент + код тарификатора,
code-first нормализация и API-контракт партнёров."""
import io
import os

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db import Base, get_db
from app.ingestion import archive_extractor as ae
from app.ingestion.archive_service import ingest_archive
from app.ingestion.normalizer import Normalizer
from app.main import app
from app.models import Clinic, ServiceCatalog


# ── код тарификатора ─────────────────────────────────────────────────────────
def test_norm_code_cyrillic_to_latin():
    assert ae.norm_code("В02.110.002 кровь") == "B02.110.002"   # кириллич. В → латин. B
    assert ae.norm_code("A02.020.000.2") == "A02.020.000"        # хвостовой суффикс отрезан
    assert ae.norm_code("без кода") is None


def test_parse_price_thousands_vs_decimal():
    assert ae.parse_price("10 002") == 10002
    assert ae.parse_price("10.002") == 10002      # точка = тысячи (3 знака)
    assert ae.parse_price("2099.5") == 2099.5     # точка = десятичный (1 знак)
    assert ae.parse_price("16 380 ₸") == 16380


# ── извлечение xlsx с двумя тарифами и кодом ─────────────────────────────────
def _make_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Прейскурант", None, None, None])           # шум до шапки
    ws.append(["№", "Код услуги", "Наименование",
               "Цена для граждан РК", "Цена для граждан СНГ"])  # шапка не в 1-й строке
    ws.append([1, "B02.110.002", "Общий анализ крови", 880, 1410])
    ws.append([2, "A02.004.000", "Приём акушер-гинеколога", 5000, 7000])
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_extract_xlsx_resident_nonresident_and_code():
    fmt, items = ae.detect_and_parse("price.xlsx", _make_xlsx())
    assert fmt == "xlsx"
    by_code = {it.code: it for it in items if it.code}
    assert "B02.110.002" in by_code
    oak = by_code["B02.110.002"]
    assert oak.price_resident == 880 and oak.price_nonresident == 1410
    assert oak.name.startswith("Общий анализ крови")


# ── code-first нормализация + приём документа ────────────────────────────────
@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = TestingSession()
    # целевой справочник
    s.add(ServiceCatalog(canonical_name="Общий анализ крови", category="Анализы",
                         synonyms=[], tarificator_code="B02.110.002", specialty="Гематология"))
    s.add(Clinic(name="Клиника 1", city="Алматы"))
    s.commit()
    app.dependency_overrides[get_db] = lambda: s
    yield s
    app.dependency_overrides.clear()
    s.close()


def test_code_first_match_is_exact(db):
    nz = Normalizer(db)
    # сырое имя совсем другое, но КОД совпадает → точное сопоставление conf=1.0
    svc, conf = nz.match_archive("кровь с ЭДТА (ОАК)", "B02.110.002")
    assert conf == 1.0 and svc.canonical_name == "Общий анализ крови"
    # нет кода и непохожее имя → unmatched (None), справочник не загрязняется
    svc2, _ = nz.match_archive("абракадабра ноунейм", None)
    assert svc2 is None


def test_ingest_archive_writes_dual_tariff(db):
    clinic = db.query(Clinic).first()
    items = [ae.ArchiveItem(name="кровь с ЭДТА", code="B02.110.002",
                            price_resident=880, price_nonresident=1410, price_original=880)]
    st = ingest_archive(db, clinic_id=clinic.id, file_name="k1.pdf", fmt="pdf", items=items)
    assert st["matched"] == 1 and st["services"] == 1
    from app.models import Price
    p = db.query(Price).first()
    assert float(p.price_resident) == 880 and float(p.price_nonresident) == 1410
    assert p.tarificator_code == "B02.110.002"


# ── API-контракт MedArchive ──────────────────────────────────────────────────
def test_partners_api_contract(db):
    clinic = db.query(Clinic).first()
    items = [ae.ArchiveItem(name="кровь с ЭДТА", code="B02.110.002",
                            price_resident=880, price_nonresident=1410, price_original=880)]
    ingest_archive(db, clinic_id=clinic.id, file_name="k1.pdf", fmt="pdf", items=items)
    client = TestClient(app)

    r = client.get("/api/partners")
    assert r.status_code == 200 and r.json()[0]["services_count"] == 1

    r = client.get(f"/api/partners/{clinic.id}/services")
    svc = r.json()["services"][0]
    assert svc["price_resident"] == 880 and svc["price_nonresident"] == 1410
    assert svc["tarificator_code"] == "B02.110.002"

    sid = svc["service_id"]
    r = client.get(f"/api/services/{sid}/partners")
    assert r.json()["partners"][0]["price_nonresident"] == 1410

    r = client.get("/api/archive/quality")
    assert r.json()["positions"] == 1


# ── §2.1/§5: приём архива через HTTP + сохранение оригиналов + повторная обработка ──
def test_archive_endpoint_saves_original_and_dual_tariff(db, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.archive_storage_dir", str(tmp_path), raising=False)
    clinic = db.query(Clinic).first()
    client = TestClient(app)

    r = client.post(
        "/api/ingest/archive",
        data={"clinic_id": str(clinic.id)},
        files={"files": ("price.xlsx", _make_xlsx(),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["truncated"] is False
    f0 = body["files"][0]
    assert f0["status"] == "ok" and f0["stored"] is True
    assert f0["parse_status"] in ("normalized", "needs_review")
    run_id = f0["run_id"]

    # резидент/нерезидент записаны (§4.4 / §3.3 PriceItem)
    from app.models import IngestionRun, Price
    p = db.query(Price).filter(Price.tarificator_code == "B02.110.002").first()
    assert p is not None and float(p.price_resident) == 880 and float(p.price_nonresident) == 1410

    # §2.1/§5: оригинал реально сохранён на диск и привязан к прогону
    run = db.get(IngestionRun, run_id)
    assert run.file_path and os.path.exists(run.file_path)
    assert run.clinic_id == clinic.id and run.effective_date is not None

    # §4.1: повторная обработка из сохранённого оригинала
    rr = client.post(f"/api/ingest/archive/{run_id}/reprocess")
    assert rr.status_code == 200, rr.text
    assert rr.json()["items"] >= 1


def test_archive_reprocess_404_when_no_original(db):
    """Прогон без сохранённого оригинала (старый MedPrice-путь) → 404, не 500."""
    clinic = db.query(Clinic).first()
    items = [ae.ArchiveItem(name="кровь с ЭДТА", code="B02.110.002",
                            price_resident=880, price_nonresident=1410, price_original=880)]
    st = ingest_archive(db, clinic_id=clinic.id, file_name="k1.pdf", fmt="pdf", items=items)
    client = TestClient(app)
    rr = client.post(f"/api/ingest/archive/{st['run_id']}/reprocess")
    assert rr.status_code == 404


# ── алиас канонов: дубль из справочника вливается в существующий канон ────────
def test_official_catalog_alias_folds_into_existing_canon(db):
    """«Глюкоза (кровь)» из официального справочника не плодит дубль, а вливается
    синонимом в витринный канон «Глюкоза (в крови)» (долг #41/#43)."""
    from app.ingestion.refcatalog import load_official_catalog

    db.add(ServiceCatalog(canonical_name="Глюкоза (в крови)", category="Анализы",
                          synonyms=["сахар"], tarificator_code=None, specialty=""))
    db.commit()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ID", "Специальность", "TarificatrCode", "Name_ru"])
    ws.append([1, "Лабораторная диагностика", "B03.016.006", "Глюкоза (кровь)"])
    bio = io.BytesIO(); wb.save(bio)

    stats = load_official_catalog(db, bio.getvalue())
    db.commit()

    # нового канона «Глюкоза (кровь)» НЕ создано
    assert db.query(ServiceCatalog).filter_by(canonical_name="Глюкоза (кровь)").first() is None
    primary = db.query(ServiceCatalog).filter_by(canonical_name="Глюкоза (в крови)").first()
    # имя из справочника осело синонимом, код подтянут
    assert "Глюкоза (кровь)" in primary.synonyms
    assert primary.tarificator_code == "B03.016.006"
    assert stats["created"] == 0
