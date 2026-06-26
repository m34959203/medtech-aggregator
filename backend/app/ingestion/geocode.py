"""Геокодинг адресов клиник (Спринт-2): из приблизительных координат (центр города)
в реальные по адресу → карта и «рядом со мной» становятся рабочими.

Источник — Nominatim (OpenStreetMap), бесплатный, без ключа. Политика: не более
1 запроса/сек и обязательный User-Agent. Живой прогон — скриптом backfill_geocode.py.
"""
from __future__ import annotations

import re

import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/search"
_UA = "medtsena-aggregator/1.0 (price aggregator; contact: ops@medtsena.kz)"


def build_query(address: str, city: str) -> str:
    """Собирает гео-запрос «адрес, город, Казахстан», игнорируя заглушки."""
    addr = (address or "").strip()
    # «сеть лабораторий», «г. Астана» и пустое — не геокодируемы по улице
    if not addr or addr.lower().startswith(("сеть", "г.", "город")):
        addr = ""
    parts = [p for p in (addr, (city or "").strip(), "Казахстан") if p]
    return ", ".join(parts)


def is_geocodable(address: str) -> bool:
    """Есть ли в адресе улица/номер дома (иначе геокодить нечего)."""
    a = (address or "").strip()
    if not a or a.lower().startswith(("сеть", "г.", "город")):
        return False
    return bool(re.search(r"\d", a))  # номер дома → реальный адрес


def geocode(address: str, city: str, client: httpx.Client | None = None,
            timeout: float = 10.0) -> tuple[float, float] | None:
    """Возвращает (lat, lng) по адресу или None. Сетевой вызов."""
    q = build_query(address, city)
    if not q:
        return None
    own = client is None
    client = client or httpx.Client(timeout=timeout, headers={"User-Agent": _UA})
    try:
        r = client.get(NOMINATIM, params={"q": q, "format": "json", "limit": 1})
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None
    finally:
        if own:
            client.close()
