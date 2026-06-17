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
from app.ingestion.service import ingest_items
from app.ingestion.web_scraper import scrape_url
from app.models import Clinic, Price, ServiceCatalog

# Базовый справочник — чтобы fuzzy-нормализация сводила длинные сырые имена к
# короткому эталону без LLM (GROQ-ключа на проде нет).
CATALOG = [
    ("Общий анализ крови", "Анализы"),
    ("Общий анализ мочи", "Анализы"),
    ("Биохимический анализ крови", "Анализы"),
    ("Анализ на глюкозу", "Анализы"),
    ("Холестерин общий", "Анализы"),
    ("Витамин D", "Анализы"),
    ("Ферритин", "Анализы"),
    ("ТТГ (тиреотропный гормон)", "Анализы"),
    ("СОЭ", "Анализы"),
    ("Креатинин", "Анализы"),
    ("УЗИ брюшной полости", "УЗИ"),
    ("УЗИ почек", "УЗИ"),
    ("УЗИ щитовидной железы", "УЗИ"),
    ("УЗИ органов малого таза", "УЗИ"),
    ("УЗИ молочных желёз", "УЗИ"),
    ("Приём терапевта", "Приём врача"),
    ("Приём кардиолога", "Приём врача"),
    ("Приём гинеколога", "Приём врача"),
    ("Приём невролога", "Приём врача"),
    ("Приём офтальмолога", "Приём врача"),
    ("Приём уролога", "Приём врача"),
    ("Приём эндокринолога", "Приём врача"),
    ("ЭКГ", "Процедуры"),
    ("ЭхоКГ (эхокардиография)", "Процедуры"),
]

# Курируемые срезы: оставляем позиции, чьё сырое имя содержит один из ключей.
# Иначе крупная сеть залила бы 300-2000 позиций и зашумила справочник.
LAB_KEYWORDS = [
    "общий анализ крови", "общий анализ мочи", "глюкоза", "холестерин общий",
    "витамин d", "ферритин", "тиреотропный", "соэ", "креатинин",
    "билирубин общий", "биохими", "с-реактивный", "гликированный",
]
CLINIC_KEYWORDS = [
    "терапевт", "кардиолог", "гинеколог", "невролог", "невропатолог",
    "офтальмолог", "уролог", "эндокринолог", "дерматолог", "лор",
    "брюшной полости", "почек", "щитовид", "малого таза", "молочных желез",
    "эхокардиограф", "экг",
]
# Органные ключи неоднозначны («операция на органах брюшной полости» ≠ УЗИ).
# Засчитываем их только если в названии явно есть «узи».
_ULTRASOUND_ONLY = {"брюшной полости", "почек", "щитовид", "малого таза", "молочных желез"}

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
]

_CITY_CENTER = {
    "Алматы": (43.2380, 76.9450),
    "Астана": (51.1600, 71.4300),
    "Караганда": (49.8060, 73.0850),
    "Актобе": (50.2839, 57.1670),
    "Шымкент": (42.3000, 69.5900),
}


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


def _curate(items, keywords):
    """Фильтр по ключам + не больше одной позиции на ключ (первая = базовая цена)."""
    seen, out = set(), []
    for it in items:
        low = it.raw_name.lower()
        key = next((k for k in keywords if k in low
                    and (k not in _ULTRASOUND_ONLY or "узи" in low)), None)
        if key is None or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def main(reset: bool = True):
    init_db()
    db = SessionLocal()
    try:
        if reset:
            db.query(Price).delete()
            db.query(ServiceCatalog).delete()
            db.query(Clinic).delete()
            db.commit()

        for name, category in CATALOG:
            db.add(ServiceCatalog(canonical_name=name, category=category, synonyms=[]))
        db.commit()

        total_prices = 0
        for name, city, district, address, lat, lng, phone, url, kind in _build_clinics():
            try:
                items = scrape_url(url, timeout=45)
            except Exception as e:
                print(f"  ✗ {name}: скрапинг не удался — {type(e).__name__}: {str(e)[:80]}")
                continue
            items = _curate(items, LAB_KEYWORDS if kind == "lab" else CLINIC_KEYWORDS)
            if not items:
                print(f"  ✗ {name}: 0 позиций после фильтра")
                continue
            clinic = Clinic(name=name, city=city, district=district, address=address,
                            lat=lat, lng=lng, phone=phone)
            db.add(clinic)
            db.commit()
            db.refresh(clinic)
            res = ingest_items(
                db, clinic_id=clinic.id, channel="pull", source_type="web_scrape",
                items=items, fmt="html", valid_from=date.today(),
            )
            total_prices += res.items_found
            print(f"  ✓ {name}: {res.items_found} поз., совпало {res.matched}, на проверку {res.needs_review}")

        n_cat = db.query(ServiceCatalog).count()
        n_price = db.query(Price).count()
        print(f"\nИтого: {db.query(Clinic).count()} клиник, {n_cat} услуг, {n_price} цен.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
