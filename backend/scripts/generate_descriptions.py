"""Генерация кратких описаний услуг для витрины (Gemini/Vertex, батчами).

Для каждой услуги — одно короткое нейтральное предложение «что это» (≤120 симв.),
без диагнозов/советов. Заполняет только ПУСТЫЕ `description` (идемпотентно).
Приоритет — услуги с публичными офферами (их реально видят пользователи).

    python generate_descriptions.py            # dry-run: 1 батч, показать примеры
    python generate_descriptions.py --apply    # сгенерировать и записать всё
    python generate_descriptions.py --apply --limit 200   # ограничить кол-во услуг

Батч = BATCH имён → один JSON-ответ {имя: описание}. При сбое батча — пропуск
(описание необязательное, можно догнать повторным запуском).
"""
from __future__ import annotations

import json
import sys

from app import llm
from app.db import SessionLocal
from app.models import Clinic, Price, ServiceCatalog

BATCH = 25

_PROMPT = """Ты — медицинский редактор каталога услуг. Для каждого названия медицинской
услуги дай ОДНО короткое нейтральное предложение по-русски: что это за услуга/анализ
и зачем (простыми словами для пациента). Строго ≤120 символов, без диагнозов, без
советов «обратитесь к врачу», без воды и кавычек. Если название непонятно — дай общее
корректное пояснение по категории.

Верни СТРОГО JSON-объект {"название": "описание", ...} с теми же названиями-ключами.

Услуги:
%s"""


def _ordered_targets(db):
    """Услуги с пустым описанием: сперва с публичными офферами, потом остальные."""
    public_sids = {
        r[0] for r in db.query(Price.service_id)
        .join(Clinic, Clinic.id == Price.clinic_id)
        .filter(Clinic.is_public.is_(True)).distinct()
    }
    empty = [s for s in db.query(ServiceCatalog).all() if not (s.description or "").strip()]
    empty.sort(key=lambda s: (s.id not in public_sids, s.canonical_name))
    return empty


def main(apply: bool, limit: int | None) -> None:
    if not llm.has_key():
        print("[descr] ✗ LLM не настроен (нет ключа/SA) — прерываю")
        return
    db = SessionLocal()
    try:
        targets = _ordered_targets(db)
        if limit:
            targets = targets[:limit]
        total = len(targets)
        print(f"[descr] услуг без описания к обработке: {total} (батч={BATCH})")
        done = failed = 0
        for start in range(0, total, BATCH):
            chunk = targets[start:start + BATCH]
            names = [s.canonical_name for s in chunk]
            data = llm.json_completion(_PROMPT % json.dumps(names, ensure_ascii=False), max_tokens=1500)
            if not isinstance(data, dict):
                failed += len(chunk)
                print(f"  [{start + len(chunk)}/{total}] ✗ батч без JSON — пропуск")
                continue
            # сопоставляем по точному имени, иначе по позиции
            vals = list(data.values())
            for i, s in enumerate(chunk):
                desc = (data.get(s.canonical_name) or (vals[i] if i < len(vals) else "") or "").strip()
                desc = desc.strip('"').strip()[:240]
                if not desc:
                    continue
                if apply:
                    s.description = desc
                done += 1
                if start == 0 and i < 5:
                    print(f"    «{s.canonical_name}» → {desc}")
            if apply:
                db.commit()
            print(f"  [{min(start + BATCH, total)}/{total}] записано всего: {done}")
            if not apply:
                print("[descr] dry-run — только первый батч, НЕ записано (запусти с --apply)")
                return
        print(f"\n[descr] ✅ готово: описаний {done}, сбойных {failed}")
    finally:
        db.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    lim = None
    if "--limit" in args:
        lim = int(args[args.index("--limit") + 1])
    main(apply="--apply" in args, limit=lim)
