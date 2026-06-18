"""Семантическая нормализация (in-process): смысл, а не буквы. Gated моделью."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base
from app import models  # noqa: F401
from app.ingestion import semantic
from app.ingestion.normalizer import Normalizer
from app.models import ServiceCatalog


@pytest.fixture
def db(monkeypatch):
    # включаем семантику и проверяем, что модель грузится (иначе skip)
    monkeypatch.setattr(settings, "semantic_enabled", True)
    semantic.reset_memory()
    try:
        semantic.embed(["проверка"])
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"модель эмбеддингов недоступна: {type(e).__name__}")

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add_all([
        ServiceCatalog(canonical_name="Общий анализ крови", category="Анализы", synonyms=["ОАК"]),
        ServiceCatalog(canonical_name="Глюкоза (в крови)", category="Анализы", synonyms=["глюкоза"]),
        ServiceCatalog(canonical_name="УЗИ почек", category="УЗИ", synonyms=["узи почек"]),
        ServiceCatalog(canonical_name="Приём кардиолога", category="Приём врача", synonyms=[]),
    ])
    s.commit()
    yield s
    s.close()


def _canon(db, sid):
    return db.get(ServiceCatalog, sid).canonical_name


def test_semantic_matches_meaning(db):
    sid, score = semantic.match(db, "кровь на сахар")
    assert _canon(db, sid) == "Глюкоза (в крови)" and score >= settings.semantic_threshold
    sid2, _ = semantic.match(db, "ультразвуковое исследование почек")
    assert _canon(db, sid2) == "УЗИ почек"


def test_normalizer_semantic_tier(db):
    # fuzzy не ловит (нет буквального совпадения с эталоном) — ловит семантика
    n = Normalizer(db)
    res = n.normalize("уровень сахара натощак")
    assert res.service.canonical_name == "Глюкоза (в крови)"


def test_match_used_by_basket_path(db):
    n = Normalizer(db)
    svc, score = n.match("ультразвук почек")
    assert svc and svc.canonical_name == "УЗИ почек"
