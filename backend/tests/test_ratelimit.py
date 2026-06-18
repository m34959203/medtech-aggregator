"""Rate-limit публичных POST: после лимита — 429 с Retry-After."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app import models  # noqa: F401
from app.ratelimit import LIMITERS, RateLimiter


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def _ov():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _ov
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_unit_sliding_window():
    rl = RateLimiter(limit=2, window=60)
    assert rl.hit("a") == (True, 0)
    assert rl.hit("a")[0] is True
    ok, retry = rl.hit("a")
    assert ok is False and retry > 0
    assert rl.hit("b")[0] is True  # другой ключ — свой счётчик


def test_public_post_429_after_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    lim = LIMITERS["report"]
    orig = lim.limit
    lim.limit = 2
    lim.reset()
    try:
        for _ in range(2):
            assert client.post("/api/feedback/price-report", json={"service": "X"}).status_code == 200
        r = client.post("/api/feedback/price-report", json={"service": "X"})
        assert r.status_code == 429
        assert "retry-after" in {k.lower() for k in r.headers}
    finally:
        lim.limit = orig
        lim.reset()


def test_disabled_when_setting_off(client):
    # rate_limit_enabled=False (conftest) → лимит не срабатывает даже при крошечном лимите
    lim = LIMITERS["report"]
    orig = lim.limit
    lim.limit = 1
    lim.reset()
    try:
        for _ in range(5):
            assert client.post("/api/feedback/price-report", json={"service": "X"}).status_code == 200
    finally:
        lim.limit = orig
        lim.reset()
