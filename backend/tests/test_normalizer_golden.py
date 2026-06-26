"""Golden-набор из боевого прогона направления (отчёт 27.06.2026).

Проверяет: входной gate (шум), порог отказа (нет ложных 100%/принудительной
привязки), guard кровь/моча, декомпозицию панелей, санитайзер синонимов.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app import models  # noqa: F401
from app.models import ServiceCatalog
from app.ingestion.normalizer import Normalizer, sanitize_synonyms, _prefer_blood


@pytest.fixture
def db():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    cat = [
        ServiceCatalog(canonical_name="Общий анализ крови", category="Анализы", synonyms=["ОАК", "CBC"]),
        ServiceCatalog(canonical_name="Общий анализ мочи", category="Анализы", synonyms=["ОАМ"]),
        ServiceCatalog(canonical_name="Глюкоза (в крови)", category="Анализы", synonyms=["глюкоза", "glucose"]),
        ServiceCatalog(canonical_name="Гликированный гемоглобин (HbA1c)", category="Анализы", synonyms=["hba1c"]),
        ServiceCatalog(canonical_name="ТТГ (тиреотропный гормон)", category="Анализы", synonyms=["ттг", "tsh"]),
        # ЗАГРЯЗНЕНИЕ: «Ферритин» ошибочно в синонимах Витамина D
        ServiceCatalog(canonical_name="Витамин D", category="Анализы", synonyms=["25-он-d3", "Ферритин"]),
        ServiceCatalog(canonical_name="HBsAg", category="Анализы", synonyms=[]),
        ServiceCatalog(canonical_name="Ферритин", category="Анализы", synonyms=["феретин"]),
        # ЗАГРЯЗНЕНИЕ: «Ферритин» (кровяной) в синонимах мочевого варианта
        ServiceCatalog(canonical_name="Ферритин в моче", category="Анализы", synonyms=["Ферритин"]),
        # ЗАГРЯЗНЕНИЕ: «АЛТ» ошибочно в синонимах кальция (есть отдельная услуга АЛТ)
        ServiceCatalog(canonical_name="Са+ (кальций ионизированный)", category="Анализы", synonyms=["АЛТ"]),
        ServiceCatalog(canonical_name="АЛТ", category="Анализы", synonyms=["аланинаминотрансфераза"]),
    ]
    s.add_all(cat)
    s.commit()
    yield s
    s.close()


def _first(norm, line):
    r = norm.analyze(line)
    return r


def test_sanitize_removes_polluted_synonyms(db):
    removed = sanitize_synonyms(db)
    assert removed >= 3
    vitd = db.query(ServiceCatalog).filter_by(canonical_name="Витамин D").first()
    ca = db.query(ServiceCatalog).filter_by(canonical_name="Са+ (кальций ионизированный)").first()
    urine = db.query(ServiceCatalog).filter_by(canonical_name="Ферритин в моче").first()
    assert "Ферритин" not in (vitd.synonyms or [])
    assert "АЛТ" not in (ca.synonyms or [])
    assert "Ферритин" not in (urine.synonyms or [])
    # легитимная аббревиатура НЕ удалена
    cbc = db.query(ServiceCatalog).filter_by(canonical_name="Общий анализ крови").first()
    assert "ОАК" in (cbc.synonyms or [])


def test_prefer_blood_helper():
    assert _prefer_blood("Ферритин", "Ферритин в моче") == "Ферритин"
    assert _prefer_blood("Ферритин в моче", "Ферритин в моче") is None  # сырое про мочу
    assert _prefer_blood("Глюкоза", "Глюкоза (в крови)") is None       # матч не мочевой


NOISE = [
    "НАПРАВЛЕНИЕ НА ЛАБОРАТОРНЫЕ ИССЛЕДОВАНИЯ",
    "Пациент: Тестовый пациент",
    "Дата: 27.06.2026",
    "Сдать утром натощак, результаты предоставить врачу.",
]


@pytest.mark.parametrize("line", NOISE)
def test_noise_filtered(db, line):
    r = Normalizer(db).analyze(line)
    assert r["kind"] == "noise", f"{line} -> {r}"
    assert r["items"] == []


MATCHED = [
    ("ОАК развернутый + лейкоцитарная формула + СОЭ", "Общий анализ крови"),
    ("Общий анализ крови (CBC, 5 diff)", "Общий анализ крови"),
    ("ОАМ / общий ан. мочи", "Общий анализ мочи"),
    ("Glucose fasting — глюкоза крови натощак", "Глюкоза (в крови)"),
    ("HbA1c (гликированный гемоглобин)", "Гликированный гемоглобин (HbA1c)"),
    ("ТТГ / TSH", "ТТГ (тиреотропный гормон)"),
    ("HBsAg", "HBsAg"),
]


@pytest.mark.parametrize("line,expected", MATCHED)
def test_matched_not_broken(db, line, expected):
    sanitize_synonyms(db)
    r = Normalizer(db).analyze(line)
    assert r["kind"] == "service"
    assert len(r["items"]) == 1
    it = r["items"][0]
    assert it["status"] == "matched" and it["canonical"] == expected, f"{line} -> {it}"


def test_ferritin_prefers_blood(db):
    sanitize_synonyms(db)
    it = Normalizer(db).analyze("Ферритин (феретин)")["items"][0]
    assert it["status"] == "matched"
    assert it["canonical"] == "Ферритин"  # НЕ «Ферритин в моче»


def test_alt_not_forced_to_calcium(db):
    sanitize_synonyms(db)
    it = Normalizer(db).analyze("АЛТ (ALT)")["items"][0]
    # после точечной чистки «АЛТ» убран из синонимов кальция (это имя ДРУГОЙ услуги) →
    # матчится на настоящую услугу «АЛТ», НЕ на «Са+»
    assert it["canonical"] != "Са+ (кальций ионизированный)"
    assert it["canonical"] == "АЛТ" and it["status"] == "matched"


PANELS = [
    ("Билирубин общий + прямой + непрямой",
     ["Билирубин общий", "Билирубин прямой", "Билирубин непрямой"]),
    ("Липидограмма: общий холестерин, ЛПНП, ЛПВП, триглицериды",
     ["Холестерин общий", "ЛПНП", "ЛПВП", "Триглицериды"]),
    ("Коагулограмма: ПТИ, МНО (INR), АЧТВ, фибриноген",
     ["ПТИ", "МНО", "АЧТВ", "Фибриноген"]),
]


@pytest.mark.parametrize("line,expected", PANELS)
def test_panels_decomposed(db, line, expected):
    r = Normalizer(db).analyze(line)
    assert r["kind"] == "service"
    assert [it["canonical"] for it in r["items"]] == expected, f"{line} -> {r['items']}"
