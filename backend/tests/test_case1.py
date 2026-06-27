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
        ServiceCatalog(canonical_name="Глюкоза (в крови)", category="Анализы",
                       synonyms=["сахар", "глюкоза"]),
        ServiceCatalog(canonical_name="Приём терапевта", category="Приём врача",
                       synonyms=["Первичный приём терапевта"]),
    ])
    a = Clinic(name="Клиника А", city="Алматы", district="", address="ул. Абая, 1", phone="+7")
    b = Clinic(name="Клиника Б", city="Астана", district="", address="пр. Мира, 2", phone="+7")
    s.add(a)
    s.add(b)
    s.flush()
    cid1, cid2 = a.id, b.id
    s.commit()
    s.close()

    def _override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    c = TestClient(app); c.cid1 = cid1; c.cid2 = cid2; c.Session = TestingSession
    yield c
    app.dependency_overrides.clear()


def _csv(rows: str) -> bytes:
    return ("Услуга;Цена\n" + rows).encode("utf-8")


def test_batch_zip_one_report(client):
    """Zip из двух прайсов разных клиник (префикс <id>_) → один отчёт по всем."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{client.cid1}_lab.csv", _csv("ОАК;2500\n"))
        zf.writestr(f"{client.cid2}_doctors.csv", _csv("Первичный приём терапевта;6000\n"))
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
    assert clinics == {str(client.cid1), str(client.cid2)}  # каждый файл ушёл в свою клинику по префиксу


def test_batch_multiple_files_default_clinic(client):
    """Несколько файлов без префикса → общий clinic_id из формы."""
    r = client.post(
        "/api/ingest/upload-batch",
        data={"clinic_id": str(client.cid1)},
        files=[
            ("files", ("lab.csv", _csv("ОАК;2400\n"), "text/csv")),
            ("files", ("more.csv", _csv("Первичный приём терапевта;5500\n"), "text/csv")),
        ],
    )
    assert r.status_code == 200, r.text
    assert all(f.get("clinic_id") == str(client.cid1) for f in r.json()["files"] if f["status"] == "ok")


def test_export_catalog_xlsx_and_csv(client):
    # сначала зальём данные
    client.post("/api/ingest/upload-batch", data={"clinic_id": str(client.cid1)},
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
    client.post("/api/ingest/upload-batch", data={"clinic_id": str(client.cid1)},
                files=[("files", ("p.csv", _csv("ОАК;2400\n"), "text/csv"))])
    st = client.get("/api/ingest/stats").json()
    assert st["clinics"] == 2 and st["services"] >= 2
    assert st["prices"] >= 1 and st["runs"] >= 1
    assert "upload" in st["by_source"]
    for k in ("empty_runs", "failed_runs", "reports_new"):
        assert k in st and isinstance(st[k], int)


def test_compare_exposes_attributes_and_variants(client):
    """Сквозь: батч «Глюкоза крови»+«Глюкоза в моче» → разведены → compare даёт теги и сёстру."""
    import io as _io, zipfile as _zip
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w") as zf:
        zf.writestr(f"{client.cid1}_lab.csv", _csv("Глюкоза (сахар крови);500\nГлюкоза в моче;700\n"))
    buf.seek(0)
    r = client.post("/api/ingest/upload-batch",
                    data={"clinic_id": str(client.cid1)},
                    files={"files": ("a.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 200, r.text

    # найдём id кровяной и мочевой услуг
    svcs = {s["canonical_name"]: s["id"] for s in client.get("/api/services?limit=99").json()}
    assert "Глюкоза в моче" in svcs, "мочевой вариант должен был создаться нормализатором"

    cmp = client.get(f"/api/compare/{svcs['Глюкоза (в крови)']}").json()
    assert cmp["attributes"]["biomaterial"] == "blood"
    assert "кровь" in cmp["attributes"]["tags"]
    sib = {v["canonical_name"] for v in cmp["variants"]}
    assert "Глюкоза в моче" in sib  # перелинковка на другой вариант


def test_price_report_feedback_loop(client):
    r = client.post("/api/feedback/price-report", json={
        "clinic_id": str(client.cid1), "clinic_name": "Клиника А", "service": "ОАК", "price": 2500,
        "note": "на сайте дешевле",
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "new"
    lst = client.get("/api/feedback/price-reports?status=new").json()
    assert any(x["clinic_name"] == "Клиника А" for x in lst)


def test_lead_create_and_validation(client):
    bad = client.post("/api/leads", json={"clinic_id": str(client.cid1), "phone": "123"})
    assert bad.status_code == 422  # короткий телефон
    ok = client.post("/api/leads", json={
        "clinic_id": str(client.cid1), "clinic_name": "Клиника А", "service": "ОАК",
        "price": 2400, "name": "Иван", "phone": "+7 701 234 56 78",
    })
    assert ok.status_code == 200 and ok.json()["status"] == "new"
    assert any(l["name"] == "Иван" for l in client.get("/api/leads?status=new").json())


def test_review_queue_and_confirm(client):
    # «чужая» позиция → новая услуга с низкой уверенностью → попадает в очередь
    client.post("/api/ingest/upload-batch", data={"clinic_id": str(client.cid1)},
                files=[("files", ("p.csv", _csv("Криоконсервация эмбрионов;90000\n"), "text/csv"))])
    q = client.get("/api/review/queue").json()
    assert q["low_confidence"], "низко-уверенная позиция должна быть в очереди"
    pid = q["low_confidence"][0]["price_id"]
    r = client.post(f"/api/review/price/{pid}", json={"action": "confirm"})
    assert r.status_code == 200
    # после подтверждения уверенность 1.0 → вышла из очереди
    assert all(it["price_id"] != pid for it in client.get("/api/review/queue").json()["low_confidence"])


def test_review_report_status(client):
    client.post("/api/feedback/price-report", json={"clinic_name": "К", "service": "ОАК"})
    rid = client.get("/api/review/queue").json()["reports"][0]["id"]
    assert client.post(f"/api/review/report/{rid}", json={"status": "fixed"}).status_code == 200
    assert not client.get("/api/review/queue").json()["reports"]  # ушла из очереди


def test_anonymous_clinics_hidden_from_public_aggregator(client):
    """Обезличенные клиники (is_public=False) не попадают в публичный поиск/сравнение/
    список клиник, но их цены остаются в БД (Кейс-2/MedArchive)."""
    from app.models import Clinic, Price, ServiceCatalog

    db = client.Session()
    svc_id = db.query(ServiceCatalog).filter_by(canonical_name="Глюкоза (в крови)").first().id
    # публичная клиника с ценой
    db.add(Price(clinic_id=client.cid1, service_id=svc_id, raw_name="Глюкоза", price=900,
                 currency="KZT", match_confidence=1.0))
    # обезличенная архив-клиника с ценой
    anon = Clinic(name="Клиника 9", city="", district="", address="", phone="", is_public=False)
    db.add(anon); db.flush()
    db.add(Price(clinic_id=anon.id, service_id=svc_id, raw_name="Глюкоза (сахар)", price=500,
                 currency="KZT", match_confidence=1.0))
    db.commit(); db.close()

    # /api/compare — только публичный оффер (900), анонимный (500) скрыт
    cmp = client.get(f"/api/compare/{svc_id}").json()
    names = [o["clinic_name"] for o in cmp["offers"]]
    assert "Клиника А" in names
    assert "Клиника 9" not in names
    assert cmp["offers_count"] == 1

    # /api/clinics — анонимной нет
    clinics = [c["name"] for c in client.get("/api/clinics").json()]
    assert "Клиника 9" not in clinics
