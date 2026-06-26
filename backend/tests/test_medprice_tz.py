"""Покрытие требований ТЗ Кейс1 «MedPrice»: §2.2 (поля/валюта/категория),
§3.3 (фильтры/сортировки/автодополнение/профиль), §4 (свежесть 30 дней)."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app import models  # noqa: F401
from app.models import Clinic, Price, ServiceCatalog
from app.ingestion.service import to_kzt
from app.ingestion import category as cat


# ---------- §2.2 чистые юниты ----------

def test_usd_to_kzt_conversion():
    kzt, orig, cur = to_kzt(100, "USD")
    assert kzt == pytest.approx(48000.0) and orig == 100.0 and cur == "USD"
    # KZT не конвертируется, оригинал не выставляется
    assert to_kzt(5000, "KZT") == (5000.0, None, "")


def test_category_enum_four_values():
    assert cat.to_enum("Гематология", "", "Общий анализ крови") == cat.LAB
    assert cat.to_enum("", "", "Приём кардиолога") == cat.DOCTOR
    assert cat.to_enum("", "", "УЗИ почек") == cat.DIAGNOSTIC
    assert cat.to_enum("", "", "Массаж спины") == cat.PROCEDURE
    assert cat.to_enum("", "", "") in cat.ENUM  # дефолт — валидный enum


# ---------- интеграция через API ----------

@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    svc = ServiceCatalog(canonical_name="Общий анализ крови", category="Гематология",
                         synonyms=["ОАК", "анализ крови"])
    s.add(svc)
    # 2 клиники с рейтингом/онлайн-записью/режимом работы/сайтом
    s.add(Clinic(id=1, name="Дешёвая", city="Алматы", rating=4.8, online_booking=True,
                 working_hours="09-18", website="https://a.kz", lat=43.2, lng=76.9))
    s.add(Clinic(id=2, name="Дорогая", city="Астана", rating=3.5, online_booking=False,
                 working_hours="08-20", website="https://b.kz", lat=51.1, lng=71.4))
    s.flush()
    now = datetime.utcnow()
    # свежая дешёвая цена
    s.add(Price(clinic_id=1, service_id=svc.id, raw_name="ОАК", price=1500, currency="KZT",
                source_type="web_scrape", valid_from=date.today(), parsed_at=now,
                is_active=True, duration_days=1))
    # свежая дорогая цена
    s.add(Price(clinic_id=2, service_id=svc.id, raw_name="ОАК", price=3000, currency="KZT",
                source_type="web_scrape", valid_from=date.today(), parsed_at=now, is_active=True))
    s.commit()
    sid = svc.id
    s.close()

    def _ov():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _ov
    c = TestClient(app); c.sid = sid; c.Session = Session
    yield c
    app.dependency_overrides.clear()


def test_offer_exposes_tz_fields(client):
    r = client.get(f"/api/compare/{client.sid}").json()
    assert r["category_enum"] == cat.LAB
    o = r["offers"][0]
    for f in ("working_hours", "website", "source_url", "rating", "online_booking",
              "duration_days", "is_active", "parsed_at"):
        assert f in o
    assert o["working_hours"] and o["source_url"]


def test_filter_min_rating(client):
    r = client.get(f"/api/compare/{client.sid}", params={"min_rating": 4.0}).json()
    assert r["offers_count"] == 1 and r["offers"][0]["clinic_name"] == "Дешёвая"


def test_filter_online_booking(client):
    r = client.get(f"/api/compare/{client.sid}", params={"online_booking": "true"}).json()
    assert r["offers_count"] == 1 and r["offers"][0]["online_booking"] is True


def test_filter_price_range_min(client):
    r = client.get(f"/api/compare/{client.sid}", params={"min_price": 2000}).json()
    assert r["offers_count"] == 1 and r["offers"][0]["price"] == 3000


def test_sort_updated_and_price(client):
    asc = client.get(f"/api/compare/{client.sid}", params={"sort": "price_asc"}).json()
    assert [o["price"] for o in asc["offers"]] == [1500, 3000]
    desc = client.get(f"/api/compare/{client.sid}", params={"sort": "price_desc"}).json()
    assert [o["price"] for o in desc["offers"]] == [3000, 1500]


def test_suggest_autocomplete(client):
    assert "Общий анализ крови" in client.get("/api/suggest", params={"q": "ана"}).json()
    assert client.get("/api/suggest", params={"q": "я"}).json() == []  # <2 символов


def test_categories_are_enum(client):
    cats = client.get("/api/categories").json()
    assert cats and all(c in cat.ENUM for c in cats)


def test_clinic_profile_lists_all_services(client):
    p = client.get("/api/clinics/1/profile").json()
    assert p["name"] == "Дешёвая" and p["working_hours"] == "09-18"
    assert p["rating"] == 4.8 and p["online_booking"] is True
    assert p["services_count"] == 1 and p["services"][0]["price"] == 1500


def test_stale_price_excluded_from_results(client):
    # делаем дорогую цену протухшей (>30 дней) — её не должно быть в выдаче §4
    db = client.Session()
    old = db.query(Price).filter(Price.clinic_id == 2).first()
    old.parsed_at = datetime.utcnow() - timedelta(days=40)
    old.valid_from = date.today() - timedelta(days=40)
    db.commit(); db.close()
    r = client.get(f"/api/compare/{client.sid}").json()
    assert r["offers_count"] == 1 and r["offers"][0]["clinic_name"] == "Дешёвая"
    # include_stale через прямой билдер не нужен — фильтр по умолчанию строгий
