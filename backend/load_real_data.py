"""Загрузка РЕАЛЬНЫХ клиник и их живых прайсов (вместо демо-сида).

Скрапит публичные прайс-страницы реальных лабораторий и клиник Алматы/Астаны
через те же адаптеры web_scraper, что и боевой канал /api/ingest/scrape, и
прогоняет позиции через нормализацию (ingest_items). Для лабораторий берётся
курируемый срез популярных анализов — чтобы витрина сравнения была наглядной.

Запуск (внутри контейнера бэка):  python load_real_data.py
Источники проверены в июне 2026; селекторы могут устареть при редизайне сайтов.
"""
from __future__ import annotations

from datetime import date

from app.db import SessionLocal, init_db
from app.ingestion.web_scraper import (
    fetch_103kz_card,
    fetch_contact,
    scrape_lab_platform,
    scrape_url,
)
from app.models import Clinic, Price, ServiceCatalog

# ДЕТЕРМИНИРОВАННАЯ карта «ключ в сыром названии → эталон». Курация уже знает
# специальность/аналит по ключу, поэтому привязываем к эталону напрямую, минуя
# fuzzy-нормализатор (без LLM он путал специалистов: ЛОР→гинеколог, дробил
# ЭКГ/Электрокардиограмму на два каноне и т.п.). Порядок ВАЖЕН — первый матч
# выигрывает; require — обязательная доп-подстрока, exclude — стоп-слова.
# (keyword, canonical, category, require, excludes)
_AN, _P, _UZ, _PR, _MR = "Анализы", "Приём врача", "УЗИ", "Процедуры", "МРТ/КТ"
# Приём = только консультация (а не процедура/операция «у гинеколога»).
_CONSULT = ("прием", "приём", "консультац", "осмотр")
_UZI = ("узи", "ультразвук")
# Стоп-слова: панели/комплексы (чтобы аналит не ловил «Анемия (…Ферритин…)»)
# и операции/процедуры у специалиста (чтобы приём не ловил хирургию).
_PANEL = ("комплекс", "профил", "пакет", "скрининг", "программ", "анемия",
          "check", "чек-ап", "обследование", "диспансер")
_PROC = ("операц", "удаление", "биопси", "пункци", "инъекц", "блокад", "массаж",
         "prp", "плазмолифт", "склеротерап", "вмешательств", "манипул", "забор",
         "мазок", "лечение", "выскаблив", "прижигани", "коагул", "эксцизи")
# Сравниваем сопоставимое: только ПЕРВИЧНЫЙ взрослый приём (не повторный/онлайн/
# детский), иначе «Лучшая цена» врёт (повторный/онлайн дешевле первичного).
_NONPRIM = ("повторн", "онлайн", "детск", "дистанц", "телемед", "на дому",
            "вызов", "выезд", "видеоконсульт")
