"""Перевод каталога услуг на казахский (name_kk / description_kk) через Gemini/Vertex.

Заполняет ТОЛЬКО пустые KK-поля (идемпотентно). Приоритет — услуги с публичными
офферами (их видит пользователь). Батч = BATCH услуг → один JSON-массив переводов.

    python scripts/generate_kk.py            # dry-run: 1 батч
    python scripts/generate_kk.py --apply    # перевести и записать всё
    python scripts/generate_kk.py --apply --limit 300
"""
from __future__ import annotations

import json
import sys

from app import llm
from app.db import SessionLocal
from app.models import Clinic, Price, ServiceCatalog

BATCH = 20

_PROMPT = """Сен медициналық қызметтер каталогын қазақ тіліне аударатын редакторсың.
Берілген орысша атау мен қысқа сипаттаманы қазақ тіліне аудар. Медициналық терминдерді
дұрыс қолдан, аббревиатураларды сақта (ОАК, УЗИ, МРТ, ПЦР т.б.). Сипаттама бір сөйлем,
≤120 таңба, диагноз қоймай, нейтрал.

Қатаң JSON-ОБЪЕКТ қайтар: {"items":[{"name_kk":"...","desc_kk":"..."}, ...]} — массив кіріс ретімен.

Услуги (RU):
%s"""


def _targets(db):
    public = {
        r[0] for r in db.query(Price.service_id)
        .join(Clinic, Clinic.id == Price.clinic_id)
        .filter(Clinic.is_public.is_(True)).distinct()
    }
    empty = [s for s in db.query(ServiceCatalog).all() if not (s.name_kk or "").strip()]
    empty.sort(key=lambda s: (s.id not in public, s.canonical_name))
    return empty


def main(apply: bool, limit: int | None) -> None:
    if not llm.has_key():
        print("[kk] ✗ LLM не настроен — прерываю")
        return
    db = SessionLocal()
    try:
        targets = _targets(db)
        if limit:
            targets = targets[:limit]
        total = len(targets)
        print(f"[kk] услуг без KK-перевода: {total} (батч={BATCH})")
        done = failed = 0
        for start in range(0, total, BATCH):
            chunk = targets[start:start + BATCH]
            payload = [{"name": s.canonical_name, "desc": (s.description or "")} for s in chunk]
            data = llm.json_completion(_PROMPT % json.dumps(payload, ensure_ascii=False), max_tokens=2000)
            arr = data.get("items") if isinstance(data, dict) and "items" in data else data
            if not isinstance(arr, list):
                failed += len(chunk)
                print(f"  [{start + len(chunk)}/{total}] ✗ батч без массива — пропуск")
                continue
            for i, s in enumerate(chunk):
                item = arr[i] if i < len(arr) and isinstance(arr[i], dict) else {}
                nm = (item.get("name_kk") or "").strip()[:300]
                ds = (item.get("desc_kk") or "").strip()[:300]
                if nm:
                    if apply:
                        s.name_kk = nm
                        s.description_kk = ds
                    done += 1
                    if start == 0 and i < 5:
                        print(f"    {s.canonical_name} → {nm} | {ds}")
            if apply:
                db.commit()
            print(f"  [{min(start + BATCH, total)}/{total}] переведено всего: {done}")
            if not apply:
                print("[kk] dry-run — только первый батч, НЕ записано (--apply для записи)")
                return
        print(f"\n[kk] ✅ готово: переводов {done}, сбойных {failed}")
    finally:
        db.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    lim = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    main(apply="--apply" in args, limit=lim)
