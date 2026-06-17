"""Веб-парсер сайтов клиник (канал ② pull).

Снимает прайс-таблицы со страницы клиники. Базовая реализация — httpx + BeautifulSoup
(быстро, без браузера). Для динамических SPA-сайтов точка расширения — Playwright
(см. scrape_dynamic). Соблюдаем вежливость: User-Agent + таймаут + без параллельной
бомбардировки (этика автосбора — см. docs).
"""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from .file_parser import RawItem, parse_price

UA = "Mozilla/5.0 (compatible; MedtechAggregator/1.0; +https://example.kz/bot)"


def _items_from_html(html: str) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[RawItem] = []

    # 1. таблицы <table>
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            name = cells[0]
            price = None
            for c in cells[1:]:
                price = parse_price(c)
                if price:
                    break
            if name and price and len(name) > 2:
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


def scrape_url(url: str, timeout: float = 20.0) -> list[RawItem]:
    with httpx.Client(headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return _items_from_html(resp.text)


def scrape_html(html: str) -> list[RawItem]:
    """Парсинг уже скачанного HTML (удобно для тестов и демо без сети)."""
    return _items_from_html(html)


def scrape_dynamic(url: str) -> list[RawItem]:
    """Точка расширения для SPA-сайтов через Playwright (если установлен)."""
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