_PRIEM_EX = _PROC + _NONPRIM
SPECS: list[tuple[str, str, str, tuple[str, ...], tuple[str, ...]]] = [
    # — Сердце: ЭхоКГ раньше ЭКГ, чтобы «УЗИ сердца с ЭКГ» не ушло в ЭКГ —
    ("эхокардиограф", "ЭхоКГ (эхокардиография)", _PR, (), ()),
    ("эхокг", "ЭхоКГ (эхокардиография)", _PR, (), ()),
    ("узи сердца", "ЭхоКГ (эхокардиография)", _PR, (), ()),
    ("электрокардиограмма", "ЭКГ", _PR, (), ("суточн", "холтер", "узи", "эхо")),
    ("экг", "ЭКГ", _PR, (), ("суточн", "холтер", "узи", "эхо", "велоэрго", "тредмил")),
    # — УЗИ органов (только если есть «узи»/«ультразвук») —
    ("брюшной полости", "УЗИ брюшной полости", _UZ, _UZI, ("обзорное",)),
    ("почек", "УЗИ почек", _UZ, _UZI, ()),
    ("щитовид", "УЗИ щитовидной железы", _UZ, _UZI, ()),
    ("малого таза", "УЗИ органов малого таза", _UZ, _UZI, ()),
    ("молочных желез", "УЗИ молочных желёз", _UZ, _UZI, ()),
    # — Приёмы: только консультация (require), без процедур (exclude) —
    ("кардиолог", "Приём кардиолога", _P, _CONSULT, _PRIEM_EX),
    ("гинеколог", "Приём гинеколога", _P, _CONSULT, _PRIEM_EX),
    ("невропатолог", "Приём невролога", _P, _CONSULT, _PRIEM_EX),
    ("невролог", "Приём невролога", _P, _CONSULT, _PRIEM_EX),
    ("офтальмолог", "Приём офтальмолога", _P, _CONSULT, _PRIEM_EX),
    ("окулист", "Приём офтальмолога", _P, _CONSULT, _PRIEM_EX),
    ("эндокринолог", "Приём эндокринолога", _P, _CONSULT, _PRIEM_EX),
    ("дерматолог", "Приём дерматолога", _P, _CONSULT, _PRIEM_EX),
    ("уролог", "Приём уролога", _P, _CONSULT, _PRIEM_EX),
    ("оторинолар", "Приём ЛОР-врача", _P, _CONSULT, _PRIEM_EX),
    ("лор-врач", "Приём ЛОР-врача", _P, _CONSULT, _PRIEM_EX),
    ("терапевт", "Приём терапевта", _P, _CONSULT,
     _PRIEM_EX + ("физиотерап", "психотерап", "стоматолог", "мануальн", "озонотерап")),
    # — МРТ/КТ (диагностические центры) —
    ("мрт головного мозга", "МРТ головного мозга", _MR, (), ("сосуд", "контраст", "гипофиз", "+")),
    ("магнитно-резонансная томография головного мозга", "МРТ головного мозга", _MR, (),
     ("сосуд", "контраст", "гипофиз", "+")),
    ("кт головного мозга", "КТ головного мозга", _MR, (), ("контраст", "сосуд", "+")),
    ("компьютерная томография головного мозга", "КТ головного мозга", _MR, (), ("контраст", "сосуд", "+")),
    # — Анализы: один аналит, не панель (_PANEL в excludes) —
    ("клинический анализ крови", "Общий анализ крови", _AN, (), ()),
    ("общий анализ крови", "Общий анализ крови", _AN, (), ()),
    ("общий анализ мочи", "Общий анализ мочи", _AN, (), ()),
    ("гликированный", "Гликированный гемоглобин (HbA1c)", _AN, (), _PANEL),
    ("гликозилированный", "Гликированный гемоглобин (HbA1c)", _AN, (), _PANEL),
    ("hba1c", "Гликированный гемоглобин (HbA1c)", _AN, (), _PANEL),
    ("глюкоза", "Глюкоза (в крови)", _AN, (),
     _PANEL + ("толерант", "нагруз", "ликвор", "homa", "инсулин", "индекс")),
    ("сахар крови", "Глюкоза (в крови)", _AN, (), _PANEL),
    ("холестерин общий", "Холестерин общий", _AN, (), _PANEL),
    ("витамин d", "Витамин D", _AN, (), _PANEL + ("дигидрокси", "1,25", "25-он", "25(он")),
    ("ферритин", "Ферритин", _AN, (), _PANEL),
    ("тиреотропный", "ТТГ (тиреотропный гормон)", _AN, (), _PANEL),
    ("тиротропин", "ТТГ (тиреотропный гормон)", _AN, (), _PANEL),
    ("креатинин", "Креатинин", _AN, (), _PANEL),
    ("билирубин общий", "Билирубин общий", _AN, (), _PANEL),
    ("биохимический анализ крови", "Биохимический анализ крови", _AN, (), ()),
    ("с-реактивный", "С-реактивный белок (СРБ)", _AN, (), _PANEL),
]

