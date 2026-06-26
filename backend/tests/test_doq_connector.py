"""Коннектор к API агрегатора клиник doq.kz — офлайн (без сети).

Сетевые GET (через robots.polite_get) подменяем заглушкой, которая отдаёт
зафиксированные ответы реального API doq.kz. Так тест не зависит от доступности
сервиса и проверяет именно ПАРСИНГ структуры и связку клиника × услуга × цена.
"""
import httpx
import pytest

from app.ingestion import doq_connector as d
from app.ingestion.file_parser import RawItem


# --- зафиксированные фрагменты реальных ответов api.doq.kz/api/v1/ --------- #
FIXTURES = {
    "cities/": {
        "count": 2,
        "next": None,
        "results": [
            {"id": 3, "name": "Алматы", "slug": "almaty",
             "location": {"lat": 43.238293, "lng": 76.945465}},
            {"id": 1, "name": "Астана", "slug": "astana",
             "location": {"lat": 51.128207, "lng": 71.430411}},
        ],
    },
    "clinics/": {
        "count": 1,
        "next": None,
        "results": [
            {"id": 105, "name": "ЭМИРМЕД", "slug": "emirmed",
             "feedback_score": 9.075, "about_short": "Сеть клиник"},
        ],
    },
    "clinic-branches/": {
        "count": 1,
        "next": None,
        "results": [
            {"id": 1158, "clinic": 105, "city": 3,
             "name": "ЭМИРМЕД на Рыскулова",
             "address": "пр. Турара Рыскулова, 143В",
             "phones": ["+77070000103", "+77273551111"],
             "location": {"lat": 43.253389, "lng": 76.839043}},
        ],
    },
    "services/": {
        "count": 2,
        "next": None,
        "results": [
            {"id": 829, "name": "3D УЗИ плода", "slug": "3d-uzi-ploda",
             "type": "procedure"},
            {"id": 736, "name": "Анестезиолог-walk-in", "slug": "x",
             "type": "procedure"},
        ],
    },
    # doctors-meta зависит от service — ключуем по сервису ниже
    "doctors-meta/829": {"count": 3, "currency": "Тенге",
                         "min_price": 14000.0, "max_price": 16000.0},
    "doctors-meta/736": {"count": 1, "currency": "Тенге",
                         "min_price": None, "max_price": None},
}


def _fake_json_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json=data, request=httpx.Request("GET", "http://t"))


@pytest.fixture(autouse=True)
def _stub_network(monkeypatch):
    """Подменяем polite_get: маршрутизируем по пути/параметрам на фикстуры."""
    def fake_get(url, **kwargs):
        if "cities/" in url:
            return _fake_json_response(FIXTURES["cities/"])
        if "clinic-branches/" in url:
            return _fake_json_response(FIXTURES["clinic-branches/"])
        if "clinics/" in url:
            return _fake_json_response(FIXTURES["clinics/"])
        if "doctors-meta/" in url:
            key = "doctors-meta/829" if "service=829" in url else "doctors-meta/736"
            return _fake_json_response(FIXTURES[key])
        if "services/" in url:
            return _fake_json_response(FIXTURES["services/"])
        raise AssertionError(f"неожиданный URL в тесте: {url}")

    monkeypatch.setattr(d, "polite_get", fake_get)


def test_fetch_cities_parses_location():
    cities = d.fetch_cities()
    assert len(cities) == 2
    almaty = next(c for c in cities if c["slug"] == "almaty")
    assert almaty == {"id": 3, "name": "Алматы", "slug": "almaty",
                      "lat": 43.238293, "lng": 76.945465}


def test_parse_clinic_joins_branch_and_city():
    city = {"id": 3, "name": "Алматы", "slug": "almaty"}
    branch = FIXTURES["clinic-branches/"]["results"][0]
    row = FIXTURES["clinics/"]["results"][0]
    clinic = d.parse_clinic(row, branch, city)
    assert clinic["name"] == "ЭМИРМЕД"
    assert clinic["city"] == "Алматы"
    assert clinic["city_id"] == 3
    assert clinic["address"].startswith("пр. Турара")
    assert clinic["phone"] == "+77070000103"
    assert clinic["lat"] == 43.253389
    assert clinic["rating"] == 9.075
    assert clinic["source_url"] == "https://doq.kz/almaty/clinic/emirmed"


def test_fetch_clinics_by_city():
    clinics = d.fetch_clinics(city_slug="almaty")
    assert len(clinics) == 1
    assert clinics[0]["id"] == 105
    assert clinics[0]["phone"] == "+77070000103"


def test_fetch_prices_links_service_and_price():
    clinic = {"id": 105, "city_id": 3, "name": "ЭМИРМЕД"}
    items = d.fetch_prices(clinic)
    # услуга без цены (min_price=null, walk-in) отброшена → остаётся одна
    assert len(items) == 1
    it = items[0]
    assert isinstance(it, RawItem)
    assert it.raw_name == "3D УЗИ плода"
    assert it.price == 14000.0
    assert it.currency == "KZT"


def test_fetch_all_shape():
    data = d.fetch_all(max_clinics=5, city_slug="almaty")
    assert len(data) == 1
    entry = data[0]
    assert entry["clinic"]["name"] == "ЭМИРМЕД"
    assert all(isinstance(x, RawItem) for x in entry["items"])
    assert entry["items"][0].price == 14000.0
