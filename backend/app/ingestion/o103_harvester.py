"""Харвестер платформы 103.kz — канал ② pull, «полный охват» клиник/лабораторий РК.

ИДЕЯ. 103.kz — агрегатор, где СОТНИ клиник и лабораторий всех городов Казахстана
публикуют прайс по единой схеме `https://{slug}.103.kz/pricing/` (СТАТИКА, SSR).
Один источник → десятки клиник с ценами, контактами и гео. Разбор одной такой
страницы уже реализован в проекте:
    web_scraper._103kz(html)        → list[RawItem]  (имя/цена позиции прайса);
    web_scraper.fetch_103kz_card(u) → {address, phone, lat, lng}  (JSON-LD LocalBusiness с geo).
Здесь — слой ПОВЕРХ них: «как найти slug'и» (discover) и «снять пачку» (harvest).

РАЗВЕДКА (проверено вживую, июнь 2026):
  • Пул всех клиник — в sitemap `https://www.103.kz/sitemap-personals.xml.gz`
    (~9248 субдоменов `{slug}.103.kz`). Города в нём нет.
  • Городские листинги — `https://www.103.kz/list/{рубрика}/{город}/`
    (laboratorii / analizy / medicinskie-centry). Листинг React-рендерится, в
    статике видна лишь горстка клиник на страницу — берём что есть (city-confirmed),
    остальное добивается из общего пула + города из карточки.
  • Имя клиники и ГОРОД — в JSON-LD `LocalBusiness` прямо на странице `/pricing/`
    (name, address.addressLocality), а geo (lat/lng) — в карточке главной (`/`).
    Поэтому на клинику два вежливых запроса: /pricing/ (позиции+имя+город) и / (geo).

ROBOTS. Все сетевые GET идут через robots.polite_get (он проверит 103.kz/robots.txt
и соблюдёт crawl-delay): `*?`/`*&`/`/search/`/`/index` запрещены, `/pricing/` и
`/list/` — разрешены, sitemap'ы тоже. Любой сбой/запрет → graceful-пропуск.
"""
from __future__ import annotations

import gzip
import json
import logging
import re

from . import web_scraper as ws
from .file_parser import RawItem
from .robots import RobotsDisallowed, polite_get

log = logging.getLogger(__name__)

SITEMAP_PERSONALS = "https://www.103.kz/sitemap-personals.xml.gz"

# Проверенные slug'и лабораторий/клиник с заведомо непустым /pricing/ — удобный
# вход harvest_known() без обхода каталога (источники №1 из ТЗ + крупные на 103.kz).
KNOWN_SLUGS = ["gemotest", "invitro", "kdlolymp", "rahat", "olimp", "aqmed", "smart-med"]

# Инфраструктурные субдомены 103.kz — это НЕ клиники, выкидываем при сборе slug'ов.
_DENY = {
    "www", "m", "static", "static1", "static2", "static3", "cdn", "img", "images",
    "ms1", "ms2", "go", "info", "mag", "apteka", "beta", "api", "blog", "help",
    "lk", "dialog", "partner", "b2b", "ws", "media", "files", "assets", "ams",
}

# Рубрики городских листингов, где встречаются лаборатории/анализы/медцентры.
_LIST_RUBRICS = ("laboratorii", "analizy", "medicinskie-centry")

# Рус. название города → slug 103.kz (у платформы свои написания: semei/uk/...).
_CITY_ALIASES = {
    "алматы": "almaty", "алма-ата": "almaty",
    "астана": "astana", "нур-султан": "astana",
    "шымкент": "shymkent", "караганда": "karaganda", "актобе": "aktobe",
    "актау": "aktau", "атырау": "atyrau", "тараз": "taraz", "павлодар": "pavlodar",
    "костанай": "kostanay", "семей": "semei", "кызылорда": "kyzylorda",
    "петропавловск": "petropavlovsk", "талдыкорган": "taldykorgan",
    "усть-каменогорск": "uk", "уральск": "uralysk-kazahstan", "балхаш": "balkhash",
}

_SLUG_RE = re.compile(r"https?://([a-z0-9][a-z0-9-]*)\.103\.kz", re.IGNORECASE)


def _city_slug(city: str) -> str:
    c = (city or "").strip().lower()
    return _CITY_ALIASES.get(c, c)


def _extract_slugs(html_or_xml: str) -> list[str]:
    """Достать уникальные slug'и `{slug}.103.kz` из HTML листинга или XML sitemap,
    отсеяв инфраструктурные субдомены. Порядок сохраняем (важно для limit)."""
    out: list[str] = []
    seen: set[str] = set()
    for s in _SLUG_RE.findall(html_or_xml):
        s = s.lower()
        if s in seen or s in _DENY:
            continue
        seen.add(s)
        out.append(s)
    return out


