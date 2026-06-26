"""Корзина-рецепт (Спринт-3): направление → распознавание услуг → выгодный вариант."""
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
    oak = ServiceCatalog(canonical_name="Общий анализ крови", category="Анализы", synonyms=["ОАК"])
    glu = ServiceCatalog(canonical_name="Глюкоза (в крови)", category="Анализы", synonyms=["глюкоза", "сахар"])
    ttg = ServiceCatalog(canonical_name="ТТГ (тиреотропный гормон)", category="Анализы", synonyms=["ТТГ"])
    s.add_all([oak, glu, ttg])
    a = Clinic(name="Клиника А", city="Алматы", address="ул. Абая, 1", phone="+7 701")
    b = Clinic(name="Клиника Б", city="Алматы", address="пр. Мира, 2", phone="+7 702")
    s.add_all([a, b])
    s.flush()
    P = lambda c, sv, pr: Price(clinic_id=c, service_id=sv, source_type="web_scrape",
                                raw_name="x", price=pr, currency="KZT", match_confidence=1.0)
    s.add_all([
        P(a.id, oak.id, 2000), P(a.id, glu.id, 1000), P(a.id, ttg.id, 3000),  # А: всё
        P(b.id, oak.id, 1800), P(b.id, glu.id, 1200),                         # Б: без ТТГ
    ])
    s.commit()
    s.close()

    def _ov():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _ov
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_recommend_from_text(client):
    text = "Направление\n1. Общий анализ крови\n2. Глюкоза\n3. ТТГ\nФИО: Иванов И."
    r = client.post("/api/basket/recommend", json={"text": text, "city": "Алматы"}).json()
    assert r["services_found"] == 3
    # mixed: ОАК 1800(Б) + Глюкоза 1000(А) + ТТГ 3000(А) = 5800
    assert r["total_cheapest_mixed"] == 5800
    # одна клиника: А покрывает все 3 (2000+1000+3000=6000)
    best = r["best_single_clinic"]
    assert best["clinic_name"] == "Клиника А" and best["covered"] == 3 and best["total"] == 6000
    assert best["missing"] == []
    # «ФИО: Иванов» не услуга → отфильтровано gate'ом (шум): не в recognized
    # (и не в unrecognized — шум молча пропускается, TASK 1 боевого отчёта)
    assert all("ФИО" not in it["input"] and "Иванов" not in it["input"]
               for it in r["recognized"])


def test_recommend_by_names_list(client):
    r = client.post("/api/basket/recommend", json={"names": ["ОАК", "сахар крови"]}).json()
    assert r["services_found"] == 2
    found = {it["canonical"] for it in r["recognized"]}
    assert found == {"Общий анализ крови", "Глюкоза (в крови)"}


def test_single_clinic_prefers_coverage_then_price(client):
    # только ОАК+Глюкоза: Б дешевле по сумме (1800+1200=3000) и покрывает оба → лучше А (3000 же? А=3000)
    r = client.post("/api/basket/recommend",
                    json={"names": ["Общий анализ крови", "Глюкоза"], "city": "Алматы"}).json()
    best = r["best_single_clinic"]
    assert best["covered"] == 2
    assert best["clinic_name"] == "Клиника Б" and best["total"] == 3000  # А тоже 3000, но Б не дороже


def test_recommend_file_plaintext(client):
    txt = "Общий анализ крови\nГлюкоза\n".encode("utf-8")
    r = client.post("/api/basket/recommend-file",
                    data={"city": "Алматы"},
                    files={"file": ("recept.txt", txt, "text/plain")})
    assert r.status_code == 200
    assert r.json()["services_found"] == 2


def test_recommend_empty_422(client):
    assert client.post("/api/basket/recommend", json={"text": "...... 123"}).status_code == 422
