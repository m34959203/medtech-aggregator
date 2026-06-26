"""Self-service портал клиники (Спринт-3): доступ по токену, правка/подтверждение цен."""
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
from app.models import Clinic, Price, ServiceCatalog


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    svc = ServiceCatalog(canonical_name="Общий анализ крови", category="Анализы", synonyms=["ОАК"])
    s.add(svc)
    cl = Clinic(name="Клиника А", city="Алматы", address="ул. Абая, 1", phone="+7")
    s.add(cl)
    s.flush()
    s.add(Price(clinic_id=cl.id, service_id=svc.id, source_type="web_scrape", raw_name="ОАК",
                price=2000, currency="KZT", match_confidence=0.9))
    s.commit()
    cid = cl.id
    s.close()

    def _override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    c = TestClient(app); c.cid = cid
    yield c
    app.dependency_overrides.clear()


def test_issue_and_view(client):
    issued = client.post(f"/api/portal/issue/{client.cid}").json()
    token = issued["token"]
    assert token and issued["portal_path"] == f"/clinic/{token}"
    view = client.get(f"/api/portal/{token}").json()
    assert view["clinic"]["name"] == "Клиника А"
    assert len(view["prices"]) == 1 and view["prices"][0]["confirmed"] is False


def test_bad_token_404(client):
    assert client.get("/api/portal/nope").status_code == 404


def test_edit_price_marks_confirmed_upload(client):
    token = client.post(f"/api/portal/issue/{client.cid}").json()["token"]
    pid = client.get(f"/api/portal/{token}").json()["prices"][0]["price_id"]
    r = client.patch(f"/api/portal/{token}/price/{pid}", json={"price": 2300})
    assert r.status_code == 200
    p = client.get(f"/api/portal/{token}").json()["prices"][0]
    assert p["price"] == 2300 and p["confirmed"] is True and p["source_type"] == "upload"


def test_confirm_all(client):
    token = client.post(f"/api/portal/issue/{client.cid}").json()["token"]
    assert client.post(f"/api/portal/{token}/confirm-all").json()["confirmed"] == 1
    assert client.get(f"/api/portal/{token}").json()["confirmed_count"] == 1


def test_portal_upload_own_pricelist(client):
    token = client.post(f"/api/portal/issue/{client.cid}").json()["token"]
    csv = "Услуга;Цена\nОбщий анализ крови;1800\n".encode("utf-8")
    r = client.post(f"/api/portal/{token}/upload",
                    files={"file": ("price.csv", csv, "text/csv")})
    assert r.status_code == 200
    assert r.json()["status"] == "normalized"
    # цена клиники обновилась официальной загрузкой (upload приоритетнее web_scrape)
    p = client.get(f"/api/portal/{token}").json()["prices"][0]
    assert p["source_type"] == "upload" and p["price"] == 1800


def test_edit_foreign_price_rejected(client):
    """Правка чужой цены (нет такой у клиники) → 404."""
    token = client.post(f"/api/portal/issue/{client.cid}").json()["token"]
    assert client.patch(f"/api/portal/{token}/price/9999", json={"price": 100}).status_code == 404
