"""Слияние дублей-канонов «Глюкоза (кровь)» / «Глюкоза (кровь) экспресс» в SPECS-канон
«Глюкоза (в крови)» (долг #41/#43).

Официальный «Справочник услуг.xlsx» содержит «Глюкоза (кровь)»+«…экспресс», а SPECS
(`load_real_data.py`) — «Глюкоза (в крови)». archive-ингест создавал их отдельными
канонами → в чате/сравнении два почти одинаковых блюда крови. Этот скрипт переносит
цены/синонимы в главный канон и удаляет пустые дубли. Мочевые/толерантный тест НЕ
трогаются (другой биоматериал/методика).

Аномалия: мочевые сырьё под кровяным дублем с неадекватной ценой (парс-ошибка) —
удаляется как мусор (не пригодно для сравнения); адекватные мочевые → в «Глюкоза в моче».

    python merge_glucose.py            # dry-run: показать план
    python merge_glucose.py --apply    # выполнить

Идемпотентно: повторный запуск ничего не находит (дубли уже удалены).
"""
from __future__ import annotations

import sys

from app.db import SessionLocal
from app.models import Price, PriceHistory, PriceSubscription, ServiceCatalog

PRIMARY = "Глюкоза (в крови)"
URINE = "Глюкоза в моче"
DUPS = ["Глюкоза (кровь)", "Глюкоза (кровь) экспресс"]
_ABSURD_PRICE = 50_000  # ни один анализ глюкозы не стоит столько → парс-ошибка
# Маркеры «шумного» сырого имени: пакет/комплекс/чужой контекст — НЕ кладём в синонимы
# (иначе ложные совпадения, болезнь кросс-загрязнения синонимов из NOTES).
_NOISE = ("комплекс", "обследовани", "супружеск", "пара", "панель", "профиль", "чек")


def _by_name(db, name):
    return db.query(ServiceCatalog).filter(ServiceCatalog.canonical_name == name).first()


def _is_urine(raw: str) -> bool:
    return "моч" in (raw or "").lower()


def _good_synonym(raw: str) -> bool:
    """Короткое глюкозо-специфичное имя, без пакетного шума → годится в синонимы."""
    low = (raw or "").lower()
    return bool(raw) and len(raw) <= 40 and not any(n in low for n in _NOISE)


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        primary = _by_name(db, PRIMARY)
        urine = _by_name(db, URINE)
        if primary is None:
            print(f"[merge] ✗ главный канон «{PRIMARY}» не найден — прерываю")
            return

        existing_syn = {s.lower() for s in (primary.synonyms or [])}
        new_syn: list[str] = []
        moved = deleted_prices = moved_to_urine = 0

        for dup_name in DUPS:
            dup = _by_name(db, dup_name)
            if dup is None:
                print(f"[merge] «{dup_name}» уже отсутствует — пропуск")
                continue
            prices = db.query(Price).filter(Price.service_id == dup.id).all()
            print(f"\n[merge] «{dup_name}» — {len(prices)} цен:")
            for p in prices:
                raw = p.raw_name or ""
                if _is_urine(raw):
                    if float(p.price) >= _ABSURD_PRICE:
                        print(f"    ✗ УДАЛИТЬ мусор (моча+цена {p.price}): {raw!r}")
                        if apply:
                            db.delete(p)
                        deleted_prices += 1
                    elif urine is not None:
                        print(f"    → в «{URINE}»: {raw!r} ({p.price})")
                        if apply:
                            p.service_id = urine.id
                        moved_to_urine += 1
                    else:
                        print(f"    ! моча, но канона «{URINE}» нет — оставляю: {raw!r}")
                    continue
                # кровь → в главный канон; сырое имя → кандидат в синонимы
                print(f"    → в «{PRIMARY}»: {raw!r} ({p.price})")
                if apply:
                    p.service_id = primary.id
                moved += 1
                if _good_synonym(raw) and raw.lower() not in existing_syn:
                    existing_syn.add(raw.lower())
                    new_syn.append(raw)

            # синоним самого дубля-имени тоже полезен для поиска
            if dup_name.lower() not in existing_syn:
                existing_syn.add(dup_name.lower())
                new_syn.append(dup_name)

            # price_history по FK: мусор (цена-аномалия) удалить, остальное → в главный
            hist = db.query(PriceHistory).filter(PriceHistory.service_id == dup.id).all()
            h_moved = h_del = 0
            for h in hist:
                if float(h.price) >= _ABSURD_PRICE:
                    if apply:
                        db.delete(h)
                    h_del += 1
                else:
                    if apply:
                        h.service_id = primary.id
                    h_moved += 1
            # подписки (если есть) → в главный
            subs = db.query(PriceSubscription).filter(PriceSubscription.service_id == dup.id).all()
            for s in subs:
                if apply:
                    s.service_id = primary.id
            if hist or subs:
                print(f"    история: →главный {h_moved}, удалить мусор {h_del}; подписок {len(subs)}")

            print(f"    🗑  удалить пустой канон «{dup_name}»")
            if apply:
                db.flush()  # чтобы repoint истории/цен ушёл в БД ДО удаления канона
                db.delete(dup)

        if new_syn:
            print(f"\n[merge] +{len(new_syn)} синонимов в «{PRIMARY}»: {new_syn}")
            if apply:
                primary.synonyms = list(primary.synonyms or []) + new_syn

        print(f"\n[merge] итог: цен в главный={moved}, в мочу={moved_to_urine}, "
              f"удалено мусор-цен={deleted_prices}, дублей-канонов удалить={len(DUPS)}")
        if apply:
            db.commit()
            print("[merge] ✅ применено")
        else:
            db.rollback()
            print("[merge] dry-run — НЕ применено (запусти с --apply)")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
