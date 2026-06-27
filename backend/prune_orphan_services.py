"""Удаление услуг-сирот из справочника: канонов без единой цены (шум каталога).

Услуга-сирота = `ServiceCatalog` без строк в `prices`. Это записи официального
справочника, которые никто не предлагает, — засоряют поиск/каталог. Связанные
`price_history`/`price_subscriptions` (если вдруг есть) удаляются вместе с услугой.

    python prune_orphan_services.py            # dry-run: показать, что удалится
    python prune_orphan_services.py --apply    # удалить

Идемпотентно. НЕ трогает услуги, у которых есть хотя бы одна цена (в т.ч. цены
обезличенных архив-клиник — они остаются в каталоге, просто не видны публично).
"""
from __future__ import annotations

import sys

from app.db import SessionLocal
from app.models import Price, PriceHistory, PriceSubscription, ServiceCatalog


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        priced_ids = {row[0] for row in db.query(Price.service_id).distinct()}
        all_services = db.query(ServiceCatalog).all()
        orphans = [s for s in all_services if s.id not in priced_ids]

        print(f"[prune] услуг всего: {len(all_services)}; с ценами: {len(priced_ids)}; "
              f"сирот к удалению: {len(orphans)}")
        # показываем первые 15 для контроля
        for s in orphans[:15]:
            print(f"    ✗ {s.canonical_name}  [{s.category}]")
        if len(orphans) > 15:
            print(f"    … и ещё {len(orphans) - 15}")

        h_del = sub_del = 0
        if apply:
            ids = [s.id for s in orphans]
            for chunk_start in range(0, len(ids), 500):
                chunk = ids[chunk_start:chunk_start + 500]
                h_del += (db.query(PriceHistory)
                          .filter(PriceHistory.service_id.in_(chunk))
                          .delete(synchronize_session=False))
                sub_del += (db.query(PriceSubscription)
                            .filter(PriceSubscription.service_id.in_(chunk))
                            .delete(synchronize_session=False))
            for s in orphans:
                db.delete(s)
            db.commit()
            print(f"[prune] ✅ удалено: услуг={len(orphans)}, "
                  f"истории={h_del}, подписок={sub_del}")
        else:
            print("[prune] dry-run — НЕ применено (запусти с --apply)")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
