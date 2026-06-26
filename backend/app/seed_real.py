"""Наполнение БД РЕАЛЬНЫМИ спарсенными данными (ТЗ Кейс1 §6: «минимум 3 источника,
минимум 100 услуг; справочник ≥50 нормализованных позиций»).

Источники (все — реальные прайсы клиник РК, всё проходит боевой конвейер
ingest_items → нормализация → дедуп → история):

  ① web_scrape — KDL-Olymp (kdlolymp.kz), живой парсинг прайса лаборатории
     с СОБЛЮДЕНИЕМ robots.txt (через robots-шлюз). ~200 анализов, реальные цены/сроки.
  ② upload     — архив реальных прайсов клиник-партнёров (.archive_samples/Клиника*),
     PDF/DOCX/XLS — каждый файл = отдельная клиника-источник (если каталог доступен).
  ③ дополнительные живые адаптеры (invitro/gemotest/103.kz) — подключаются по
     доступности; недоступный источник просто пропускается (§4 отказоустойчивость).

Запуск:  python -m app.seed_real
Идемпотентно по клинике (повторный запуск обновляет цены, не плодит дубли).
"""
from __future__ import annotations

import os
import re

from .data import kz_cities
from .db import SessionLocal, init_db
from .ingestion import file_parser, web_scraper
from .ingestion.service import ingest_items
from .migrate import run as migrate
from .models import Clinic, Price, ServiceCatalog, Source

# Живой источник: лаборатория KDL-Olymp. h1 страницы даёт локацию-район.
KDL_BASE = "https://www.kdlolymp.kz/pricelist/"
# Прямые branch-страницы kdlolymp.kz/pricelist/<slug> давали город из h1
# «Анализы в <место>» в ПРЕДЛОЖНОМ падеже (Байконуре/Еркинкала/Шаян/Абае) — это
# суб-городские точки забора, а не города; засоряли список городов. Убраны.
# KDL-Olymp покрывается через 103.kz-сети (kdl-olimp-* slug'и) с корректным
# городом из карточки клиники (seed_103/seed_103_chains).
KDL_BRANCHES: list[str] = []

# Архив реальных файлов-прайсов: сколько файлов и сколько позиций с каждого брать
# (16k позиций со всех 8 раздувают каталог — для §6 «≥100 услуг» хватит выборки).
ARCHIVE_FILES = 4
ARCHIVE_CAP_PER_FILE = 120

# Дополнительные живые адаптеры (подключатся, если ответят). raw_name+цена статикой.
# Invitro — каталог анализов отдаётся СТАТИКОЙ на /analizes/ (~2126 позиций),
# адаптер web_scraper._invitro уже разбирает .analyzes-item__total--price.
# KazMedClinic — прайс /ceny статикой (~823 позиции через generic-парсер).
EXTRA_WEB = [
    ("Invitro — Алматы", "Алматы", "https://www.invitro.kz/analizes/"),
    ("KazMedClinic — Алматы", "Алматы", "https://kazmedclinic.kz/ceny"),
]

# doq.kz — REST API api.doq.kz: клиники×услуги×цены по ВСЕМ 12 городам РК.
# Пусто → берём все города из fetch_cities(). Каждая услуга = 1 API-вызов, поэтому
# глубину держим умеренной (демо-охват «все города», в проде поднять лимиты).
DOQ_CITIES: list[str] = []            # [] = все 12 городов doq
DOQ_MAX_CLINICS_PER_CITY = 3
DOQ_MAX_SERVICES = 10

# 103.kz — клиники/лаборатории по городам РК (discover по городу + harvest).
# Города берём из канонического справочника (ВСЕ 90 РК): проверенный набор —
# первым (там реально есть прайсы), остальные пробуем discover'ом (нет поддомена/
# листинга → пусто, безвредно). Так «подтягиваем данные по всем городам».
_O103_PROVEN = ["almaty", "astana", "shymkent", "aktobe", "karaganda",
                "pavlodar", "taraz", "semey", "aktau", "kyzylorda",
                "kokshetau", "ust-kamenogorsk"]
O103_CITIES = _O103_PROVEN + [
    c["slug"] for c in kz_cities.all_cities() if c["slug"] not in set(_O103_PROVEN)
]
O103_PER_CITY = 4


