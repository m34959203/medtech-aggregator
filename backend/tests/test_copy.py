"""Перенос данных между БД (copy_to_pg.copy) — проверка на sqlite→sqlite."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import Base  # noqa: E402
from app.models import Clinic, Price, ServiceCatalog  # noqa: E402
from copy_to_pg import copy  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


def test_copy_sqlite_to_sqlite(tmp_path):
    src_url = f"sqlite:///{tmp_path/'src.db'}"
    dst_url = f"sqlite:///{tmp_path/'dst.db'}"
    se = create_engine(src_url)
    de = create_engine(dst_url)
    Base.metadata.create_all(se)
    Base.metadata.create_all(de)  # целевая схема создана заранее (как миграциями)

    S = sessionmaker(bind=se)
    s = S()
    c = Clinic(name="A", city="Алматы", access_token="tok")
    sc = ServiceCatalog(canonical_name="ОАК", category="Анализы", synonyms=["ОАК"])
    s.add_all([c, sc]); s.flush()
    s.add(Price(clinic_id=c.id, service_id=sc.id, source_type="web_scrape",
                raw_name="ОАК", price=2000, currency="KZT", match_confidence=0.9))
    s.commit(); s.close()

    counts = copy(src_url, dst_url)
    assert counts["clinics"] == 1 and counts["service_catalog"] == 1 and counts["prices"] == 1

    D = sessionmaker(bind=de)
    d = D()
    assert d.query(Clinic).count() == 1
    assert d.query(Clinic).first().access_token == "tok"  # все поля перенесены
    assert float(d.query(Price).first().price) == 2000.0
    d.close()
