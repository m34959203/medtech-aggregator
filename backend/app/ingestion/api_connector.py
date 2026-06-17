"""API-коннектор (канал ② pull): тянет прайс из REST/JSON эндпоинта клиники
или стороннего агрегатора и приводит к RawItem.

Гибко мапит поля: имя услуги и цена ищутся по типичным ключам, структура ответа
может быть списком или объектом с массивом внутри (data/items/services/results).
"""
from __future__ import annotations

import httpx

from .file_parser import RawItem, parse_price

NAME_KEYS = ["name", "service", "title", "наименование", "услуга", "атауы", "service_name"]
PRICE_KEYS = ["price", "cost", "amount", "цена", "стоимость", "бағасы", "value"]
LIST_KEYS = ["data", "items", "services", "results", "prices", "list"]


def _extract_list(payload) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in LIST_KEYS:
            if isinstance(payload.get(k), list):
                return [x for x in payload[k] if isinstance(x, dict)]
        # объект сам может быть {name: price, ...}
        flat = [{"name": k, "price": v} for k, v in payload.items() if isinstance(v, (int, float, str))]
        return flat
    return []


def _pick(d: dict, keys: list[str]):
    lower = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k in lower:
            return lower[k]
    return None


def items_from_json(payload) -> list[RawItem]:
    items: list[RawItem] = []
    for row in _extract_list(payload):
        name = _pick(row, NAME_KEYS)
        price = parse_price(_pick(row, PRICE_KEYS))
        if name and price and len(str(name)) > 2:
            items.append(RawItem(raw_name=str(name).strip(), price=price))
    return items


def fetch_api(endpoint: str, timeout: float = 20.0, headers: dict | None = None) -> list[RawItem]:
    with httpx.Client(timeout=timeout, headers=headers or {}, follow_redirects=True) as client:
        resp = client.get(endpoint)
        resp.raise_for_status()
        return items_from_json(resp.json())