# Поисковые алиасы (народные/сокращённые названия) — кладём в синонимы эталона,
# чтобы поиск находил по «ОАК», «сахар», «кровь», «СРБ» и т.п. (поиск ищет и по синонимам).
ALIASES = {
    "Общий анализ крови": ["ОАК", "анализ крови", "кровь", "клинический анализ крови"],
    "Общий анализ мочи": ["ОАМ", "анализ мочи", "моча"],
    "Глюкоза (в крови)": ["сахар", "сахар крови", "глюкоза"],
    "Холестерин общий": ["холестерин"],
    "Биохимический анализ крови": ["биохимия", "БАК", "биохимический анализ"],
    "ТТГ (тиреотропный гормон)": ["ТТГ", "гормон щитовидной железы"],
    "Гликированный гемоглобин (HbA1c)": ["HbA1c", "гликированный гемоглобин", "диабет"],
    "С-реактивный белок (СРБ)": ["СРБ", "CRP", "воспаление"],
    "Витамин D": ["витамин д", "vitamin d"],
    "ЭКГ": ["электрокардиограмма", "кардиограмма"],
    "ЭхоКГ (эхокардиография)": ["эхокардиография", "УЗИ сердца", "эхо сердца"],
}

# (name, city, district, address, lat, lng, phone, url, kind)  kind: lab|clinic
CLINICS = [
    # — Лаборатории (свой домен) —
    ("INVITRO Алматы", "Алматы", "Медеуский", "ул. Кунаева, 32 (БЦ «Эталон»)",
     43.2560, 76.9560, "+7 727 311 09 09",
     "https://invitro.kz/analizes/for-doctors/", "lab"),
    ("INVITRO Астана", "Астана", "Есильский", "пр. Кабанбай батыра, 11",
     51.1280, 71.4300, "+7 7172 76 09 09",
     "https://invitro.kz/analizes/for-doctors/astana/", "lab"),
    ("Лаборатория Gemotest Алматы", "Алматы", "Алмалинский", "сеть лабораторий (Алматы)",
     43.2480, 76.9300, "8 800 070 13 13",
     "https://gemotest.kz/almaty/catalog/", "lab"),
    ("Лаборатория Gemotest Астана", "Астана", "Есильский", "сеть лабораторий (Астана)",
     51.1450, 71.4200, "8 800 070 13 13",
     "https://gemotest.kz/astana/catalog/", "lab"),
    ("INVITRO Караганда", "Караганда", "", "сеть лабораторий (Караганда)",
     49.8060, 73.0850, "+7 7212 50 09 09",
     "https://invitro.kz/analizes/for-doctors/karaganda/", "lab"),
    # — Клиники (платформа 103.kz, универсальный адаптер) —
    ("Клиника Emirmed", "Алматы", "Бостандыкский", "сеть клиник (Алматы)",
     43.2380, 76.9090, "+7 727 350 11 11", "https://emirmed.103.kz/pricing/", "clinic"),
    ("Медцентр «Сункар»", "Алматы", "Медеуский", "сеть клиник (Алматы)",
     43.2330, 76.9560, "+7 727 250 00 00", "https://sunkar.103.kz/pricing/", "clinic"),
    ("Клиника «Авиценна»", "Алматы", "Алмалинский", "ул. Тимирязева",
     43.2351, 76.8474, "+7 727 258 00 11", "https://avicenna.103.kz/pricing/", "clinic"),
    ("Клиника «Мой Доктор»", "Алматы", "Ауэзовский", "сеть клиник (Алматы)",
     43.2150, 76.8700, "+7 727 357 00 00", "https://moydoctor.103.kz/pricing/", "clinic"),
    ("Сеть клиник Mediker", "Астана", "Есильский", "сеть клиник (Астана)",
     51.1450, 71.4100, "+7 7172 76 00 00", "https://mediker-18.103.kz/pricing/", "clinic"),
    ("Клиника «Мейірім»", "Астана", "Алматинский", "г. Астана",
     51.1600, 71.4500, "+7 7172 73 00 00", "https://meirim-ast.103.kz/pricing/", "clinic"),
    # — Клиника со своим прайс-листом (таблица) —
    ("Медицинский центр «Луч»", "Астана", "Сарыаркинский", "г. Астана",
     51.1700, 71.4200, "+7 7172 38 11 47",
     "https://luchcenter.kz/uslugi/33-prejskurant", "clinic"),
]

