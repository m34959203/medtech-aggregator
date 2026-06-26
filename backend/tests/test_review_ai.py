"""ИИ-разбор очереди ревью: предложения + применение (LLM замокан, офлайн)."""
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
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = TS()
    he4 = ServiceCatalog(id=1, canonical_name="HE4", category="Анализы", synonyms=[])
    wrong = ServiceCatalog(id=2, canonical_name="1,25(OH)2D3", category="Анализы", synonyms=[])
    s.add_all([he4, wrong])
    s.add(Clinic(id=1, name="Invitro", city="Алматы"))
    # спорная цена (conf ниже порога), привязана к ВЕРНОЙ услуге (self-match) → confirm
    s.add(Price(id=10, clinic_id=1, service_id=1, raw_name="HE4 (Human epididymis protein 4)",
                price=7250, currency="KZT", source_type="web_scrape", match_confidence=0.27))
    # мусорная позиция, привязана к чему попало → junk
    s.add(Price(id=11, clinic_id=1, service_id=2, raw_name="Прoвeрьтe здoрoвьe рeбeнка",
                price=13215, currency="KZT", source_type="web_scrape", match_confidence=0.41))
    s.commit(); s.close()

    def _ov():
        db = TS()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _ov
    c = TestClient(app); c.Session = TS
    yield c
    app.dependency_overrides.clear()


def test_ai_resolve_graceful_without_llm(client):
    """Без LLM-ключа (conftest мокает json_completion→None) — корректный skip, без падения."""
    r = client.post("/api/review/ai-resolve", json={"limit": 10, "apply": True}).json()
    assert r["processed"] == 2 and r["applied"] == 0
    assert all(p["action"] == "skip" for p in r["proposals"])


def test_ai_resolve_applies_confident_decisions(client, monkeypatch):
    """LLM решает: HE4→confirm, мусор→junk. apply применяет уверенные."""
    def fake_decide(raw, current, candidates):
        if "здoрoвьe" in raw or "Прoвeрьтe" in raw:
            return {"action": "junk", "service_id": None, "reason": "не услуга", "confidence": 0.95}
        return {"action": "confirm", "service_id": None, "reason": "та же услуга", "confidence": 0.9}
    monkeypatch.setattr("app.routers.review._ai_decide", fake_decide)

    r = client.post("/api/review/ai-resolve", json={"limit": 10, "apply": True, "min_confidence": 0.8}).json()
    assert r["applied"] == 2

    db = client.Session()
    he4 = db.get(Price, 10)
    junk = db.get(Price, 11)
    assert he4 is not None and he4.match_confidence == 1.0  # confirmed
    assert junk is None  # junk → удалена
    db.close()


def test_review_price_new_action_creates_service(client):
    """Действие 'new' создаёт услугу из сырого имени и переназначает."""
    before = client.Session()
    n0 = before.query(ServiceCatalog).count(); before.close()
    r = client.post("/api/review/price/11", json={"action": "new"}).json()
    assert r["ok"] is True
    db = client.Session()
    assert db.query(ServiceCatalog).count() == n0 + 1
    p = db.get(Price, 11)
    assert p.match_confidence == 1.0 and p.service_id != 2  # переназначена на новую
    db.close()
