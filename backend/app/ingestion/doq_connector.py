"""Коннектор к публичному REST API агрегатора клиник doq.kz (канал ② pull).

doq.kz — крупнейший в РК агрегатор «врач + клиника + запись на приём». Под капотом
у фронта (Vite SPA) лежит Django REST Framework на `https://api.doq.kz/api/v1/`
(пагинация `?limit=&offset=`, ответ `{count,next,previous,results}`). Этот модуль —
тонкая обёртка, которая достаёт оттуда города, клиники (с адресом/телефоном/гео) и,
главное, ЦЕНЫ услуг по каждой клинике, приводя их к нашему `RawItem`.

Где в API лежит цена (результат разведки):
  • эндпоинты `/clinics/{id}/services|prices`, `/procedure-prices/`, `/prices/` — 404;
  • прайс отдаёт АГРЕГИРУЮЩИЙ эндпоинт `GET /doctors-meta/?city=<id>&service=<id>`:
    `{count, currency:"Тенге", min_price, max_price, max_discount, ...}` — это диапазон
    цен по услуге в городе среди всех врачей/клиник;
  • тот же эндпоинт принимает `&clinic=<id>` и сужает диапазон до КОНКРЕТНОЙ клиники —
    так получаем связку клиника × услуга × цена (например clinic=105 «ЭМИРМЕД»,
    service=829 «3D УЗИ плода» → min_price=14000, max_price=16000 ₸).
  • как «цену услуги» в клинике берём `min_price` (то, что на сайте показано как
    «от N ₸»); `max_price` сохраняем в `duration_days`? — нет, это срок, не трогаем.

Каталог услуг клиники — `GET /services/?clinic=<id>` (список услуг без цен), города —
`GET /cities/` (city.id числовой, в фильтрах нужен именно id, slug даёт 400), адрес и
телефон клиники — `GET /clinic-branches/?clinic=<id>` (у клиники может быть несколько
филиалов, берём первый как основной).

Вежливость: ВСЕ сетевые GET идут через `robots.polite_get` (проверка robots.txt +
crawl-delay пер-хост). robots.txt у api.doq.kz отсутствует (404) → краулерам разрешено
всё, но шлюз всё равно соблюдаем. Объём ограничиваем параметрами (max_clinics,
max_services) — не выкачиваем все 528 клиник × 1348 услуг в демо.
"""
from __future__ import annotations

from urllib.parse import urlencode

from .file_parser import RawItem
from .robots import RobotsDisallowed, polite_get

API_BASE = "https://api.doq.kz/api/v1"
SITE_BASE = "https://doq.kz"
# DRF отдаёт цены строкой "Тенге" — в наших RawItem валюта в ISO-коде.
CURRENCY = "KZT"

# Дефолтные лимиты вежливости: не бомбим API и не тянем весь каталог в демо.
_DEFAULT_MAX_CLINICS = 30
_DEFAULT_MAX_SERVICES = 40
# Размер страницы пагинации DRF.
_PAGE = 50


# --------------------------------------------------------------------------- #
#  Низкоуровневый доступ к API (через вежливый шлюз)
# --------------------------------------------------------------------------- #
def _url(path: str, **params) -> str:
    """Собирает URL эндпоинта с query-параметрами (пустые значения отбрасываются)."""
    q = {k: v for k, v in params.items() if v is not None}
    qs = ("?" + urlencode(q)) if q else ""
    return f"{API_BASE}/{path.lstrip('/')}{qs}"


def _get_json(path: str, **params) -> dict | list:
    """GET к API doq.kz через polite_get. RobotsDisallowed пробрасываем наверх
    (значит путь запрещён robots.txt — выше решат, что делать)."""
    resp = polite_get(_url(path, **params))
    resp.raise_for_status()
    return resp.json()


def _paginate(path: str, *, limit: int | None = None, **params):
    """Итерирует записи DRF-пагинации `{count,next,results}`. `limit` — мягкий
    потолок на ОБЩЕЕ число записей (вежливость), None = все страницы."""
    offset = 0
    yielded = 0
    while True:
        page_size = _PAGE
        if limit is not None:
            page_size = min(_PAGE, limit - yielded)
            if page_size <= 0:
                return
        data = _get_json(path, limit=page_size, offset=offset, **params)
        if not isinstance(data, dict):
            return
        results = data.get("results") or []
        for row in results:
            yield row
            yielded += 1
            if limit is not None and yielded >= limit:
                return
        if not data.get("next") or not results:
            return
        offset += len(results)


# --------------------------------------------------------------------------- #
#  Города
# --------------------------------------------------------------------------- #
def parse_city(row: dict) -> dict:
    """city из API → наш плоский dict (id, name, slug, lat, lng)."""
    loc = row.get("location") or {}
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "slug": row.get("slug"),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
    }


def fetch_cities() -> list[dict]:
    """Список городов РК с координатами (12 шт.: Алматы, Астана, ...)."""
    return [parse_city(r) for r in _paginate("cities/")]


def _city_index() -> dict[str, dict]:
    """Индекс slug → город (для резолва city_slug в числовой id фильтров)."""
    return {c["slug"]: c for c in fetch_cities() if c.get("slug")}


