"""Тесты чат-помощника: детерминированный фолбэк-путь (без сети/LLM)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app import models  # noqa: F401
from app.models import Clinic, Price, ServiceCatalog
from app.routers.chat import ChatMessage, _fallback, _rank_services


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    oak = ServiceCatalog(canonical_name="Общий анализ крови", category="Анализы",
                         synonyms=["ОАК", "Анализ крови общий"])
    oam = ServiceCatalog(canonical_name="Общий анализ мочи", category="Анализы",
                         synonyms=["ОАМ"])
    uzi = ServiceCatalog(canonical_name="УЗИ брюшной полости", category="УЗИ",
                         synonyms=["УЗИ ОБП"])
    s.add_all([oak, oam, uzi])
    s.flush()
    c1 = Clinic(name="Клиника А", city="Алматы", district="Бостандык", phone="+7 700 111")
    c2 = Clinic(name="Клиника Б", city="Алматы", district="Алмалы", phone="+7 700 222")
    c3 = Clinic(name="Клиника К", city="Караганда", district="", phone="+7 700 333")
    s.add_all([c1, c2, c3])
    s.flush()
    s.add_all([
        Price(clinic_id=c1.id, service_id=oak.id, raw_name="ОАК", price=2500, currency="KZT", source_type="upload"),
        Price(clinic_id=c2.id, service_id=oak.id, raw_name="Общий анализ крови", price=1900, currency="KZT", source_type="upload"),
        Price(clinic_id=c3.id, service_id=oak.id, raw_name="ОАК", price=2100, currency="KZT", source_type="upload"),
        # в Караганде ОАМ дешевле, чем ОАК — ловушка на «смешивание услуг»
        Price(clinic_id=c3.id, service_id=oam.id, raw_name="ОАМ", price=900, currency="KZT", source_type="upload"),
        Price(clinic_id=c1.id, service_id=uzi.id, raw_name="УЗИ ОБП", price=8000, currency="KZT", source_type="upload"),
    ])
    s.commit()
    yield s
    s.close()


def test_rank_finds_service_by_synonym(db):
    found = _rank_services(db, "оак")
    assert found and found[0].canonical_name == "Общий анализ крови"


def test_rank_fuzzy_typo(db):
    found = _rank_services(db, "узи брюшной")
    assert any(s.canonical_name == "УЗИ брюшной полости" for s in found)


def test_fallback_returns_cheapest_first(db):
    resp = _fallback(db, [ChatMessage(role="user", content="сколько стоит общий анализ крови")])
    assert resp.grounded and not resp.llm
    assert "1900" in resp.reply  # самая дешёвая цена попала в сводку
    cheapest = [o for o in resp.offers if o.is_cheapest]
    assert cheapest and cheapest[0].price == 1900 and cheapest[0].clinic_name == "Клиника Б"


def test_fallback_no_match_is_honest(db):
    resp = _fallback(db, [ChatMessage(role="user", content="пересадка сердца на Марсе")])
    assert not resp.grounded and resp.offers == []
    assert "не нашёл" in resp.reply.lower()


def test_detect_city(db):
    from app.routers.chat import _detect_city
    assert _detect_city(db, "сколько стоит ОАК в Алматы?") == "Алматы"
    assert _detect_city(db, "просто общий анализ крови") is None


def test_detect_city_declension(db):
    """Город в косвенном падеже: «в Караганде» → «Караганда» (был баг)."""
    from app.routers.chat import _detect_city
    assert _detect_city(db, "где дешевле общий анализ крови в Караганде?") == "Караганда"
    assert _detect_city(db, "цены в караганде") == "Караганда"


def test_explicit_service_not_blended(db):
    """Явный «общий анализ крови» не должен подмешивать «общий анализ мочи»."""
    found = _rank_services(db, "где дешевле общий анализ крови")
    names = {s.canonical_name for s in found}
    assert names == {"Общий анализ крови"}


def test_search_offers_single_cheapest_and_city_filter(db):
    """В Караганде по ОАК ровно одна 🏆 и нет чужих городов/услуг (ОАМ за 900)."""
    from app.routers.chat import _search_offers
    offers, _ = _search_offers(db, "общий анализ крови", city="Караганда")
    assert offers, "ожидались предложения по Караганде"
    assert all(o.city == "Караганда" for o in offers)
    assert all(o.service == "Общий анализ крови" for o in offers)
    assert sum(1 for o in offers if o.is_cheapest) == 1


def test_chat_provider_selection():
    from app.config import Settings
    # _env_file=None — игнорируем локальный .env, проверяем чистую логику
    def S(**kw):
        return Settings(_env_file=None, **kw)
    # auto: alem при наличии ключа, иначе groq
    assert S(alem_api_key="x").chat_provider == "alem"
    assert S(alem_api_key="").chat_provider == "groq"
    # явный выбор уважается
    assert S(llm_provider="groq", alem_api_key="x").chat_provider == "groq"
    assert S(llm_provider="alem").chat_provider == "alem"
