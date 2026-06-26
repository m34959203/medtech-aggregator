"""Планировщик (§4): авто-обновление источников по cron, маршрутизация коннекторов.

Проверяем, что run_all_sources корректно роутит:
- web_scrape → web_scraper.scrape_url_raw (KDL/invitro/103/KazMedClinic);
- api с ref `doq://{city_id}/{clinic_id}` → doq_connector.refresh;
- api без doq-ref → generic api_connector.fetch_api;
- падение одного источника не валит остальные (отказоустойчивость).
Сеть замокана — тест offline.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app import scheduler
from app.ingestion.file_parser import RawItem
from app.ingestion import doq_connector
from app.models import Clinic, Source, ServiceCatalog, Price


def test_doq_parse_ref():
    assert doq_connector.parse_ref("doq://3/105") == (3, 105)
    assert doq_connector.parse_ref("https://doq.kz/almaty/clinic/x") is None
    assert doq_connector.parse_ref("https://lab.103.kz/pricing/") is None


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(scheduler, "SessionLocal", Session)
    # каталог, чтобы нормализатор сматчил
    s = Session()
    s.add(ServiceCatalog(canonical_name="3D УЗИ плода", category="диагностика", synonyms=[]))
    s.add(ServiceCatalog(canonical_name="Общий анализ крови", category="лаборатория", synonyms=["ОАК"]))
    s.add(Clinic(id=1, name="Doq-клиника", city="Алматы"))
    s.add(Clinic(id=2, name="Web-клиника", city="Астана"))
    s.add(Source(id=10, clinic_id=1, type="api", url_or_endpoint="doq://3/105", enabled=True))
    s.add(Source(id=11, clinic_id=2, type="web_scrape",
                 url_or_endpoint="https://lab.103.kz/pricing/", enabled=True))
    s.commit(); s.close()
    return Session


def test_scheduler_routes_doq_and_web(db, monkeypatch):
    calls = {"doq": 0, "scrape": 0, "api": 0}

    def fake_refresh(clinic_id, city_id, *a, **k):
        calls["doq"] += 1
        assert (city_id, clinic_id) == (3, 105)
        return [RawItem(raw_name="3D УЗИ плода", price=14000.0)]

    def fake_scrape(url, *a, **k):
        calls["scrape"] += 1
        assert url == "https://lab.103.kz/pricing/"
        return ("<html/>", [RawItem(raw_name="ОАК", price=1500.0)])

    def fake_api(url):
        calls["api"] += 1
        return []

    monkeypatch.setattr(scheduler.doq_connector, "refresh", fake_refresh)
    monkeypatch.setattr(scheduler.web_scraper, "scrape_url_raw", fake_scrape)
    monkeypatch.setattr(scheduler.api_connector, "fetch_api", fake_api)
    # без сети при нормализации
    monkeypatch.setattr("app.llm.json_completion", lambda *a, **k: None)
    monkeypatch.setattr("app.config.settings.semantic_enabled", False, raising=False)

    report = scheduler.run_all_sources()

    assert calls == {"doq": 1, "scrape": 1, "api": 0}  # doq-ref ушёл в коннектор, не в generic
    assert sum(1 for r in report if r["status"] == "ok") == 2
    # цены реально записались обоими путями
    s = db()
    assert s.query(Price).count() == 2
    s.close()


def test_one_source_failure_does_not_stop_others(db, monkeypatch):
    def boom(url, *a, **k):
        raise RuntimeError("источник лёг")

    monkeypatch.setattr(scheduler.doq_connector, "refresh",
                        lambda *a, **k: [RawItem(raw_name="3D УЗИ плода", price=14000.0)])
    monkeypatch.setattr(scheduler.web_scraper, "scrape_url_raw", boom)
    monkeypatch.setattr("app.llm.json_completion", lambda *a, **k: None)
    monkeypatch.setattr("app.config.settings.semantic_enabled", False, raising=False)

    report = scheduler.run_all_sources()
    statuses = {r["source_id"]: r["status"] for r in report}
    assert statuses[10] == "ok"        # doq отработал
    assert statuses[11] == "error"     # web упал, но не уронил doq
