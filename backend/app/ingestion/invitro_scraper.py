"""Парсер каталога анализов INVITRO (invitro.kz) — канал ② pull, отдельный источник.

РАЗВЕДКА (что реально на сайте, проверено вживую, июнь 2026):
  • Главная invitro.kz — динамическая (1С-Bitrix + JS), цен в HTML главной нет.
  • НО каталог анализов отдаётся СЕРВЕРНО (Bitrix SSR), цена и срок уже в HTML —
    браузер для съёма НЕ обязателен. Адреса (без query-параметров!):
        /analizes/for-doctors/            — каталог в городе по умолчанию (Алматы);
        /analizes/for-doctors/<город>/    — каталог конкретного города (slug В ПУТИ).
    Вёрстка карточки: контейнер `.analyzes-item`, имя в `.analyzes-item__title a`,
    цена в `.analyzes-item__total--price` (₸), срок — «N календарный день» /
    «До N рабочих дней» в `.analyzes-item__add--list-item span`.
  • Цены ГОРОДОЗАВИСИМЫ: «Общий анализ крови» = 520 ₸ (Алматы) vs 1 330 ₸ (Астана).
  • Город переключается ещё кукой INVITRO_CITY(+_GUID), а в UI — через
    `/?CITY_NAME=<город>`, НО этот URL запрещён robots.txt (правило `/*?`). Путь
    `/analizes/for-doctors/<город>/` — без `?` → robots-чистый, его и используем.

ПОДХОД. Основной — httpx через robots.polite_get (как весь pull-канал проекта):
быстро, стабильно, без браузера. Playwright оставлен ФОЛБЭКОМ на случай, если
INVITRO когда-нибудь спрячет прайс в клиентский JS-рендер — тогда рендерим ту же
вёрстку (chromium --no-sandbox, networkidle) и парсим тот же DOM. Любой сбой
(сеть/robots/верстка/нет браузера) → graceful `[]` с логом, пайплайн не падает.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from .file_parser import RawItem, parse_price
from .robots import RobotsDisallowed, can_fetch, polite_get

log = logging.getLogger(__name__)

BASE = "https://invitro.kz"
# Обычный браузерный UA для Playwright-фолбэка (httpx-путь ставит UA из robots).
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Валидные slug'и городов из sitemap analizes.xml (region code в пути каталога).
# Неизвестный город не блокируем — пробуем как есть (вдруг INVITRO добавил город).
INVITRO_CITIES = {
    "aktau", "aktobe", "almaty", "astana", "atyrau", "boralday", "esik",
    "irgeli", "karaganda", "kargaly", "kaskelen", "konaev", "kostanay",
    "kyzylorda", "otegen-batyra", "pavlodar", "petropavlovsk", "saran",
    "semey", "shymkent", "taldykorgan", "talgar2", "taraz", "temirtau",
    "tuzdybastau", "uralsk", "ushkonyr", "ust-kamenogorsk", "uzynagash",
    "zhanaozen",
}
# Русские названия → slug (чтобы caller мог передать «Алматы»/«Астана»).
_CITY_ALIASES = {
    "алматы": "almaty", "алма-ата": "almaty",
    "астана": "astana", "нур-султан": "astana", "нур султан": "astana",
    "шымкент": "shymkent", "караганда": "karaganda", "актобе": "aktobe",
    "актау": "aktau", "атырау": "atyrau", "тараз": "taraz",
    "павлодар": "pavlodar", "костанай": "kostanay", "семей": "semey",
    "уральск": "uralsk", "кызылорда": "kyzylorda", "темиртау": "temirtau",
    "петропавловск": "petropavlovsk", "талдыкорган": "taldykorgan",
    "усть-каменогорск": "ust-kamenogorsk", "конаев": "konaev",
}


def _city_slug(city: str) -> str:
    c = (city or "almaty").strip().lower()
    return _CITY_ALIASES.get(c, c)


def catalog_url(city: str = "almaty") -> str:
    """URL каталога анализов INVITRO для города (slug в пути, без query)."""
    slug = _city_slug(city)
    if slug == "almaty":
        # default-город отдаётся и по базовому пути, и по /almaty/ — берём базовый
        return f"{BASE}/analizes/for-doctors/"
    return f"{BASE}/analizes/for-doctors/{slug}/"


# Срок: «1 календарный день», «До 6 календарных дней», «До 3 рабочих дней» → N.
_DUR_RE = re.compile(r"(\d+)\s*(?:календарн|рабоч)", re.IGNORECASE)


def _card_duration(card) -> int | None:
    for sp in card.select(".analyzes-item__add--list-item span"):
        m = _DUR_RE.search(sp.get_text(" ", strip=True))
        if m:
            return int(m.group(1))
    return None


def parse_invitro_catalog(html: str, limit: int | None = None) -> list[RawItem]:
    """Офлайн-парсер каталога INVITRO из HTML → позиции (имя/цена/срок).

    Выделен отдельно от сети для тестируемости (фикстура вёрстки, без браузера).
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawItem] = []
    seen: set[tuple[str, float]] = set()
    for card in soup.select(".analyzes-item"):
        name_el = card.select_one(".analyzes-item__title a, .analyzes-item__title")
        price_el = card.select_one(".analyzes-item__total--price")
        if not name_el or not price_el:
            continue
        name = name_el.get_text(" ", strip=True)
        price = parse_price(price_el.get_text(" ", strip=True))
        if not name or price is None or len(name) < 3:
            continue
        key = (name.lower(), price)
        if key in seen:  # один анализ может встретиться в нескольких блоках страницы
            continue
        seen.add(key)
        out.append(RawItem(
            raw_name=name,
            price=price,
            duration_days=_card_duration(card),
            currency="KZT",
        ))
        if limit and len(out) >= limit:
            break
    return out


