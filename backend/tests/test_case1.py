"""Кейс 1: пакетный приём архива, экспорт каталога, статистика приёма."""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app import models  # noqa: F401
from app.models import Clinic, ServiceCatalog


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # одно общее соединение → одна in-memory БД на все сессии
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    s = TestingSession()
    s.add_all([
        ServiceCatalog(canonical_name="Общий анализ крови", category="Анализы", synonyms=["ОАК"]),
        ServiceCatalog(canonical_name="Приём терапевта", category="Приём врача",
                       synonyms=["Первичный приём терапевта"]),
    ])
    s.add(Clinic(id=1, name="Клиника А", city="Алматы", district="", address="ул. Абая, 1", phone="+7"))
    s.add(Clinic(id=2, name="Клиника Б", city="Астана", district="", address="пр. Мира, 2", phone="+7"))
    s.commit()
    s.close()

    def _override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _csv(rows: str) -> bytes:
    return ("Услуга;Цена\n" + rows).encode("utf-8")


def test_batch_zip_one_report(client):
    """Zip из двух прайсов разных клиник (префикс <id>_) → один отчёт по всем."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("1_lab.csv", _csv("ОАК;2500\n"))
        zf.writestr("2_doctors.csv", _csv("Первичный приём терапевта;6000\n"))
    buf.seek(0)
    r = client.post(
        "/api/ingest/upload-batch",
        files={"files": ("archive.zip", buf.getvalue(), "application/zip")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["totals"]["files"] == 2
    assert data["totals"]["ok"] == 2
    assert data["totals"]["items"] == 2
    clinics = {f["clinic_id"] for f in data["files"]}
    assert clinics == {1, 2}  # каждый файл ушёл в свою клинику по префиксу


def test_batch_multiple_files_default_clinic(client):
    """Несколько файлов без префикса → общий clinic_id из формы."""
    r = client.post(
        "/api/ingest/upload-batch",
        data={"clinic_id": "1"},
        files=[
            ("files", ("lab.csv", _csv("ОАК;2400\n"), "text/csv")),
            ("files", ("more.csv", _csv("Первичный приём терапевта;5500\n"), "text/csv")),
        ],
    )
    assert r.status_code == 200, r.text
    assert all(f.get("clinic_id") == 1 for f in r.json()["files"] if f["status"] == "ok")


def test_export_catalog_xlsx_and_csv(client):
    # сначала зальём данные
    client.post("/api/ingest/upload-batch", data={"clinic_id": "1"},
                files=[("files", ("p.csv", _csv("ОАК;2400\n"), "text/csv"))])
    rx = client.get("/api/export/catalog?format=xlsx")
    assert rx.status_code == 200
    assert "spreadsheetml" in rx.headers["content-type"]
    assert rx.headers["content-disposition"].endswith('.xlsx"')
    assert rx.content[:2] == b"PK"  # валидный xlsx (zip)
    rc = client.get("/api/export/catalog?format=csv")
    assert rc.status_code == 200
    assert "Общий анализ крови" in rc.content.decode("utf-8-sig")
    assert client.get("/api/export/catalog?format=pdf").status_code == 422


def test_stats_endpoint(client):
    client.post("/api/ingest/upload-batch", data={"clinic_id": "1"},
                files=[("files", ("p.csv", _csv("ОАК;2400\n"), "text/csv"))])
    st = client.get("/api/ingest/stats").json()
    assert st["clinics"] == 2 and st["services"] >= 2
    assert st["prices"] >= 1 and st["runs"] >= 1
    assert "upload" in st["by_source"]
