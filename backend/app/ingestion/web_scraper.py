"""Веб-парсер сайтов клиник (канал ② pull).

Снимает прайс-таблицы со страницы клиники. Базовая реализация — httpx + BeautifulSoup
(быстро, без браузера). Для динамических SPA-сайтов точка расширения — Playwright
(см. scrape_dynamic). Соблюдаем вежливость: User-Agent + таймаут + без параллельной
бомбардировки (этика автосбора — см. docs).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from .file_parser import RawItem, parse_price
from .robots import RobotsDisallowed, polite_get  # noqa: F401  (re-export для вызовов)

UA = "Mozilla/5.0 (compatible; MedtechAggregator/1.0; +https://example.kz/bot)"


# --- Адаптеры под конкретные сайты (точные CSS-селекторы) ---------------------
# Generic-парсер ниже годится для простых таблиц, но крупные сети рендерят
# карточки услуг BEM-блоками, где имя и цена — разные узлы. Для них — адаптеры.

def _invitro(html: str) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawItem] = []
    for card in soup.select(".analyzes-item"):
        name_el = card.select_one(".analyzes-item__name, .analyzes-item__title, a")
        price_el = card.select_one(".analyzes-item__total--price")
        if not name_el or not price_el:
            continue
        price = parse_price(price_el.get_text(" ", strip=True))
        name = name_el.get_text(" ", strip=True)
        if name and price and len(name) > 2:
            out.append(RawItem(raw_name=name, price=price))
    return _dedup(out)


def _gemotest(html: str) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawItem] = []
    for card in soup.select(".analysis"):
        name_el = card.select_one("a")
        price_el = card.select_one(".analysis-price")  # первая = базовая (не «срочно»)
        if not name_el or not price_el:
            continue
        price = parse_price(price_el.get_text(" ", strip=True))
        name = name_el.get_text(" ", strip=True)
        if name and price and len(name) > 2:
            out.append(RawItem(raw_name=name, price=price))
    return _dedup(out)


def _kdl(html: str) -> list[RawItem]:
    """KDL (kdl.kz / kdlolymp.kz) — лаборатория, источник №1 в ТЗ. Прайс по
    филиалам: `/pricelist/<филиал>`. Карточка анализа — `a.analysis`, цена в
    `.price`, а имя — текст карточки без служебных блоков (.about/.category/
    .duration/.buy: туда уходят «Гематология · 1 день · ₸ · В корзину»)."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawItem] = []
    for card in soup.select("a.analysis, .analysis"):
        price_el = card.select_one(".price")
        if not price_el:
            continue
        price = parse_price(price_el.get_text(" ", strip=True))
        if not price:
            continue
        # срок выполнения анализа («1 день» → 1) из .duration — §2.2 duration_days
        dur_el = card.select_one(".duration")
        days = None
        if dur_el:
            m = re.search(r"(\d+)", dur_el.get_text(" ", strip=True))
            if m:
                days = int(m.group(1))
        # имя = текст карточки минус служебные узлы
        name_node = card.select_one(".name, .title") or card
        if name_node is card:
            tmp = BeautifulSoup(str(card), "html.parser")
            for sel in (".about", ".buy", ".category", ".duration", ".price"):
                for n in tmp.select(sel):
                    n.decompose()
            name = tmp.get_text(" ", strip=True)
        else:
            name = name_node.get_text(" ", strip=True)
        if name and len(name) > 2:
            out.append(RawItem(raw_name=name, price=price, duration_days=days))
    return _dedup(out)