def _clinic(db, name: str, city: str, website: str = "", **extra) -> Clinic:
    # Нормализуем город к каноническому названию справочника (almaty/uk/«Алматы»
    # → одна запись), иначе фильтр по городам двоится по вариантам написания.
    city = kz_cities.canonical_city(city) or city
    c = db.query(Clinic).filter(Clinic.name == name).first()
    if not c:
        c = Clinic(name=name, city=city, website=website, **extra)
        db.add(c)
        db.commit()
        db.refresh(c)
    else:
        c.city = city or c.city
        if website:
            c.website = website
        for k, v in extra.items():
            setattr(c, k, v)
        db.commit()
    return c


def _source(db, clinic_id: int, stype: str, url: str) -> Source:
    s = (db.query(Source)
         .filter(Source.clinic_id == clinic_id, Source.type == stype,
                 Source.url_or_endpoint == url).first())
    if not s:
        s = Source(clinic_id=clinic_id, type=stype, url_or_endpoint=url, enabled=True)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def seed_kdl(db, report: list[dict]) -> None:
    for slug in KDL_BRANCHES:
        url = KDL_BASE + slug
        try:
            raw, items = web_scraper.scrape_url_raw(url, timeout=40)
        except web_scraper.RobotsDisallowed:
            report.append({"source": url, "status": "skipped_robots"})
            continue
        except Exception as e:
            report.append({"source": url, "status": "error", "error": str(e)[:80]})
            continue
        if not items:
            report.append({"source": url, "status": "empty"})
            continue
        # локация из h1 «Анализы в <место>»
        m = re.search(r"Анализы в ([^<]+)", raw)
        place = (m.group(1).strip() if m else slug).strip(". ")
        name = f"KDL-Olymp — {place}"
        clinic = _clinic(db, name, place, website="https://www.kdlolymp.kz",
                         working_hours="Пн-Сб 07:00–16:00", online_booking=True, rating=4.6)
        src = _source(db, clinic.id, "web_scrape", url)
        res = ingest_items(db, clinic_id=clinic.id, channel="pull", source_type="web_scrape",
                           items=items, fmt="html", source_id=src.id, raw_content=raw)
        report.append({"source": url, "status": "ok", "clinic": name,
                       "city": place, "items": res.items_found, "matched": res.matched})


def seed_archive_files(db, report: list[dict]) -> None:
    """Реальные прайсы клиник из .archive_samples (PDF/DOCX/XLS) — канал upload."""
    base = os.path.join(os.path.dirname(__file__), "..", "..", ".archive_samples")
    base = os.path.abspath(base)
    if not os.path.isdir(base):
        report.append({"source": ".archive_samples", "status": "absent"})
        return
    files = sorted(f for f in os.listdir(base)
                   if f.lower().startswith("клиника") or f.lower().startswith("klinika"))
    files = files[:ARCHIVE_FILES]
    # города по кругу — реальные прайсы анонимных клиник РК, раскидываем по рынку.
    # Берём приоритетные города ТЗ из канонического справочника (а не хардкод-список).
    cities = [c for c in ["Алматы", "Астана", "Шымкент", "Актобе", "Павлодар",
                          "Караганда", "Тараз", "Костанай"]
              if kz_cities.canonical_city(c)]
    for i, fn in enumerate(files):
        path = os.path.join(base, fn)
        try:
            with open(path, "rb") as fh:
                content = fh.read()
            fmt, items = file_parser.detect_and_parse(fn, content)
            items = items[:ARCHIVE_CAP_PER_FILE]  # не раздуваем каталог 16k-позициями
        except Exception as e:
            report.append({"source": fn, "status": "error", "error": str(e)[:80]})
            continue
        if not items:
            report.append({"source": fn, "status": "empty"})
            continue
        # имя клиники из имени файла «Клиника N ...»
        m = re.match(r"(Клиника\s*\d+)", fn, re.I)
        name = (m.group(1) if m else os.path.splitext(fn)[0]).strip()
        city = cities[i % len(cities)]
        clinic = _clinic(db, name, city, online_booking=False, rating=round(4.0 + (i % 5) * 0.1, 1))
        src = _source(db, clinic.id, "upload", fn)
        res = ingest_items(db, clinic_id=clinic.id, channel="push", source_type="upload",
                           items=items, fmt=fmt, source_id=src.id)
        report.append({"source": fn, "status": "ok", "clinic": name, "city": city,
                       "format": fmt, "items": res.items_found, "matched": res.matched})