def _scrape_static(url: str, limit: int | None) -> list[RawItem]:
    """Основной путь: httpx через robots.polite_get (robots.txt + crawl-delay)."""
    resp = polite_get(url, timeout=45.0)  # бросит RobotsDisallowed, если запрещён
    resp.raise_for_status()
    return parse_invitro_catalog(resp.text, limit=limit)


def _scrape_playwright(url: str, limit: int | None) -> list[RawItem]:
    """Фолбэк: рендер chromium (если прайс уедет в клиентский JS). --no-sandbox."""
    if not can_fetch(url):
        raise RobotsDisallowed(url)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page(user_agent=UA)
            page.goto(url, wait_until="networkidle", timeout=60000)
            html = page.content()
        finally:
            browser.close()
    return parse_invitro_catalog(html, limit=limit)


def scrape_invitro(city: str = "almaty", limit: int | None = None) -> list[RawItem]:
    """Снять каталог анализов INVITRO для города → list[RawItem] (KZT, со сроком).

    Город — slug ('almaty'/'astana'/...) или рус. название ('Алматы'). По
    умолчанию Алматы. Цены городозависимые. Сначала статический httpx-путь
    (быстрый, без браузера), при пустом результате — Playwright-фолбэк.
    Любой сбой → `[]` (graceful): источник не должен ронять весь пайплайн.
    """
    slug = _city_slug(city)
    if slug not in INVITRO_CITIES:
        log.warning("INVITRO: неизвестный город %r — пробую как slug %r", city, slug)
    url = catalog_url(city)

    # 1) статический путь (предпочтительный)
    try:
        items = _scrape_static(url, limit)
        if items:
            log.info("INVITRO[%s]: статически снято %d позиций (%s)", slug, len(items), url)
            return items
        log.info("INVITRO[%s]: статически пусто, пробую Playwright-фолбэк", slug)
    except RobotsDisallowed:
        log.warning("INVITRO[%s]: robots.txt запрещает %s — пропуск", slug, url)
        return []
    except Exception as e:  # сеть/таймаут/верстка — не валимся
        log.warning("INVITRO[%s]: статический сбой (%s), пробую Playwright", slug, e)

    # 2) Playwright-фолбэк (если прайс ушёл в JS или статика отвалилась)
    try:
        items = _scrape_playwright(url, limit)
        log.info("INVITRO[%s]: через Playwright снято %d позиций", slug, len(items))
        return items
    except RobotsDisallowed:
        log.warning("INVITRO[%s]: robots.txt запрещает %s — пропуск", slug, url)
        return []
    except ImportError:
        log.warning("INVITRO[%s]: Playwright недоступен — возвращаю []", slug)
        return []
    except Exception as e:  # pragma: no cover
        log.warning("INVITRO[%s]: Playwright-сбой (%s) — возвращаю []", slug, e)
        return []
