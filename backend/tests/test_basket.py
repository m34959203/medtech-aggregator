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


def test_garbage_not_recognized_as_real_analysis(client):
    """Мусорный ввод («HemoglobinX», «Test 123») НЕ должен ложно распознаваться
    реальным анализом — честное «не распознано» (порог рецепта 0.72/0.85)."""
    r = client.post("/api/basket/recommend",
                    json={"names": ["HemoglobinX", "Test 123", "xyz123 random", "asdfgh"]}).json()
    assert r["services_found"] == 0
    assert r["recognized"] == []
    # реальный анализ рядом с мусором всё ещё ловится
    r2 = client.post("/api/basket/recommend", json={"names": ["HemoglobinX", "ОАК"]}).json()
    found = {it["canonical"] for it in r2["recognized"]}
    assert found == {"Общий анализ крови"}


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


def test_chat_vision_ocr_referral(client, monkeypatch):
    """OCR в чате: фото направления → распознавание услуг → ответ по витрине.
    OCR мокаем (tesseract в тестах не нужен) — проверяем логику распознавания+поиска."""
    monkeypatch.setattr(
        "app.routers.chat._extract_text_any",
        lambda fn, content: "Направление\nОбщий анализ крови\nГлюкоза\nТТГ",
    )
    r = client.post(
        "/api/chat/vision",
        files={"file": ("napravlenie.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        data={"city": "Алматы"},
    )
    assert r.status_code == 200
    d = r.json()
    # распознаны и нормализованы 3 услуги справочника
    assert set(d["recognized"]) == {"Общий анализ крови", "Глюкоза (в крови)", "ТТГ (тиреотропный гормон)"}
    assert d["grounded"] is True and len(d["offers"]) > 0
    # цена в ответе без enum-репра «Currency.KZT»
    assert "Currency." not in d["reply"]


def test_chat_vision_unreadable_image(client, monkeypatch):
    """Нечитаемое фото (OCR пусто) → 200 с понятным сообщением, не падение."""
    monkeypatch.setattr("app.routers.chat._extract_text_any", lambda fn, content: "")
    r = client.post("/api/chat/vision", files={"file": ("x.png", b"\x89PNG\r\n\x1a\n", "image/png")})
    assert r.status_code == 200
    assert r.json()["recognized"] == [] and r.json()["grounded"] is False


def test_extract_drops_referral_header(client):
    """«Направление на анализы», ФИО, дата, нумерация — не услуги (баг боевого
    прогона: «Направление на анализы:» ловилось в «Анализ пота»)."""
    from app.routers.basket import extract_service_names
    out = extract_service_names(
        "Направление на анализы:\n1. Общий анализ крови\n2. Глюкоза\nФИО: Иванов И.\n12.06.2026"
    )
    assert out == ["Общий анализ крови", "Глюкоза"]


def test_extract_splits_inline_list(client):
    """Единый парсер списков: перечисление в одной строке (запятая/«+»/«/»)
    дробится на отдельные услуги — чтобы чат-OCR и /recipe не расходились
    (баг боевого отчёта: чат дробил «ОАК, ОАМ», /recipe — нет)."""
    from app.routers.basket import extract_service_names
    assert extract_service_names("ОАК, ОАМ") == ["ОАК", "ОАМ"]
    assert extract_service_names("АЛТ/АСТ") == ["АЛТ", "АСТ"]
    assert extract_service_names("глюкоза + холестерин") == ["глюкоза", "холестерин"]
    # многострочный + перечисления вместе
    assert extract_service_names("Общий анализ крови\nТТГ, Витамин D") == [
        "Общий анализ крови", "ТТГ", "Витамин D",
    ]


def test_recommend_by_service_ids(client):
    """CTA «Собрать корзину»: /recipe шлёт точные service_id — корзина строится
    напрямую, без повторного фаззи-матча по имени."""
    from app.models import ServiceCatalog
    # достаём реальные uuid услуг из in-memory БД через сам же эндпоинт
    ids = []
    for nm in ("ОАК", "Глюкоза"):
        rr = client.post("/api/basket/recommend", json={"names": [nm]}).json()
        ids.append(rr["recognized"][0]["service_id"])
    r = client.post("/api/basket/recommend",
                    json={"service_ids": ids, "city": "Алматы"}).json()
    assert r["services_found"] == 2
    assert {it["canonical"] for it in r["recognized"]} == {
        "Общий анализ крови", "Глюкоза (в крови)"}


def test_chat_rank_plain_analyte_prefers_blood():
    """«Глюкоза» в чате не должна тянуть мочевой вариант (дефолт=кровь)."""
    from app.routers.chat import _rank_services
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    s.add_all([
        ServiceCatalog(canonical_name="Глюкоза (в крови)", category="Анализы", synonyms=["глюкоза"]),
        ServiceCatalog(canonical_name="Глюкоза в моче", category="Анализы", synonyms=["глюкоза мочи"]),
    ])
    s.commit()
    names = [svc.canonical_name for svc in _rank_services(s, "Глюкоза", 3)]
    assert "Глюкоза (в крови)" in names
    assert "Глюкоза в моче" not in names  # мочевой вариант отсечён биоматериал-гардом
    s.close()
