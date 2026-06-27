"""Дозаполнение контактов клиник из 103.kz JSON-LD: сайт, часы работы, рейтинг
(+ телефон/адрес/гео, если пусто). Источник URL — таблица `sources` (web_scrape).

Заполняем ТОЛЬКО пустые поля (идемпотентно, не затираем уже заполненное).
Анонимные «Клиника N» без source-строки не трогаются — у них нет источника.

    python enrich_contacts.py            # dry-run: показать, что изменится
    python enrich_contacts.py --apply    # записать в БД
"""
from __future__ import annotations

import sys

from app.db import SessionLocal
from app.ingestion import web_scraper
from app.models import Clinic, Source


def _empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        # clinic_id → первый 103.kz-URL (у клиники может быть несколько филиалов-источников)
        src_by_clinic: dict = {}
        for s in db.query(Source).filter(Source.type == "web_scrape").all():
            url = s.url_or_endpoint or ""
            if ".103.kz" in url and s.clinic_id not in src_by_clinic:
                src_by_clinic[s.clinic_id] = url

        total = len(src_by_clinic)
        print(f"[enrich] клиник с 103.kz-источником: {total}")
        filled = {"website": 0, "working_hours": 0, "rating": 0, "phone": 0, "address": 0, "geo": 0}
        touched = 0
        for i, (cid, url) in enumerate(src_by_clinic.items(), 1):
            clinic = db.get(Clinic, cid)
            if clinic is None:
                continue
            card = web_scraper.fetch_103kz_card(url)
            if not card:
                print(f"  [{i}/{total}] ✗ {clinic.name}: карточка не получена ({url})")
                continue
            changes = []
            if _empty(clinic.website) and card.get("website"):
                clinic.website = card["website"]; filled["website"] += 1; changes.append("site")
            if _empty(clinic.working_hours) and card.get("working_hours"):
                clinic.working_hours = card["working_hours"]; filled["working_hours"] += 1; changes.append("часы")
            if clinic.rating is None and card.get("rating") is not None:
                clinic.rating = card["rating"]; filled["rating"] += 1; changes.append("рейтинг")
            if _empty(clinic.phone) and card.get("phone"):
                clinic.phone = card["phone"]; filled["phone"] += 1; changes.append("тел")
            if _empty(clinic.address) and card.get("address"):
                clinic.address = card["address"]; filled["address"] += 1; changes.append("адрес")
            if clinic.lat is None and card.get("lat") is not None:
                clinic.lat = float(card["lat"]); clinic.lng = float(card["lng"])
                filled["geo"] += 1; changes.append("гео")
            if changes:
                touched += 1
                print(f"  [{i}/{total}] {clinic.name}: +{', '.join(changes)}"
                      f"  [часы='{card.get('working_hours','')}' рейт={card.get('rating')}]")
        print(f"\n[enrich] клиник затронуто: {touched}; поля: {filled}")
        if apply:
            db.commit()
            print("[enrich] ✅ записано в БД")
        else:
            db.rollback()
            print("[enrich] dry-run — изменения НЕ записаны (запусти с --apply)")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
