"""Тесты нормализации, дедупликации и сквозного конвейера (без сети/LLM)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app import models  # noqa: F401
from app.models import Clinic, Price, ServiceCatalog
from app.ingestion.file_parser import RawItem
from app.ingestion.normalizer import Normalizer
from app.ingestion.service import ingest_items


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add_all([
        ServiceCatalog(canonical_name="Общий анализ крови", category="Анализы",
                       synonyms=["ОАК", "Анализ крови общий"]),
        ServiceCatalog(canonical_name="Приём терапевта", category="Приём врача",
                       synonyms=["Консультация терапевта"]),
    ])
    s.commit()
    yield s
    s.close()


def test_fuzzy_matches_variants(db):
    n = Normalizer(db)
    # разные написания одной услуги должны указать на одну запись справочника
    r1 = n.normalize("ОАК")
    r2 = n.normalize("Общий анализ крови (5 параметров)")
    r3 = n.normalize("Анализ крови — общий")
    assert r1.service.id == r2.service.id == r3.service.id
    assert r1.confidence > 0.7


def test_new_service_created(db):
    n = Normalizer(db)
    before = db.query(ServiceCatalog).count()
    r = n.normalize("Пломбирование зуба световой пломбой")
    assert r.is_new
    assert db.query(ServiceCatalog).count() == before + 1


def test_dedup_priority_upload_beats_scrape(db):
    clinic = Clinic(name="Тест", city="Алматы")
    db.add(clinic)
    db.commit()

    # сначала автосбор с сайта (дешевле)
    ingest_items(db, clinic_id=clinic.id, channel="pull", source_type="web_scrape",
                 items=[RawItem("ОАК", 2000.0)], fmt="html")
    # затем официальная загрузка клиники (дороже) — должна победить
    ingest_items(db, clinic_id=clinic.id, channel="push", source_type="upload",
                 items=[RawItem("Общий анализ крови", 2500.0)], fmt="xlsx")

    prices = db.query(Price).filter(Price.clinic_id == clinic.id).all()
    assert len(prices) == 1  # дедуп: одна услуга — одна цена
    assert float(prices[0].price) == 2500.0
    assert prices[0].source_type == "upload"


def test_scrape_does_not_override_upload(db):
    clinic = Clinic(name="Тест2", city="Алматы")
    db.add(clinic)
    db.commit()
    ingest_items(db, clinic_id=clinic.id, channel="push", source_type="upload",
                 items=[RawItem("Общий анализ крови", 2500.0)], fmt="xlsx")
    ingest_items(db, clinic_id=clinic.id, channel="pull", source_type="web_scrape",
                 items=[RawItem("ОАК", 1900.0)], fmt="html")
    prices = db.query(Price).filter(Price.clinic_id == clinic.id).all()
    assert len(prices) == 1
    assert float(prices[0].price) == 2500.0  # upload не перезаписан парсером


# --- Парсер CSV: устойчивость к разделителю ---
from app.ingestion.file_parser import parse_csv  # noqa: E402


def test_csv_semicolon_with_commas_in_text():
    """Разделитель ';' + запятые внутри текста (шапка/название) не теряют строки."""
    csv = (
        "Наименование услуги;Тариф, тенге\n"
        "Общий анализ крови (расширенный);3 200,00 ₸\n"
        "Приём терапевта, первичный;7000\n"
        "ЭКГ с расшифровкой;4 500 тг\n"
    ).encode()
    items = parse_csv(csv)
    names = {i.raw_name for i in items}
    assert "Приём терапевта, первичный" in names  # строка с запятой в имени не выпала
    assert len(items) == 3
    assert {i.price for i in items} == {3200.0, 7000.0, 4500.0}


def test_csv_plain_comma_not_merged():
    """Чистый comma-CSV: имя и цена не слипаются в одну колонку."""
    items = parse_csv(b"name,price\n\xd0\x9e\xd0\x90\xd0\x9a,2200\n")
    assert len(items) == 1
    assert items[0].raw_name == "ОАК" and items[0].price == 2200.0
