"""Канонический справочник городов РК + подключение в фильтр (§3.3/§7)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data import kz_cities
from app.db import Base, get_db
from app.main import app
from app import models  # noqa: F401
from app.models import Clinic, Price, ServiceCatalog


def test_directory_has_90_cities():
    assert len(kz_cities.CITIES) == 90
    assert len(kz_cities.all_cities()) == 90
    assert len(kz_cities.names()) == 90


def test_canonical_city_normalizes_variants():
    # slug, латиница, регистр, алиасы источников → одно каноническое имя
    assert kz_cities.canonical_city("almaty") == "Алматы"
    assert kz_cities.canonical_city("Алматы") == "Алматы"
    assert kz_cities.canonical_city("АЛМАТЫ") == "Алматы"
    assert kz_cities.canonical_city("astana") == "Астана"
    assert kz_cities.canonical_city("nur-sultan") == "Астана"
    assert kz_cities.canonical_city("uk") == "Усть-Каменогорск"
    # неизвестный город не теряем, отдаём как есть (title)
    assert kz_cities.canonical_city("деревня") == "Деревня"
    assert kz_cities.canonical_city("") is None
    assert kz_cities.canonical_city(None) is None


def test_slugify():
    assert kz_cities.slugify("Усть-Каменогорск") == "ust-kamenogorsk"
    assert kz_cities.slugify("Шымкент") == "shymkent"


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = TS()
    svc = ServiceCatalog(canonical_name="ОАК", category="Анализы", synonyms=[])
    s.add(svc)
    s.add(Clinic(id=1, name="Клиника А", city="Алматы"))
    s.add(Clinic(id=2, name="Клиника Б", city="Астана"))
    s.flush()
    # у обеих клиник есть цена → оба города «с данными»
    s.add(Price(clinic_id=1, service_id=svc.id, raw_name="ОАК", price=1500, source_type="web_scrape"))
    s.add(Price(clinic_id=2, service_id=svc.id, raw_name="ОАК", price=2000, source_type="web_scrape"))
    s.commit()
    s.close()

    def _override():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_cities_endpoint_only_cities_with_data(client):
    """Фильтр отдаёт ТОЛЬКО города с ценами — без пустых из справочника."""
    cities = client.get("/api/cities").json()
    assert cities == ["Алматы", "Астана"]
    # пустые города справочника (без данных) в фильтр НЕ попадают
    assert "Тараз" not in cities and "Байконыр" not in cities


def test_cities_coverage_endpoint(client):
    cov = client.get("/api/cities/coverage").json()
    by_name = {c["name"]: c for c in cov}
    assert by_name["Алматы"]["has_data"] is True
    assert by_name["Алматы"]["clinics"] == 1
    # город из справочника без данных = зарегистрирован, данных нет
    assert by_name["Тараз"]["has_data"] is False
    assert by_name["Тараз"]["clinics"] == 0