# --------------------------------------------------------------------------- #
#  Клиники (+ адрес/телефон/гео из основного филиала)
# --------------------------------------------------------------------------- #
def _first_branch(clinic_id: int, city_id: int | None = None) -> dict | None:
    """Первый (основной) филиал клиники — носитель адреса/телефонов/координат."""
    for b in _paginate("clinic-branches/", limit=1, clinic=clinic_id, city=city_id):
        return b
    # филиал в заданном городе не найден — берём любой
    if city_id is not None:
        for b in _paginate("clinic-branches/", limit=1, clinic=clinic_id):
            return b
    return None


def parse_clinic(row: dict, branch: dict | None, city: dict | None) -> dict:
    """Собирает наш dict клиники из объекта clinics/ + его филиала + города."""
    branch = branch or {}
    loc = branch.get("location") or {}
    phones = branch.get("phones") or []
    phone = phones[0] if phones else branch.get("direct_call_phone")
    slug = row.get("slug")
    city_slug = (city or {}).get("slug")
    # Канонический URL карточки на сайте: doq.kz/<город>/clinic/<slug>.
    source_url = f"{SITE_BASE}/{city_slug}/clinic/{slug}" if city_slug and slug else (
        f"{SITE_BASE}/clinic/{slug}" if slug else SITE_BASE
    )
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "slug": slug,
        "city": (city or {}).get("name"),
        "city_id": (city or {}).get("id") or branch.get("city"),
        "address": branch.get("address"),
        "phone": phone,
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "rating": row.get("feedback_score"),
        "source_url": source_url,
        "website": source_url,
    }


def fetch_clinics(city_slug: str | None = None, limit: int | None = None) -> list[dict]:
    """Клиники (по городу, если задан city_slug) с адресом/телефоном/гео/рейтингом.

    Чтобы не делать N+1 запросов за филиалами, при заданном городе один раз тянем
    все филиалы города и строим индекс clinic_id → филиал.
    """
    cities = _city_index()
    city = cities.get(city_slug) if city_slug else None
    city_id = city["id"] if city else None

    # Индекс филиалов по клинике (по городу — оптом; иначе добираем поштучно ниже).
    branch_by_clinic: dict[int, dict] = {}
    if city_id is not None:
        for b in _paginate("clinic-branches/", city=city_id):
            cid = b.get("clinic")
            if cid is not None and cid not in branch_by_clinic:
                branch_by_clinic[cid] = b

    out: list[dict] = []
    for row in _paginate("clinics/", limit=limit, city=city_id):
        cid = row.get("id")
        branch = branch_by_clinic.get(cid)
        if branch is None:
            branch = _first_branch(cid, city_id)
        out.append(parse_clinic(row, branch, city))
    return out


# --------------------------------------------------------------------------- #
#  Цены: услуга × клиника → RawItem
# --------------------------------------------------------------------------- #
def _clinic_city_id(clinic: dict) -> int | None:
    """Достаёт city_id из dict клиники (или добирает из её филиала)."""
    cid = clinic.get("city_id")
    if cid is not None:
        return cid
    branch = _first_branch(clinic.get("id"))
    return (branch or {}).get("city")


def fetch_prices(clinic: dict, max_services: int = _DEFAULT_MAX_SERVICES) -> list[RawItem]:
    """Позиции «услуга + цена» для одной клиники.

    Алгоритм: каталог услуг клиники (`services/?clinic=`) × агрегатор цен
    (`doctors-meta/?city=&service=&clinic=`). Цена услуги = `min_price` («от N ₸»).
    Услуги без цены (на сайте «по записи»/walk-in, min_price=null) пропускаем.
    """
    clinic_id = clinic.get("id")
    if clinic_id is None:
        return []
    city_id = _clinic_city_id(clinic)
    if city_id is None:
        return []

    items: list[RawItem] = []
    for svc in _paginate("services/", limit=max_services, clinic=clinic_id):
        sid = svc.get("id")
        name = (svc.get("name") or "").strip()
        if sid is None or len(name) < 2:
            continue
        meta = _get_json(
            "doctors-meta/", city=city_id, service=sid, clinic=clinic_id
        )
        price = meta.get("min_price") if isinstance(meta, dict) else None
        if not price or price <= 0:
            continue
        items.append(RawItem(raw_name=name, price=float(price), currency=CURRENCY))
    return items


# --------------------------------------------------------------------------- #
#  Высокоуровневый сборщик для сидинга
# --------------------------------------------------------------------------- #
def fetch_all(
    max_clinics: int = _DEFAULT_MAX_CLINICS,
    *,
    city_slug: str | None = "almaty",
    max_services: int = _DEFAULT_MAX_SERVICES,
) -> list[dict]:
    """[{clinic:{...}, items:[RawItem,...]}] — клиники с прайсом, готово для сидинга.

    По умолчанию берём Алматы (самый полный каталог цен) и не более max_clinics
    клиник. Ошибка/запрет по одной клинике не валит весь сбор.
    """
    out: list[dict] = []
    for clinic in fetch_clinics(city_slug=city_slug, limit=max_clinics):
        try:
            items = fetch_prices(clinic, max_services=max_services)
        except RobotsDisallowed:
            raise
        except Exception:
            items = []
        out.append({"clinic": clinic, "items": items})
    return out