# Доп. клиники на платформе 103.kz (проверены: ≥7 сравнимых услуг в прайсе).
# (name, city, slug, kind)
EXTRA_103KZ = [
    ("Центральная семейная клиника", "Алматы", "semeinaya-klinika", "clinic"),
    ("On Clinic Алматы", "Алматы", "on-clinic", "clinic"),
    ("Алматинский региональный диагностический центр", "Алматы", "ardc", "clinic"),
    ("ASIA MED clinic", "Алматы", "asia-med-clinic", "clinic"),
    ("Damed clinic", "Алматы", "damed-clinic", "clinic"),
    ("Рахат — центр семейной медицины", "Алматы", "rahat-1", "clinic"),
    ("Medical Park", "Алматы", "medical-park", "clinic"),
    ("Диагностический центр Smart Health (КазНУ)", "Алматы", "smart-health", "clinic"),
    ("Меди-Сервис", "Алматы", "mediservice", "clinic"),
    ("Медикер Алатау", "Алматы", "mediker-alatay", "clinic"),
    ("КДЛ Олимп", "Алматы", "kdlolymp", "lab"),
    ("Национальный научный медицинский центр", "Астана", "nacionalynyj-nauchnyj-medcentr", "clinic"),
    ("Президентская клиника (БМЦ УДП РК)", "Астана", "bmcudpkz", "clinic"),
    ("ЦЕТНАМЕД (центр народной медицины)", "Астана", "centr-narodnoj-mediciny-1", "clinic"),
    ("Прогресс Мед", "Астана", "progress-med", "clinic"),
    ("Многопрофильный медцентр (онкодиспансер)", "Астана", "onkologicheskij-dispanser", "clinic"),
    ("Ansar", "Астана", "ansar-astana", "clinic"),
    ("Medical Assistance Group", "Астана", "medical-assistance-group-3", "clinic"),
    ("Pro Clinique", "Астана", "proclinique", "clinic"),
    ("Alanda Clinic", "Астана", "alandaclinic", "clinic"),
    # — Караганда —
    ("Jysan Med", "Караганда", "jysan-med", "clinic"),
    ("Гиппократ — диагностический центр", "Караганда", "gippokrat-24", "clinic"),
    ("Gala Клиника", "Караганда", "galaklinika", "clinic"),
    ("Клинико-диагностический центр SANAD", "Караганда", "sanad", "clinic"),
    ("Integra Clinic", "Караганда", "integra-clinic", "clinic"),
    ("Диацент", "Караганда", "diacent", "clinic"),
    ("Clinic Miras", "Караганда", "clinicmiras", "clinic"),
    ("ЮТА — клиника красоты и здоровья", "Караганда", "juta", "clinic"),
    ("Городская поликлиника №1", "Караганда", "gp-1", "clinic"),
    # — Алматы (доп.) —
    ("KAZMED", "Алматы", "kazmed", "clinic"),
    ("Клиника «Семейный доктор»", "Алматы", "semejnyj-doktor", "clinic"),
    ("NurLab", "Алматы", "nurlab", "clinic"),
    ("Иммунодиагностика", "Алматы", "immunodiagnostika", "clinic"),
    ("МРТ Лидер (Алматы)", "Алматы", "mrt-lider-1", "clinic"),
    # — Астана (доп.) —
    ("Ultraline", "Астана", "ultraline", "clinic"),
    ("Sana Vita Medical", "Астана", "sanavita", "clinic"),
    ("Центр перинатальной профилактики", "Астана", "centr-perinatalynoj-profilaktiki", "clinic"),
    ("Лечебно-диагностический центр (ЛДЦ)", "Астана", "ldc", "clinic"),
    ("Городская детская инфекционная больница", "Астана", "gdib-astana", "clinic"),
    ("Ермен Clinic", "Астана", "jermen-clinic", "clinic"),
    ("Эколайф Астана", "Астана", "astana-ekolajf", "clinic"),
    ("Green Clinic", "Астана", "green-clinic", "clinic"),
    # — Караганда (доп.) —
    ("Клиника «Авиценна» (Караганда)", "Караганда", "avicenna-4", "clinic"),
    ("Медцентр SAT", "Караганда", "sat", "clinic"),
    ("Медцентр «Ависта»", "Караганда", "avista", "clinic"),
    ("КДЛ Олимп (Караганда)", "Караганда", "olimp-36", "lab"),
    # — Актобе —
    ("Медцентр «Евразия»", "Актобе", "eurasia", "clinic"),
    ("Медцентр «Куаныш»", "Актобе", "kuanish", "clinic"),
    ("S CLINIC", "Актобе", "s-clinic", "clinic"),
    ("Клиника «Айгерим»", "Актобе", "aigerim", "clinic"),
    # — Шымкент —
    ("Smart Clinic", "Шымкент", "smartclinic", "clinic"),
    ("Сан-Мед Сервис", "Шымкент", "sanmed-servis", "lab"),
    ("Медцентр «Сенім»", "Шымкент", "mc-senim", "clinic"),
    # — КДЛ Олимп по городам (лаборатория, 103.kz) —
    ("КДЛ Олимп (Астана)", "Астана", "olimp-15", "lab"),
    ("КДЛ Олимп (Шымкент)", "Шымкент", "olimp-41", "lab"),
    ("КДЛ Олимп (Актобе)", "Актобе", "olimp-kz-3", "lab"),
    ("КДЛ Олимп (Актау)", "Актау", "olimp-61", "lab"),
    ("КДЛ Олимп (Семей)", "Семей", "olimp-114", "lab"),
]

