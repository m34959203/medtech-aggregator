"""История/тренд цен (Спринт-3): медианная динамика по дням."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app import models  # noqa: F401
from app.models import Clinic, PriceHistory, ServiceCatalog


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    svc = ServiceCatalog(canonical_name="Общий анализ крови", category="Анализы", synonyms=["ОАК"])
    s.add(svc); s.add(Clinic(id=1, name="К", city="Алматы")); s.flush()
    d0 = date.today() - timedelta(days=30)
    # две даты: было 2000/2200 (медиана 2100) → стало 2400/2600 (медиана 2500)
    s.add_all([
        PriceHistory(clinic_id=1, service_id=svc.id, price=2000, recorded_at=d0),
        PriceHistory(clinic_id=1, service_id=svc.id, price=2200, recorded_at=d0),
        PriceHistory(clinic_id=1, service_id=svc.id, price=2400, recorded_at=date.today()),
        PriceHistory(clinic_id=1, service_id=svc.id, price=2600, recorded_at=date.today()),
    ])
    s.commit(); sid = svc.id; s.close()

    def _ov():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _ov
    c = TestClient(app); c.sid = sid
    yield c
    app.dependency_overrides.clear()


def test_history_endpoint_trend(client):
    r = client.get(f"/api/services/{client.sid}/history").json()
    t = r["trend"]
    assert t is not None and len(t["points"]) == 2
    assert t["points"][0]["median"] == 2100 and t["points"][1]["median"] == 2500
    assert t["change_pct"] == pytest.approx(19.0, abs=0.1) and t["direction"] == "up"


def test_history_absent_when_one_point(client):
    # услуга без истории → trend None
    other = client.get("/api/services/99999/history")
    assert other.status_code == 404