def discover_slugs(city: str | None = None, limit: int = 50) -> list[str]:
    """Найти slug'и клиник на 103.kz.

    city=None → общий пул из sitemap-personals (тысячи клиник, без города).
    city задан → городские листинги `/list/{рубрика}/{город}/` (city-confirmed,
    но статикой их немного — 103.kz листинг React). Любой сбой → то, что успели.
    """
    slugs: list[str] = []
    seen: set[str] = set()

    def _add(found: list[str]) -> bool:
        for s in found:
            if s not in seen:
                seen.add(s)
                slugs.append(s)
                if len(slugs) >= limit:
                    return True
        return False

    if city:
        cs = _city_slug(city)
        for rubric in _LIST_RUBRICS:
            url = f"https://www.103.kz/list/{rubric}/{cs}/"
            try:
                html = polite_get(url, timeout=30.0).text
            except RobotsDisallowed:
                log.warning("103.kz: robots запрещает %s", url)
                continue
            except Exception as e:
                log.warning("103.kz: листинг %s недоступен (%s)", url, e)
                continue
            if _add(_extract_slugs(html)):
                break
        log.info("103.kz: для города %r найдено %d slug'ов", city, len(slugs))
        return slugs

    # Глобальный пул: gzip-sitemap всех клиник.
    try:
        raw = polite_get(SITEMAP_PERSONALS, timeout=60.0).content
        xml = gzip.decompress(raw).decode("utf-8", "ignore")
    except RobotsDisallowed:
        log.warning("103.kz: robots запрещает sitemap")
        return slugs
    except Exception as e:
        log.warning("103.kz: sitemap недоступен (%s)", e)
        return slugs
    _add(_extract_slugs(xml))
    log.info("103.kz: из sitemap собрано %d slug'ов (лимит %d)", len(slugs), limit)
    return slugs


# Сети-лаборатории с пронумерованными поддоменами-филиалами (invitro-12, olimp-70,
# gemotest-5…). Их филиалы есть и в МАЛЫХ городах, прайс сети единый/региональный,
# город у каждого филиала свой (из карточки) — высокий выход охвата на город.
CHAIN_SLUG_RE = re.compile(
    r"^(invitro|olimp|olympe?|kdl|gemotest|helix|genom|sinevo|synevo|inco|dnk)[-0-9]",
    re.IGNORECASE,
)


def discover_chain_branches(limit: int = 500) -> list[str]:
    """Из общего sitemap отобрать филиалы сетей-лабораторий (см. CHAIN_SLUG_RE).

    Это рычаг малых городов: сканировать пул «с головы» бесполезно (он отсортирован
    по мегаполисам), а филиалы сетей раскиданы по всей стране. Город каждого филиала
    берётся из его карточки при сборе.
    """
    pool = discover_slugs(None, limit=99999)
    branches = [s for s in pool if CHAIN_SLUG_RE.match(s)]
    log.info("103.kz: филиалов сетей в sitemap %d (берём %d)", len(branches), min(limit, len(branches)))
    return branches[:limit]


# schema.org dayOfWeek → (русское сокращение, индекс недели)
_DOW = {"monday": ("Пн", 0), "tuesday": ("Вт", 1), "wednesday": ("Ср", 2),
        "thursday": ("Чт", 3), "friday": ("Пт", 4), "saturday": ("Сб", 5),
        "sunday": ("Вс", 6)}


def _parse_hours(obj: dict) -> str:
    """§3.3 режим работы из JSON-LD LocalBusiness (openingHoursSpecification).
    Группирует подряд идущие дни с одинаковым графиком: «Пн–Пт 08:00–16:00, Сб 09:00–14:00»."""
    spec = obj.get("openingHoursSpecification")
    days: dict[int, tuple[str, str, str]] = {}
    if isinstance(spec, list):
        for s in spec:
            if not isinstance(s, dict):
                continue
            opens, closes = (s.get("opens") or "")[:5], (s.get("closes") or "")[:5]
            if not opens or not closes:
                continue
            dow = s.get("dayOfWeek")
            for d in (dow if isinstance(dow, list) else [dow]):
                key = str(d).rstrip("/").split("/")[-1].lower()
                if key in _DOW:
                    abbr, idx = _DOW[key]
                    days[idx] = (abbr, opens, closes)
    if not days:
        return ""
    items = sorted(days.items())               # [(idx,(abbr,opens,closes)), ...]
    out, i = [], 0
    while i < len(items):
        j = i
        while (j + 1 < len(items) and items[j + 1][0] == items[j][0] + 1
               and items[j + 1][1][1:] == items[i][1][1:]):
            j += 1
        a, b = items[i][1][0], items[j][1][0]
        opens, closes = items[i][1][1], items[i][1][2]
        span = a if i == j else f"{a}–{b}"
        # круглосуточно всю неделю → человеческая подпись
        if span == "Пн–Вс" and opens == "00:00" and closes in ("23:59", "24:00"):
            return "Круглосуточно"
        out.append(f"{span} {opens}–{closes}")
        i = j + 1
    return ", ".join(out)


