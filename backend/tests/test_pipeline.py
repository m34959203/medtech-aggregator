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


# --- Веб-скрапер: таблица с № строки и адаптер 103.kz ---
from app.ingestion.web_scraper import scrape_html, _103kz  # noqa: E402


def test_table_skips_row_number_picks_real_price():
    """Таблица '№ | услуга | цена': имя — текстовая ячейка, цена — макс. число."""
    html = """<table>
      <tr><td>14.</td><td>УЗИ органов брюшной полости</td><td>8 000 тенге</td></tr>
      <tr><td>16.</td><td>УЗИ почек</td><td>6 000 тенге</td></tr>
    </table>"""
    items = {i.raw_name: i.price for i in scrape_html(html)}
    assert items == {"УЗИ органов брюшной полости": 8000.0, "УЗИ почек": 6000.0}


def test_103kz_adapter_variant_b_skips_unspecified():
    """Адаптер 103.kz (вариант B): тянет имя+цену, пропускает 'уточняйте'."""
    html = """
    <div class="PersonalOffers__item">
      <div class="PersonalOffers__title">Первичный приём терапевта</div>
      <span class="PersonalOffers__price">от 6 000 тенге</span>
    </div>
    <div class="PersonalOffers__item">
      <div class="PersonalOffers__title">Приём кардиолога</div>
      <span class="PersonalOffers__price">уточняйте</span>
    </div>"""
    items = _103kz(html)
    assert len(items) == 1
    assert items[0].raw_name == "Первичный приём терапевта" and items[0].price == 6000.0


# --- Детерминированная классификация прайсов (load_real_data._classify) ---
import os, sys  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load_real_data import _classify  # noqa: E402


def test_classify_oak_variants_to_one_canonical():
    assert _classify("Клинический анализ крови (с лейкоцитарной формулой)")[0] == "Общий анализ крови"
    assert _classify("Анализ крови. Общий анализ крови (без СОЭ)")[0] == "Общий анализ крови"


def test_classify_priem_only_consultation_not_procedure():
    # консультация → приём; операция/мазок у того же специалиста → НЕ приём
    assert _classify("Первичный приём врача-гинеколога")[0] == "Приём гинеколога"
    assert _classify("Биопсия шейки матки у гинеколога") is None
    assert _classify("Удаление кисты (гинекология)") is None


def test_classify_analyte_excludes_panels_and_false_matches():
    assert _classify("Ферритин") == ("Ферритин", "Анализы")
    assert _classify("Анемия воспаления (ОАК, СРБ, Ферритин, В12)") is None  # панель
    assert _classify("Индекс HOMA-IR (Инсулин + Глюкоза)") is None           # не глюкоза
    assert _classify("Глюкоза (сахар крови)")[0] == "Глюкоза (в крови)"


def test_classify_echo_before_ecg():
    assert _classify("УЗИ сердца с ЭКГ")[0] == "ЭхоКГ (эхокардиография)"
    assert _classify("ЭКГ с расшифровкой")[0] == "ЭКГ"
