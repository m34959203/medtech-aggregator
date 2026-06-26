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


def _localbusiness_meta(html: str) -> dict:
    """Имя/город/адрес/телефон клиники из JSON-LD LocalBusiness страницы /pricing/.
    (geo там нет — его добираем из карточки главной через fetch_103kz_card.)"""
    meta = {"name": None, "city": None, "address": None, "phone": ""}
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
            return meta
    return meta


def harvest(slugs: list[str]) -> list[dict]:
    """Снять прайсы пачки клиник 103.kz.

    На каждый slug: GET /pricing/ (позиции + имя/город из LocalBusiness) и GET /
    (контакты+geo через web_scraper.fetch_103kz_card). Клиники без позиций
    пропускаем (нет публичного прайса). → [{clinic{...}, items:[RawItem]}].
    """
    out: list[dict] = []
    for slug in slugs:
        base = f"https://{slug}.103.kz"
        pricing = f"{base}/pricing/"
        try:
            html = polite_get(pricing, timeout=40.0).text
        except RobotsDisallowed:
            log.warning("103.kz[%s]: robots запрещает /pricing/", slug)
            continue
        except Exception as e:
            log.warning("103.kz[%s]: /pricing/ недоступен (%s)", slug, e)
            continue

        items = ws._103kz(html)
        if not items:  # нет прайса в публичном доступе — клинику не добавляем
            log.info("103.kz[%s]: позиций не найдено — пропуск", slug)
            continue

        meta = _localbusiness_meta(html)
        try:
            card = ws.fetch_103kz_card(f"{base}/") or {}
        except Exception as e:  # geo — необязательно, не валим клинику
            log.warning("103.kz[%s]: карточка недоступна (%s)", slug, e)
            card = {}

        clinic = {
            "name": meta.get("name") or slug,
            "city": meta.get("city"),
            "address": card.get("address") or meta.get("address"),
            "phone": card.get("phone") or meta.get("phone") or "",
            "lat": card.get("lat"),
            "lng": card.get("lng"),
            "website": f"{base}/",
            "source_url": pricing,
        }
        out.append({"clinic": clinic, "items": items})
        log.info("103.kz[%s]: %s (%s) — %d позиций",
                 slug, clinic["name"], clinic["city"], len(items))
    return out


def harvest_known(limit: int = len(KNOWN_SLUGS)) -> list[dict]:
    """Удобный вход на проверенном наборе slug'ов (без обхода каталога)."""
    return harvest(KNOWN_SLUGS[:limit])