def _localbusiness_meta(html: str) -> dict:
    """Имя/город/адрес/телефон/режим клиники из JSON-LD LocalBusiness страницы /pricing/.
    (geo там нет — его добираем из карточки главной через fetch_103kz_card.)"""
    meta = {"name": None, "city": None, "address": None, "phone": "", "working_hours": ""}
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        for obj in (data if isinstance(data, list) else [data]):
            if not isinstance(obj, dict) or obj.get("@type") != "LocalBusiness":
                continue
            addr = obj.get("address") or {}
            meta["name"] = obj.get("name") or meta["name"]
            if isinstance(addr, dict):
                meta["city"] = addr.get("addressLocality") or meta["city"]
                meta["address"] = addr.get("streetAddress") or meta["address"]
            tel = obj.get("telephone") or ""
            meta["phone"] = re.sub(r"\s+", " ", tel.split(",")[0].strip())
            meta["working_hours"] = _parse_hours(obj)
            return meta
    return meta


def fetch_pricing(slug: str) -> dict | None:
    """Дешёвый шаг (1 запрос): GET /pricing/ → имя+город+позиции, БЕЗ geo.

    Возвращает «сырую» запись с собственным ГОРОДОМ клиники (из LocalBusiness) —
    этого достаточно, чтобы решить, брать ли клинику (кэп по городу). Нет прайса
    в публичном доступе → None. geo добирается отдельно (enrich_geo), только если
    клинику берём — так не тратим 2-й запрос на отсеянные.
    """
    base = f"https://{slug}.103.kz"
    pricing = f"{base}/pricing/"
    try:
        html = polite_get(pricing, timeout=40.0).text
    except RobotsDisallowed:
        log.warning("103.kz[%s]: robots запрещает /pricing/", slug)
        return None
    except Exception as e:
        log.warning("103.kz[%s]: /pricing/ недоступен (%s)", slug, e)
        return None
    items = ws._103kz(html)
    if not items:  # нет прайса в публичном доступе — клинику не добавляем
        log.info("103.kz[%s]: позиций не найдено — пропуск", slug)
        return None
    meta = _localbusiness_meta(html)
    return {
        "slug": slug, "base": base, "source_url": pricing,
        "name": meta.get("name") or slug, "city": meta.get("city"),
        "address": meta.get("address"), "phone": meta.get("phone") or "",
        "working_hours": meta.get("working_hours") or "",
        "lat": None, "lng": None, "items": items,
    }


def enrich_geo(rec: dict) -> dict:
    """2-й запрос (GET /): контакты+geo из карточки главной. geo необязателен."""
    try:
        card = ws.fetch_103kz_card(f"{rec['base']}/") or {}
    except Exception as e:
        log.warning("103.kz[%s]: карточка недоступна (%s)", rec.get("slug"), e)
        card = {}
    rec["address"] = card.get("address") or rec.get("address")
    rec["phone"] = card.get("phone") or rec.get("phone") or ""
    rec["lat"] = card.get("lat")
    rec["lng"] = card.get("lng")
    return rec


def _block(rec: dict) -> dict:
    return {
        "clinic": {
            "name": rec["name"], "city": rec.get("city"),
            "address": rec.get("address"), "phone": rec.get("phone") or "",
            "working_hours": rec.get("working_hours") or "",
            "lat": rec.get("lat"), "lng": rec.get("lng"),
            "website": f"{rec['base']}/", "source_url": rec["source_url"],
        },
        "items": rec["items"],
    }


def harvest_one(slug: str, with_geo: bool = True) -> dict | None:
    """Снять одну клинику 103.kz → {clinic{...}, items} либо None (нет прайса)."""
    rec = fetch_pricing(slug)
    if rec is None:
        return None
    if with_geo:
        enrich_geo(rec)
    log.info("103.kz[%s]: %s (%s) — %d позиций",
             slug, rec["name"], rec.get("city"), len(rec["items"]))
    return _block(rec)


def harvest(slugs: list[str]) -> list[dict]:
    """Снять прайсы пачки клиник 103.kz. → [{clinic{...}, items:[RawItem]}]."""
    out: list[dict] = []
    for slug in slugs:
        block = harvest_one(slug)
        if block is not None:
            out.append(block)
    return out


def harvest_known(limit: int = len(KNOWN_SLUGS)) -> list[dict]:
    """Удобный вход на проверенном наборе slug'ов (без обхода каталога)."""
    return harvest(KNOWN_SLUGS[:limit])
