"""Решение «малых городов»: city-diversity харвест общего пула 103.kz (офлайн)."""
from sqlalchemy import create_engine, distinct
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app import models  # noqa: F401
from app.models import Clinic


def _db():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def test_harvest_one_splits_pricing_and_geo(monkeypatch):
    """fetch_pricing — 1 запрос (город+позиции), geo — отдельно, только при взятии."""
    from app.ingestion import o103_harvester as o103
    from app.ingestion.file_parser import RawItem

    calls = {"pricing": 0, "geo": 0}

    def fake_pricing(slug):
        calls["pricing"] += 1
        return {"slug": slug, "base": f"https://{slug}.103.kz",
                "source_url": f"https://{slug}.103.kz/pricing/", "name": slug.title(),
                "city": "Жезказган", "address": None, "phone": "", "items": [RawItem("ОАК", 2000)]}

    def fake_geo(rec):
        calls["geo"] += 1
        rec["lat"], rec["lng"] = 47.8, 67.7
        return rec

    monkeypatch.setattr(o103, "fetch_pricing", fake_pricing)
    monkeypatch.setattr(o103, "enrich_geo", fake_geo)
    block = o103.harvest_one("rahat")
    assert block["clinic"]["city"] == "Жезказган"
    assert block["clinic"]["lat"] == 47.8
    assert calls == {"pricing": 1, "geo": 1}


def test_chain_branch_filter_matches_networks():
    """Фильтр филиалов: берём invitro/olimp/gemotest-N, отсекаем независимые."""
    from app.ingestion import o103_harvester as o103
    keep = ["invitro-12", "olimp-70", "gemotest-5", "kdl-olimp-balkhash-227", "helix-3"]
    drop = ["healthcity", "my-clinic", "dostar-med-1", "smart-health"]
    assert all(o103.CHAIN_SLUG_RE.match(s) for s in keep)
    assert not any(o103.CHAIN_SLUG_RE.match(s) for s in drop)


def test_seed_chains_covers_small_cities_with_per_city_cap(monkeypatch):
    """Филиалы сетей раскидываются по городам из карточек; кэп на город держит
    ширину — малые города попадают в базу наравне с крупными."""
    from app import seed_real
    from app.ingestion import o103_harvester as o103
    from app.ingestion.file_parser import RawItem

    # филиалы: 4 алматинских + по одному в малых городах
    branches = ["invitro-1", "olimp-2", "gemotest-3", "invitro-4", "olimp-70", "invitro16", "kdl-kentau"]
    city_of = {"invitro-1": "Алматы", "olimp-2": "Алматы", "gemotest-3": "Алматы",
               "invitro-4": "almaty", "olimp-70": "Жезказган", "invitro16": "Балхаш",
               "kdl-kentau": "Кентау"}

    monkeypatch.setattr(o103, "discover_chain_branches", lambda limit=500: branches)
    monkeypatch.setattr(o103, "fetch_pricing", lambda slug: {
        "slug": slug, "base": f"https://{slug}.103.kz",
        "source_url": f"https://{slug}.103.kz/pricing/", "name": slug,
        "city": city_of[slug], "address": None, "phone": "", "items": [RawItem("ОАК", 2500)]})
    monkeypatch.setattr(o103, "enrich_geo", lambda rec: rec)
    monkeypatch.setattr(seed_real, "O103_CHAIN_PER_CITY", 3)

    db = _db()
    report: list[dict] = []
    seed_real.seed_103_chains(db, report)

    cities = {c for (c,) in db.query(distinct(Clinic.city)).all() if c}
    # малые города покрыты
    assert {"Жезказган", "Балхаш", "Кентау"} <= cities
    # Алматы (4 кандидата, в т.ч. вариант «almaty») схлопнут кэпом до 3
    assert db.query(Clinic).filter(Clinic.city == "Алматы").count() == 3
    summary = [r for r in report if r.get("status") == "summary"][0]
    assert "городов" in summary["city"]