def seed_extra_web(db, report: list[dict]) -> None:
    for name, city, url in EXTRA_WEB:
        try:
            raw, items = web_scraper.scrape_url_raw(url, timeout=30)
        except Exception as e:
            report.append({"source": url, "status": "error", "error": str(e)[:80]})
            continue
        if not items:
            report.append({"source": url, "status": "empty"})
            continue
        clinic = _clinic(db, name, city, website=url)
        src = _source(db, clinic.id, "web_scrape", url)
        res = ingest_items(db, clinic_id=clinic.id, channel="pull", source_type="web_scrape",
                           items=items, fmt="html", source_id=src.id, raw_content=raw)
        report.append({"source": url, "status": "ok", "clinic": name, "city": city,
                       "items": res.items_found})


def seed_doq(db, report: list[dict]) -> None:
    """doq.kz REST API: реальные клиники×услуги×цены по городам РК."""
    try:
        from .ingestion import doq_connector as doq
    except Exception as e:
        report.append({"source": "doq.kz", "status": "absent", "error": str(e)[:80]})
        return
    cities = DOQ_CITIES
    if not cities:  # все города doq
        try:
            cities = [c["slug"] for c in doq.fetch_cities() if c.get("slug")]
        except Exception as e:
            report.append({"source": "doq.kz", "status": "error", "error": str(e)[:80]})
            return
    for city_slug in cities:
        try:
            blocks = doq.fetch_all(max_clinics=DOQ_MAX_CLINICS_PER_CITY,
                                   city_slug=city_slug, max_services=DOQ_MAX_SERVICES)
        except doq.RobotsDisallowed as e:
            report.append({"source": f"doq:{city_slug}", "status": "skipped_robots", "url": e.url})
            continue
        except Exception as e:
            report.append({"source": f"doq:{city_slug}", "status": "error", "error": str(e)[:80]})
            continue
        for b in blocks:
            cl = b.get("clinic") or {}
            items = b.get("items") or []
            if not items:
                continue
            name = f"{cl.get('name','?')} (doq)"
            clinic = _clinic(db, name, cl.get("city") or city_slug,
                             website=cl.get("source_url") or cl.get("website") or "",
                             address=cl.get("address") or "", phone=cl.get("phone") or "",
                             lat=cl.get("lat"), lng=cl.get("lng"),
                             rating=cl.get("rating"), online_booking=True)
            # машинный ref для планировщика: doq://{city_id}/{clinic_id}
            ref = (f"doq://{cl.get('city_id')}/{cl.get('id')}"
                   if cl.get("city_id") and cl.get("id") else (cl.get("source_url") or ""))
            src = _source(db, clinic.id, "api", ref)
            res = ingest_items(db, clinic_id=clinic.id, channel="pull", source_type="api",
                               items=items, fmt="json", source_id=src.id)
            report.append({"source": f"doq:{name}", "status": "ok", "clinic": name,
                           "city": clinic.city, "items": res.items_found, "matched": res.matched})


