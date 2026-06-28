"""Бэкфилл реальных координат клиник по адресу (Спринт-2).

Запуск внутри контейнера бэка:  python backfill_geocode.py [--all]
Без флага — только клиники без координат или с геокодируемым адресом, у которых
координаты выглядят как центр города. С --all — перегеокодировать всё с адресом.
Соблюдает лимит Nominatim 1 req/сек.
"""
from __future__ import annotations

import sys
import time

import httpx

from app.db import SessionLocal
from app.ingestion.geocode import _UA, geocode, is_geocodable
from app.models import Clinic


def main(force_all: bool = False) -> None:
    db = SessionLocal()
    client = httpx.Client(timeout=10.0, headers={"User-Agent": _UA})
    try:
        clinics = db.query(Clinic).all()
        updated = skipped = failed = 0
        for c in clinics:
            if not is_geocodable(c.address):
                skipped += 1
                continue
            if not force_all and c.lat is not None and c.lng is not None:
                # уже есть координаты и не просили перегеокодировать
                skipped += 1
                continue
            coords = geocode(c.address, c.city, client=client)
            time.sleep(1.1)  # лимит Nominatim
            if not coords:
                failed += 1
                print(f"  ✗ {c.name}: не геокодировано ({c.address})")
                continue
            c.lat, c.lng = coords
            updated += 1
            print(f"  ✓ {c.name}: {coords[0]:.5f}, {coords[1]:.5f}")
            db.commit()
        print(f"\nИтого: обновлено {updated}, пропущено {skipped}, не удалось {failed}.")
    finally:
        client.close()
        db.close()


if __name__ == "__main__":
    main(force_all="--all" in sys.argv)