def _103kz(html: str) -> list[RawItem]:
    """Универсальный адаптер платформы 103.kz: десятки клиник РК публикуют там
    прайс по шаблону <бренд>.103.kz/pricing/ в двух вёрстках карточек."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawItem] = []
    variants = [
        (".PersonalCardOfferItem", ".PersonalCardOfferItem__title", ".PersonalCardOfferItem__price"),
        (".PersonalOffers__item", ".PersonalOffers__title", ".PersonalOffers__price"),
    ]
    for item_sel, name_sel, price_sel in variants:
        for card in soup.select(item_sel):
            name_el = card.select_one(name_sel)
            price_el = card.select_one(price_sel)
            if not name_el or not price_el:
                continue
            ptext = price_el.get_text(" ", strip=True).lower()
            if "уточня" in ptext or "недоступ" in ptext:  # «цена по запросу» → пропуск
                continue
            price = parse_price(ptext)  # «от 6 000 тенге» → 6000 (нижняя граница)
            name = name_el.get_text(" ", strip=True)
            if name and price and len(name) > 2:
                out.append(RawItem(raw_name=name, price=price))
    return _dedup(out)


# Точные адаптеры по домену; для суффиксов (платформы-агрегаторы) — _SUFFIX_ADAPTERS.
_SITE_ADAPTERS = {
    "invitro.kz": _invitro,
    "gemotest.kz": _gemotest,
    "kdl.kz": _kdl,
    "kdlolymp.kz": _kdl,
}
_SUFFIX_ADAPTERS = {
    ".103.kz": _103kz,
}


def _adapter_for(url: str):
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if host in _SITE_ADAPTERS:
        return _SITE_ADAPTERS[host]
    for suffix, fn in _SUFFIX_ADAPTERS.items():
        if host.endswith(suffix):
            return fn
    return None


def _items_from_html(html: str) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[RawItem] = []

    # 1. таблицы <table>
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            # цена — числовая ячейка с МАКСИМАЛЬНЫМ значением (прайс ≫ № строки)
            priced = [(parse_price(c), i) for i, c in enumerate(cells)]
            priced = [(p, i) for p, i in priced if p]
            if not priced:
                continue
            price, price_idx = max(priced)
            # имя — самая длинная НЕчисловая ячейка (а не cells[0]: часто там № строки)
            name = ""
            for i, c in enumerate(cells):
                if i == price_idx or parse_price(c) is not None:
                    continue
                if len(c) > len(name):
                    name = c
            if name and len(name) > 2:
                items.append(RawItem(raw_name=name, price=price))

    # 2. списки «услуга — цена» (часто <li> или <div class=price-row>)
    if not items:
        for li in soup.find_all(["li", "div"]):
            text = li.get_text(" ", strip=True)
            if not text or len(text) > 160:
                continue
            price = parse_price(text)
            if price:
                # имя — текст до числа
                name = text.rsplit(str(int(price)), 1)[0].strip(" .—-:")
                if not name:
                    continue
                name = name[:120]
                if len(name) > 2:
                    items.append(RawItem(raw_name=name, price=price))

    return _dedup(items)


def _dedup(items: list[RawItem]) -> list[RawItem]:
    seen, out = set(), []
    for it in items:
        key = (it.raw_name.lower(), it.price)
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


_DOW_RU = {
    "monday": "Пн", "tuesday": "Вт", "wednesday": "Ср", "thursday": "Чт",
    "friday": "Пт", "saturday": "Сб", "sunday": "Вс",
}
_DOW_ORDER = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _format_opening_hours(spec) -> str:
    """schema.org openingHoursSpecification → компактная строка «Пн–Пт 07:30–15:00, Сб …».

    Соседние дни с одинаковым интервалом схлопываются в диапазон. Возвращает ""
    если данных нет/формат неожиданный (часы — необязательное поле клиники)."""
    if not spec:
        return ""
    items = spec if isinstance(spec, list) else [spec]
    by_day: dict[str, str] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        opens, closes = it.get("opens"), it.get("closes")
        days = it.get("dayOfWeek") or []
        days = days if isinstance(days, list) else [days]
        for d in days:
            name = str(d).rstrip("/").rsplit("/", 1)[-1].lower()
            ru = _DOW_RU.get(name)
            if ru and opens and closes:
                by_day[ru] = f"{opens}–{closes}"
    if not by_day:
        return ""
    # схлопываем подряд идущие дни с одинаковым интервалом
    ordered = [(d, by_day[d]) for d in _DOW_ORDER if d in by_day]
    groups: list[tuple[str, str, str]] = []  # (день_от, день_до, интервал)
    for d, h in ordered:
        if groups and groups[-1][2] == h and _DOW_ORDER.index(d) == _DOW_ORDER.index(groups[-1][1]) + 1:
            groups[-1] = (groups[-1][0], d, h)
        else:
            groups.append((d, d, h))
    parts = [(f"{a}–{b} {h}" if a != b else f"{a} {h}") for a, b, h in groups]
    return ", ".join(parts)


def _ld_rating(obj: dict):
    """aggregateRating.ratingValue → float (или None)."""
    ar = obj.get("aggregateRating")
    if isinstance(ar, dict):
        try:
            return round(float(str(ar.get("ratingValue")).replace(",", ".")), 1)
        except (TypeError, ValueError):
            return None
    return None


def fetch_103kz_card(url: str, timeout: float = 20.0) -> dict | None:
    """Реальные контакты клиники с 103.kz: адрес, телефон, координаты, сайт, часы, рейтинг.
    На главной субдомена есть JSON-LD LocalBusiness с geo — это настоящий филиал
    (Organization-блок без geo — шаблонный головной офис, игнорируем)."""
    import json

    host = (urlparse(url).hostname or "")
    if not host.endswith(".103.kz"):
        return None
    try:
        html = polite_get(f"https://{host}/", timeout=timeout).text
    except RobotsDisallowed:
        return None
    except Exception:
        return None
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        for obj in (data if isinstance(data, list) else [data]):
            if isinstance(obj, dict) and obj.get("geo"):
                addr = obj.get("address") or {}
                geo = obj["geo"]
                tel = (obj.get("telephone") or "").split(",")[0].strip()
                tel = re.sub(r"\s+", " ", tel)
                website = (obj.get("url") or "").strip()
                # url JSON-LD часто = сам 103.kz-субдомен; это допустимая «страница клиники».
                return {
                    "address": addr.get("streetAddress") if isinstance(addr, dict) else None,
                    "phone": tel or "",
                    "lat": geo.get("latitude"),
                    "lng": geo.get("longitude"),
                    "website": website,
                    "working_hours": _format_opening_hours(obj.get("openingHoursSpecification")),
                    "rating": _ld_rating(obj),
                }
    return None


def fetch_contact(url: str, timeout: float = 20.0) -> dict | None:
    """Контакты со страницы: адрес/координаты/телефон из JSON-LD (с geo), иначе
    хотя бы телефон из `tel:`-ссылки. Для лаб-сетей (INVIVO/SAPA/Gemotest/INVITRO)."""
    import json

    try:
        html = polite_get(url, timeout=timeout).text
    except RobotsDisallowed:
        return None
    except Exception:
        return None
    out = {"address": None, "phone": "", "lat": None, "lng": None}
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        for obj in (data if isinstance(data, list) else [data]):
            if isinstance(obj, dict) and obj.get("geo"):
                addr = obj.get("address") or {}
                geo = obj["geo"]
                out["address"] = addr.get("streetAddress") if isinstance(addr, dict) else None
                out["phone"] = re.sub(r"\s+", " ", (obj.get("telephone") or "").split(",")[0].strip())
                out["lat"], out["lng"] = float(geo["latitude"]), float(geo["longitude"])
                return out
    m = re.search(r'tel:([+\d][\d\s()+-]{7,})', html)
    if m:
        out["phone"] = re.sub(r"\s+", " ", m.group(1).strip())
        return out
    return None


def scrape_lab_platform(base_url: str, city: str, timeout: float = 45.0) -> list[RawItem]:
    """Лаборатории INVIVO и SAPA на общей Django-платформе: каталог анализов
    отдаётся не в статике, а сессионным AJAX. Берём cookies со страницы, затем
    `a-and-c-search-with-panels?service_type=anl` (любой ≠ pac → отдельные
    анализы, pac = чек-ап пакеты). Markup двух видов — INVIVO (.results-analyzes-
    item) и SAPA (строки .row с .cell__value)."""
    base = base_url.rstrip("/")
    referer = f"{base}/ru/{city}/analyzes/"
    with httpx.Client(headers={"User-Agent": settings.scrape_user_agent},
                      timeout=timeout, follow_redirects=True, verify=False) as c:
        polite_get(referer, timeout=timeout, client=c)  # набрать csrftoken/sessionid
        ajax = (f"{base}/ru/ajax/{city}/a-and-c-search-with-panels/"
                "?service_type=anl&categories=%5B%5D&showed=%5B%5D&all=true&_=1")
        resp = polite_get(ajax, timeout=timeout, client=c,
                          headers={"X-Requested-With": "XMLHttpRequest", "Referer": referer})
        resp.raise_for_status()
        data = resp.json().get("data", "")
    soup = BeautifulSoup(data, "html.parser")
    out: list[RawItem] = []
    cards = soup.select(".results-analyzes-item")
    if cards:  # INVIVO: имя до «Код:», цена — последний ₸ в карточке
        for it in cards:
            text = it.get_text(" ", strip=True)
            name = re.split(r"Код", text)[0].strip()
            nums = re.findall(r"([\d\s][\d\s]*)\s*₸", text)
            price = parse_price(nums[-1]) if nums else None
            if name and price and len(name) > 2:
                out.append(RawItem(raw_name=name, price=price))
    else:  # SAPA: строка-анализ, ячейки .cell__value (имя + цена с ₸)
        for row in soup.select(".row.justify-content-between, .open-research"):
            vals = [cell.get_text(" ", strip=True) for cell in row.select(".cell__value")]
            name = max((v for v in vals if "₸" not in v), key=len, default="")
            price = next((parse_price(v) for v in vals if "₸" in v), None)
            if name and price and len(name) > 2:
                out.append(RawItem(raw_name=name, price=price))
    return _dedup(out)


def scrape_url_raw(url: str, timeout: float = 20.0) -> tuple[str, list[RawItem]]:
    """Как scrape_url, но возвращает (сырой HTML, позиции) — для raw-слоя (§3.1)."""
    resp = polite_get(url, timeout=timeout)  # robots.txt + crawl-delay
    resp.raise_for_status()
    adapter = _adapter_for(url)
    items = adapter(resp.text) if adapter else _items_from_html(resp.text)
    return resp.text, items


def scrape_url(url: str, timeout: float = 20.0) -> list[RawItem]:
    return scrape_url_raw(url, timeout)[1]


def scrape_html(html: str) -> list[RawItem]:
    """Парсинг уже скачанного HTML (удобно для тестов и демо без сети)."""
    return _items_from_html(html)


def scrape_dynamic(url: str) -> list[RawItem]:
    """Точка расширения для SPA-сайтов через Playwright (если установлен)."""
    from .robots import can_fetch
    if not can_fetch(url):
        raise RobotsDisallowed(url)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Playwright не установлен: pip install playwright && playwright install chromium") from e
    with sync_playwright() as p:  # pragma: no cover
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=UA)
        page.goto(url, wait_until="networkidle")
        html = page.content()
        browser.close()
    return _items_from_html(html)
