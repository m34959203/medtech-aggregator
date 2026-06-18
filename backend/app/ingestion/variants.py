"""Модель «база + атрибуты варианта» — стержень доверия к сравнению.

«Одна и та же услуга» в медицине нечёткая: «Глюкоза в моче» ≠ «Глюкоза (в крови)»,
повторный приём ≠ первичный. Сравнение цен уже идёт внутри одной услуги (каждый
вариант — своя запись справочника), а этот модуль даёт две вещи поверх:

1. `attributes(canonical)` — атрибуты варианта (биоматериал, тип приёма) + человекочитаемые
   теги для карточки, чтобы «🏆 Лучшая цена» не вводила в заблуждение.
2. `base_key(canonical)` — ключ базовой услуги, по которому варианты группируются и
   показываются как «другие варианты этой услуги».

Источник истины один — вывод из канонического имени (имя кодирует вариант). Схему БД
не трогаем: атрибуты детерминированы и считаются на чтении.
"""
from __future__ import annotations

import re


def base_key(canonical: str) -> str:
    """Нормализует вариант к ключу базовой услуги (для группировки вариантов)."""
    k = (canonical or "").lower().strip()
    k = re.sub(r"^повторный при[её]м\s+", "приём ", k)
    k = re.sub(r"^онлайн-консультация\s+", "приём ", k)
    k = re.sub(r"^при[её]м детского\s+", "приём ", k)
    k = re.sub(r"\s+в моче$", "", k)            # «глюкоза в моче» → «глюкоза»
    k = re.sub(r"\s*\(в\s+крови\)\s*$", "", k)  # «глюкоза (в крови)» → «глюкоза»
    k = re.sub(r"глюкозотолерантный тест", "глюкоза", k)  # вариант глюкозы
    return re.sub(r"\s+", " ", k).strip()


def attributes(canonical: str) -> dict:
    """Атрибуты варианта + теги для витрины. Не мутирует данные."""
    name = (canonical or "").strip()
    low = name.lower()
    attrs: dict = {"base_key": base_key(name), "visit": None, "biomaterial": None,
                   "variant": None, "tags": []}

    # Тип приёма врача
    if re.search(r"^повторный при[её]м", low):
        attrs["visit"] = "repeat"
        attrs["tags"].append("повторный")
    elif low.startswith("онлайн-консультация"):
        attrs["visit"] = "online"
        attrs["tags"].append("онлайн")
    elif re.search(r"^при[её]м детского", low):
        attrs["visit"] = "pediatric"
        attrs["tags"].append("детский")
    elif re.search(r"^при[её]м\b", low):
        attrs["visit"] = "primary"
        attrs["tags"].append("первичный")

    # Биоматериал / тип аналита
    if re.search(r"\bв моче$", low) or low.endswith(" в моче"):
        attrs["biomaterial"] = "urine"
        attrs["tags"].append("моча")
    elif "(в крови)" in low:
        attrs["biomaterial"] = "blood"
        attrs["tags"].append("кровь")

    if "глюкозотолерантный" in low or "толерантн" in low:
        attrs["variant"] = "tolerance"
        attrs["tags"].append("нагрузочный тест")

    return attrs


def variant_label(canonical: str) -> str:
    """Короткая подпись варианта для списка «другие варианты» (без базового слова)."""
    tags = attributes(canonical)["tags"]
    return ", ".join(tags) if tags else canonical
