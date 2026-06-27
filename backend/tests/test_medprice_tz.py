"""Покрытие требований ТЗ Кейс1 «MedPrice»: §2.2 (поля/валюта/категория),
§3.3 (фильтры/сортировки/автодополнение/профиль), §4 (свежесть 30 дней)."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
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
    cheap = Clinic(name="Дешёвая", city="Алматы", rating=4.8, online_booking=True,
                   working_hours="09-18", website="https://a.kz", lat=43.2, lng=76.9)
    pricey = Clinic(name="Дорогая", city="Астана", rating=3.5, online_booking=False,
                    working_hours="08-20", website="https://b.kz", lat=51.1, lng=71.4)
    s.add(cheap)
    s.add(pricey)
    s.flush()
    now = datetime.utcnow()
    # свежая дешёвая цена
    s.add(Price(clinic_id=cheap.id, service_id=svc.id, raw_name="ОАК", price=1500, currency="KZT",
                source_type="web_scrape", valid_from=date.today(), parsed_at=now,
                is_active=True, duration_days=1))
    # свежая дорогая цена
    s.add(Price(clinic_id=pricey.id, service_id=svc.id, raw_name="ОАК", price=3000, currency="KZT",
                source_type="web_scrape", valid_from=date.today(), parsed_at=now, is_active=True))
    s.commit()
    sid = svc.id
    cheap_id = cheap.id
    pricey_id = pricey.id
    s.close()

    def _ov():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _ov
    c = TestClient(app); c.sid = sid; c.Session = Session
    c.cheap_id = cheap_id; c.pricey_id = pricey_id
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
    p = client.get(f"/api/clinics/{client.cheap_id}/profile").json()
    assert p["name"] == "Дешёвая" and p["working_hours"] == "09-18"
    assert p["rating"] == 4.8 and p["online_booking"] is True
    assert p["services_count"] == 1 and p["services"][0]["price"] == 1500


def test_null_is_active_treated_as_fresh(client):
    # Перенесённые/легаси строки имеют is_active=NULL — выдача НЕ должна их отсекать
    # (баг cutover: bool(None)=False прятал все 801 прод-цену). NULL = активна.
    # NULL ставим сырым SQL: в проде additive-колонка nullable (модель NOT NULL,
    # ORM бы не дал записать None — а легаси-строки именно NULL).
    db = client.Session()
    db.execute(text("UPDATE prices SET is_active = NULL"))
    db.commit(); db.close()
    r = client.get(f"/api/compare/{client.sid}").json()
    assert r["offers_count"] == 2  # обе цены остаются в выдаче


def test_explicit_false_is_active_excluded(client):
    # А вот ЯВНЫЙ False (scheduler пометил протухшей) — отсекаем.
    db = client.Session()
    db.query(Price).filter(Price.clinic_id == client.pricey_id).first().is_active = False
    db.commit(); db.close()
    r = client.get(f"/api/compare/{client.sid}").json()
    assert r["offers_count"] == 1 and r["offers"][0]["clinic_name"] == "Дешёвая"


def test_stale_price_excluded_from_results(client):
    # делаем дорогую цену протухшей (>30 дней) — её не должно быть в выдаче §4
    db = client.Session()
    old = db.query(Price).filter(Price.clinic_id == client.pricey_id).first()
    old.parsed_at = datetime.utcnow() - timedelta(days=40)
    old.valid_from = date.today() - timedelta(days=40)
    db.commit(); db.close()
    r = client.get(f"/api/compare/{client.sid}").json()
    assert r["offers_count"] == 1 and r["offers"][0]["clinic_name"] == "Дешёвая"
    # include_stale через прямой билдер не нужен — фильтр по умолчанию строгий


# ---------- §2.2 строгое закрытие: enum-типы + плоская запись ----------

def test_currency_enum_normalizes_noise():
    from app.ingestion.currency import Currency, normalize
    assert normalize("Тенге") is Currency.KZT
    assert normalize("₸") is Currency.KZT
    assert normalize("$") is Currency.USD
    assert normalize("") is Currency.KZT
    assert normalize("неведомая") is Currency.KZT  # неизвестное → KZT, не падаем
    # хранимая валюта после конверсии — всегда KZT, оригинал каноничен
    kzt, orig, cur = to_kzt(10, "$")
    assert cur == "USD" and orig == 10.0 and kzt > 10


def test_category_is_typed_enum():
    # члены — полноценные строки И типизированный enum
    assert isinstance(cat.LAB, cat.Category) and cat.LAB == "лаборатория"
    assert {c.value for c in cat.Category} == {
        "лаборатория", "приём врача", "диагностика", "процедура"}


def test_records_endpoint_verbatim_tz_22(client):
    """§2.2 «в точь точь»: плоская запись содержит ровно поля ТЗ с нужными типами."""
    rows = client.get("/api/records").json()
    assert rows, "ожидаем хотя бы одну запись"
    rec = rows[0]
    expected = {
        "clinic_id", "clinic_name", "city", "address", "phone", "working_hours",
        "source_url", "service_id", "service_name_raw", "service_name_norm",
        "category", "price_kzt", "currency", "duration_days", "parsed_at", "is_active",
    }
    assert set(rec.keys()) == expected  # ни одного лишнего/недостающего поля
    assert rec["category"] in {c.value for c in cat.Category}      # строгий enum
    assert rec["currency"] in ("KZT", "USD")                       # строгий enum
    assert rec["service_name_norm"] == "Общий анализ крови"        # привязка к справочнику
    assert rec["service_name_raw"] == "ОАК"
    assert isinstance(rec["is_active"], bool)
    # фильтр по городу работает
    alm = client.get("/api/records", params={"city": "Алматы"}).json()
    assert alm and all(x["city"] == "Алматы" for x in alm)


def test_records_invalid_enum_rejected_by_schema():
    """Строгость на уровне схемы: не-enum валюта/категория не пройдут валидацию."""
    import pytest as _pytest
    from pydantic import ValidationError
    from app.schemas import CollectedRecord
    base = dict(
        clinic_id=__import__("uuid").uuid4(), clinic_name="X", city="A", address="",
        phone="", working_hours="", source_url="", service_id=__import__("uuid").uuid4(),
        service_name_raw="r", service_name_norm="n", category="лаборатория",
        price_kzt="1500", currency="KZT", duration_days=None,
        parsed_at=datetime.utcnow(), is_active=True,
    )
    CollectedRecord(**base)  # валидная — ок
    with _pytest.raises(ValidationError):
        CollectedRecord(**{**base, "currency": "EUR"})
    with _pytest.raises(ValidationError):
        CollectedRecord(**{**base, "category": "Прочее"})