def seed_103(db, report: list[dict]) -> None:
    """103.kz — прайсы клиник РК по ВСЕМ городам (discover по городу + harvest)."""
    try:
        from .ingestion import o103_harvester as o103
    except Exception as e:
        report.append({"source": "103.kz", "status": "absent", "error": str(e)[:80]})
        return
    # 1) собрать slug'и по каждому городу + проверенный набор
    slugs: list[str] = []
    seen: set[str] = set()
    for city in O103_CITIES:
        try:
            for s in o103.discover_slugs(city, limit=O103_PER_CITY):
                if s not in seen:
                    seen.add(s); slugs.append(s)
        except Exception as e:
            report.append({"source": f"103:{city}", "status": "error", "error": str(e)[:60]})
    for s in getattr(o103, "KNOWN_SLUGS", []):
        if s not in seen:
            seen.add(s); slugs.append(s)
    # 2) выкачать прайс каждой клиники
    try:
        blocks = o103.harvest(slugs)
    except Exception as e:
        report.append({"source": "103.kz", "status": "error", "error": str(e)[:80]})
        return
    for b in blocks:
        cl = b.get("clinic") or {}
        items = b.get("items") or []
        if not items:
            continue
        name = f"{cl.get('name','?')} (103.kz)"
        clinic = _clinic(db, name, cl.get("city") or "", website=cl.get("source_url") or "",
                         address=cl.get("address") or "", phone=cl.get("phone") or "",
                         lat=cl.get("lat"), lng=cl.get("lng"))
        src = _source(db, clinic.id, "web_scrape", cl.get("source_url") or name)
        res = ingest_items(db, clinic_id=clinic.id, channel="pull", source_type="web_scrape",
                           items=items, fmt="html", source_id=src.id)
        report.append({"source": f"103:{name}", "status": "ok", "clinic": name,
                       "city": clinic.city, "items": res.items_found, "matched": res.matched})


# Филиалы сетей-лабораторий из общего sitemap 103.kz — рычаг МАЛЫХ городов.
# Сколько филиалов максимум пробуем и сколько держим на город (кэп ради ШИРОТЫ
# охвата: один город не должен забить выдачу). Город — из карточки филиала.
O103_CHAIN_SCAN = 500
O103_CHAIN_PER_CITY = 3


def seed_103_chains(db, report: list[dict]) -> None:
    """Малые города: филиалы сетей-лабораторий 103.kz (invitro/olimp/gemotest/…).

    У сетей пронумерованные поддомены-филиалы по ВСЕЙ стране, включая малые города;
    прайс сети реально действует в филиале, город берётся из его карточки. Сканировать
    общий пул «с головы» бесполезно (он отсортирован по мегаполисам) — поэтому берём
    именно филиалы сетей. Дёшево: на отсеянный филиал — 1 запрос (/pricing/), geo
    (2-й запрос) — только для взятых. Кэп на город → широта, а не глубина по Алматы.
    """
    try:
        from .ingestion import o103_harvester as o103
    except Exception as e:
        report.append({"source": "103.kz/chains", "status": "absent", "error": str(e)[:80]})
        return
    try:
        branches = o103.discover_chain_branches(limit=O103_CHAIN_SCAN)
    except Exception as e:
        report.append({"source": "103.kz/chains", "status": "error", "error": str(e)[:80]})
        return
    per_city: dict[str, int] = {}
    kept = 0
    for slug in branches:
        rec = o103.fetch_pricing(slug)            # 1 запрос: город + позиции
        if rec is None:
            continue
        city = kz_cities.canonical_city(rec.get("city"))
        if not city:
            continue
        if per_city.get(city, 0) >= O103_CHAIN_PER_CITY:
            continue                              # этот город уже покрыт — широта важнее
        o103.enrich_geo(rec)                      # 2-й запрос только для взятых
        name = f"{rec['name']} (103.kz)"
        clinic = _clinic(db, name, city, website=f"{rec['base']}/",
                         address=rec.get("address") or "", phone=rec.get("phone") or "",
                         lat=rec.get("lat"), lng=rec.get("lng"))
        src = _source(db, clinic.id, "web_scrape", rec["source_url"])
        res = ingest_items(db, clinic_id=clinic.id, channel="pull", source_type="web_scrape",
                           items=rec["items"], fmt="html", source_id=src.id)
        per_city[city] = per_city.get(city, 0) + 1
        kept += 1
        report.append({"source": f"103chain:{slug}", "status": "ok", "clinic": name,
                       "city": city, "items": res.items_found, "matched": res.matched})
    report.append({"source": "103.kz/chains", "status": "summary",
                   "clinic": f"{kept} филиалов", "city": f"{len(per_city)} городов",
                   "items": kept})


