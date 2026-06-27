"""Валюта как ENUM из значений ТЗ §2.2 MedPrice: KZT / USD.

ТЗ требует enum {KZT, USD} с конвертацией в KZT. В источниках валюта приходит
шумно («Тенге», «₸», «$»), поэтому приводим к канону на приёме. Конверсия
USD→KZT — в ``ingestion.service.to_kzt``; здесь только нормализация обозначения.
"""
from __future__ import annotations

import enum


class Currency(str, enum.Enum):
    """§2.2 ТЗ: валюта цены — строгий enum. Хранимая цена всегда в KZT."""

    KZT = "KZT"
    USD = "USD"


# Шумные обозначения (upper, без пробелов) → канон. Неизвестное → KZT.
_ALIASES = {
    "": Currency.KZT,
    "KZT": Currency.KZT,
    "ТГ": Currency.KZT,
    "ТЕНГЕ": Currency.KZT,
    "ТЕНГЕ.": Currency.KZT,
    "₸": Currency.KZT,
    "USD": Currency.USD,
    "$": Currency.USD,
    "ДОЛЛАР": Currency.USD,
}


def normalize(raw: str | None) -> Currency:
    """Любое обозначение валюты → канонический ``Currency`` (дефолт KZT)."""
    return _ALIASES.get((raw or "").upper().strip(), Currency.KZT)
