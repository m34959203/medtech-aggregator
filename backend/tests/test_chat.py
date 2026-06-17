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
    uzi = ServiceCatalog(canonical_name="УЗИ брюшной полости", category="УЗИ",
                         synonyms=["УЗИ ОБП"])
    s.add_all([oak, uzi])
    s.flush()
    c1 = Clinic(name="Клиника А", city="Алматы", district="Бостандык", phone="+7 700 111")
    c2 = Clinic(name="Клиника Б", city="Алматы", district="Алмалы", phone="+7 700 222")
    s.add_all([c1, c2])
    s.flush()
    s.add_all([
        Price(clinic_id=c1.id, service_id=oak.id, raw_name="ОАК", price=2500, currency="KZT", source_type="upload"),
        Price(clinic_id=c2.id, service_id=oak.id, raw_name="Общий анализ крови", price=1900, currency="KZT", source_type="upload"),
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