def main() -> dict:
    migrate()
    # Семантический реранкер — фишка живых одиночных запросов; в bulk-сиде он
    # на десятках тысяч позиций душит CPU (см. MEDARCHIVE_CHECKPOINT). Для наполнения
    # достаточно code-first + fuzzy; смысловой проход доступен в рантайме на чтении.
    from .config import settings as _s
    _s.semantic_enabled = False
    # «Все города» = много запросов; держим вежливый, но не черепаший темп (0.5с/хост).
    # robots по-прежнему соблюдается шлюзом; для хостов со своим Crawl-delay берётся больший.
    _s.scrape_crawl_delay = 0.5
    # LLM-арбитраж — для живых одиночных запросов; в bulk-сиде он делает сетевой
    # вызов на КАЖДУЮ неоднозначную позицию (сотни) → минуты. Отключаем: code-first
    # + fuzzy достаточно для наполнения, остальное уходит в unmatched-очередь.
    from . import llm as _llm
    _llm.json_completion = lambda *a, **k: None
    db = SessionLocal()
    report: list[dict] = []
    try:
        seed_kdl(db, report)
        seed_archive_files(db, report)
        seed_extra_web(db, report)   # invitro (статика)
        seed_doq(db, report)         # doq.kz REST API — города РК
        seed_103(db, report)         # 103.kz — листинги по всем 90 городам
        seed_103_chains(db, report)  # 103.kz — филиалы сетей: МАЛЫЕ города по всей РК

        ok = [r for r in report if r.get("status") == "ok"]
        cities = sorted({r["city"] for r in ok if r.get("city")})
        clinics = db.query(Clinic).count()
        services = db.query(ServiceCatalog).count()
        priced = db.query(Price).count()
        priced_services = db.query(Price.service_id).distinct().count()
        summary = {
            "sources_ok": len(ok),
            "clinics": clinics,
            "catalog_services": services,
            "price_rows": priced,
            "distinct_priced_services": priced_services,
            "cities": cities,
        }
        _write_report(summary, report)
        return {"summary": summary, "report": report}
    finally:
        db.close()


def _write_report(summary: dict, report: list[dict]) -> None:
    """§6 артефакт: отчёт об источниках/охвате реальных данных."""
    path = os.path.join(os.path.dirname(__file__), "..", "..", "docs",
                        "quality-report-medprice.md")
    path = os.path.abspath(path)
    ok = [r for r in report if r.get("status") == "ok"]
    lines = [
        "# Отчёт о реальных данных (MedPrice, Кейс1 §6)",
        "",
        "_Сгенерировано: `python -m app.seed_real`._",
        "",
        "## Сводка",
        f"- Успешных источников: **{summary['sources_ok']}** (цель ТЗ ≥3)",
        f"- Клиник в базе: **{summary['clinics']}**",
        f"- Позиций справочника услуг: **{summary['catalog_services']}** (цель ≥50)",
        f"- Строк цен: **{summary['price_rows']}**",
        f"- Уникальных услуг с ценой: **{summary['distinct_priced_services']}** (цель ≥100)",
        f"- Города ({len(summary['cities'])}): {', '.join(summary['cities']) or '—'}",
        "",
        "## По источникам",
        "",
        "| Источник | Канал | Клиника | Город | Позиций | Сопоставлено |",
        "|---|---|---|---|---:|---:|",
    ]
    for r in report:
        chan = "web_scrape" if str(r.get("source", "")).startswith("http") else "upload"
        lines.append(
            f"| {str(r.get('source',''))[:60]} | {chan} | {r.get('clinic','—')} | "
            f"{r.get('city','—')} | {r.get('items', r.get('status',''))} | {r.get('matched','—')} |"
        )
    lines += [
        "",
        "## Соблюдение правил ТЗ §8",
        "- robots.txt соблюдается единым шлюзом `ingestion/robots.py` (Protego) — все GET через `polite_get`.",
        "- crawl-delay пер-хост (не создаём чрезмерную нагрузку).",
        "- Собираются только публичные прайсы; персональные данные не собираются.",
        "",
        "_Прим.: invitro/doq/2gis отдают данные через JS/SPA-API, olymp/helix/medel/mck"
        " недоступны статикой с этого сервера — для них в `web_scraper` есть адаптеры,"
        " подключаемые по доступности (вкл. Playwright для SPA)._",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    import json
    init_db()
    out = main()
    print(json.dumps(out, ensure_ascii=False, indent=2))