_CITY_CENTER = {
    "Алматы": (43.2380, 76.9450),
    "Астана": (51.1600, 71.4300),
    "Караганда": (49.8060, 73.0850),
    "Актобе": (50.2839, 57.1670),
    "Шымкент": (42.3000, 69.5900),
    "Актау": (43.6500, 51.1600),
    "Семей": (50.4110, 80.2275),
}

# Лаборатории INVIVO/SAPA — каталог за сессионным AJAX (scrape_lab_platform).
# (name, city, base_url, city_slug)
LAB_PLATFORM = [
    ("Лаборатория INVIVO Алматы", "Алматы", "https://invivo.kz", "almaty"),
    ("Лаборатория INVIVO Астана", "Астана", "https://invivo.kz", "astana"),
    ("Лаборатория INVIVO Караганда", "Караганда", "https://invivo.kz", "karaganda"),
    ("Лаборатория SAPA Алматы", "Алматы", "https://sapalab.com", "almaty"),
    ("Лаборатория SAPA Астана", "Астана", "https://sapalab.com", "astana"),
    ("Лаборатория SAPA Шымкент", "Шымкент", "https://sapalab.com", "shymkent"),
]


def _build_clinics():
    """Статичный список + сгенерённые из EXTRA_103KZ (координаты разнесены по городу)."""
    clinics = list(CLINICS)
    per_city: dict[str, int] = {}
    for name, city, slug, kind in EXTRA_103KZ:
        i = per_city.get(city, 0)
        per_city[city] = i + 1
        base_lat, base_lng = _CITY_CENTER[city]
        lat = round(base_lat + (i % 5) * 0.013 - 0.026, 5)
        lng = round(base_lng + (i // 5) * 0.013 - 0.013, 5)
        clinics.append((name, city, "", "сеть клиник / 103.kz", lat, lng, "",
                        f"https://{slug}.103.kz/pricing/", kind))
    return clinics


def _classify(raw_name: str):
    """Детерминированно сопоставляет сырое имя эталону по SPECS. → (canonical, category) | None.
    require — кортеж: должен присутствовать ХОТЯ БЫ ОДИН. excludes — стоп-слова."""
    low = raw_name.lower()
    for kw, canonical, category, require, excludes in SPECS:
        if kw not in low:
            continue
        if require and not any(r in low for r in require):
            continue
        if any(x in low for x in excludes):
            continue
        return canonical, category
    return None


def _curate(items):
    """Сводит сырые позиции к эталонам: одна позиция на эталон (минимальная цена).
    → {canonical: (category, price, raw_name)}."""
    best: dict[str, tuple[str, float, str]] = {}
    for it in items:
        hit = _classify(it.raw_name)
        if not hit:
            continue
        canonical, category = hit
        cur = best.get(canonical)
        if cur is None or it.price < cur[1]:
            best[canonical] = (category, it.price, it.raw_name)
    return best


def main(reset: bool = True):
    init_db()
    db = SessionLocal()
    try:
        if reset:
            db.query(Price).delete()
            db.query(ServiceCatalog).delete()
            db.query(Clinic).delete()
            db.commit()

        cache: dict[str, ServiceCatalog] = {}

        def get_service(canonical: str, category: str) -> ServiceCatalog:
            sc = cache.get(canonical)
            if sc is None:
                sc = ServiceCatalog(canonical_name=canonical, category=category,
                                    synonyms=list(ALIASES.get(canonical, [])))
                db.add(sc)
                db.flush()
                cache[canonical] = sc
            return sc

        def load(name, city, lat, lng, items, district="", address="", phone=""):
            curated = _curate(items)
            if not curated:
                print(f"  ✗ {name}: 0 позиций после фильтра")
                return
            clinic = Clinic(name=name, city=city, district=district, address=address,
                            lat=lat, lng=lng, phone=phone)
            db.add(clinic)
            db.flush()
            for canonical, (category, price, raw) in curated.items():
                sc = get_service(canonical, category)
                # копим синонимы — по ним работает поиск
                if raw not in (sc.synonyms or []):
                    sc.synonyms = list(sc.synonyms or []) + [raw]
                db.add(Price(
                    clinic_id=clinic.id, service_id=sc.id, source_type="web_scrape",
                    raw_name=raw, price=price, currency="KZT",
                    match_confidence=1.0, valid_from=date.today(),
                ))
            db.commit()
            print(f"  ✓ {name}: {len(curated)} услуг")

        for name, city, district, address, lat, lng, phone, url, kind in _build_clinics():
            try:
                items = scrape_url(url, timeout=45)
            except Exception as e:
                print(f"  ✗ {name}: скрапинг не удался — {type(e).__name__}: {str(e)[:80]}")
                continue
            # реальные адрес/телефон/координаты с 103.kz (вместо «сеть клиник» и джиттера)
            card = fetch_103kz_card(url)
            if card and card.get("lat") and card.get("lng"):
                address = card["address"] or address
                phone = card["phone"] or phone
                lat, lng, district = card["lat"], card["lng"], ""
            load(name, city, lat, lng, items, district, address, phone)

        # Лаборатории INVIVO/SAPA через сессионный AJAX
        plat_idx = 0
        for name, city, base, city_slug in LAB_PLATFORM:
            try:
                items = scrape_lab_platform(base, city_slug)
            except Exception as e:
                print(f"  ✗ {name}: AJAX не удался — {type(e).__name__}: {str(e)[:80]}")
                continue
            base_lat, base_lng = _CITY_CENTER[city]
            lat = round(base_lat + 0.03 - (plat_idx % 3) * 0.02, 5)
            lng = round(base_lng + 0.03 - (plat_idx // 3) * 0.02, 5)
            plat_idx += 1
            # реальные контакты с сайта сети (INVIVO даёт адрес+geo, SAPA — телефон)
            address, phone = "сеть лабораторий", ""
            contact = fetch_contact(f"{base}/ru/{city_slug}/")
            if contact:
                phone = contact.get("phone") or ""
                address = contact.get("address") or address
                if contact.get("lat") and contact.get("lng"):
                    lat, lng = contact["lat"], contact["lng"]
            load(name, city, lat, lng, items, address=address, phone=phone)

        n_cat = db.query(ServiceCatalog).count()
        n_price = db.query(Price).count()
        print(f"\nИтого: {db.query(Clinic).count()} клиник, {n_cat} услуг, {n_price} цен.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
