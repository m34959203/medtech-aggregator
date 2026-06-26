"""Авторизация админ-зоны: закрытые роуты, логин по токену → cookie."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app import models  # noqa: F401


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


pytestmark = pytest.mark.real_admin  # эти тесты проверяют РЕАЛЬНЫЙ гард (без обхода)


def test_protected_route_401_without_token(client):
    # admin_token задан (conftest), но кука/заголовок не переданы → 401
    assert client.get("/api/ingest/stats").status_code == 401
    assert client.get("/api/review/queue").status_code == 401
    assert client.post("/api/portal/issue/1").status_code == 401
    assert client.get("/api/export/catalog").status_code == 401


def test_public_routes_open(client):
    assert client.get("/api/cities").status_code == 200
    assert client.get("/health").status_code == 200
    # пользовательские POST-и (жалоба/лид) — публичные
    assert client.post("/api/feedback/price-report", json={"service": "ОАК"}).status_code == 200


def test_bearer_token_grants_access(client):
    r = client.get("/api/ingest/stats", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200


def test_wrong_token_401(client):
    r = client.get("/api/ingest/stats", headers={"Authorization": "Bearer WRONG"})
    assert r.status_code == 401


def test_login_sets_cookie_then_access(client):
    assert client.post("/api/auth/login", json={"token": "WRONG"}).status_code == 401
    ok = client.post("/api/auth/login", json={"token": "test-token"})
    assert ok.status_code == 200
    # кука сохранилась в client → защищённый роут доступен
    assert client.get("/api/ingest/stats").status_code == 200
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is True and me["configured"] is True
    # логаут → снова 401
    client.post("/api/auth/logout")
    assert client.get("/api/ingest/stats").status_code == 401
