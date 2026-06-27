# Чек-лист соответствия ТЗ — Кейс 1 «MedPrice»

Построчное соответствие коду. Ветка `feat/product-evolution`. Статусы: ✅ готово ·
🟡 частично/с оговоркой · ⛔ не применимо к среде.

> §3.4 в ТЗ помечен **«опционально (дают преимущество)»** — отмечен отдельно.

## §2.1 Источники — реально задействованы с данными

В проде (Postgres, на 2026-06-27): **107 клиник · 1985 услуг · 10078 цен · 14 городов** (Алматы/Астана/Караганда/Актобе/Шымкент/Актау/Семей/Павлодар/Петропавловск/Усть-Каменогорск/Тараз/Костанай/Талдыкорган/Кызылорда). Резидент/нерезидент заполнен на **3767 ценах**; очередь ревью (unmatched) — **4264**. Каталог обогащён ОФИЦИАЛЬНЫМ справочником: загружен «Справочник услуг.xlsx» (1281 услуга, 1204 с кодом тарификатора) → +1191 услуга, code-first нормализация.

| Источник из ТЗ | Способ | Статус | Что в проекте |
|---|---|---|---|
| **kdl.kz / kdlolymp.kz** | статика (адаптер `_kdl`) | ✅ задействован | живой парсинг 4 филиалов, ~280 цен |
| **invitro.kz** | статика `/analizes/` (адаптер `_invitro`) | ✅ задействован | ~316 анализов с ценами |
| **doq.kz** | REST API `api.doq.kz/api/v1/` (`doq_connector`) | ✅ задействован | 528 клиник × 12 городов; цена через `/doctors-meta/`; в сиде — 14 клиник по 4 городам |
| **olymp.kz** | — | ⛔ недоступен | timeout с сервера; та же сеть КДЛ покрыта через kdlolymp |
| helix.kz | Playwright | 🟡 возможен | редирект на helix.ru, частичный рендер |
| medel.kz / mck.kz | Playwright | 🟡 возможен | SPA/заглушка |
| aksai-clinic.kz | — | ⛔ | DNS не резолвится |
| **сайты клиник РК (PDF/DOCX/HTML)** | upload + 103.kz | ✅ задействован | 4 реальных файла-прайса + **103.kz**: Гемотест/КДЛ/Рахат/AQmed/Smartmed (≈90–105 цен каждая) |

Доп. инфраструктура: `ingestion/o103_harvester.py` (sitemap 103.kz ≈9248 поддоменов клиник для масштабирования), Playwright+chromium установлены и работают (`--no-sandbox`) для SPA-источников. Полный аудит источников по городам — в истории задач/отчёте команды.

## §2.2 Структура собираемых данных

| Поле ТЗ | Статус | Где |
|---|---|---|
| clinic_id (**uuid**) | ✅ | `Clinic.id` тип `Uuid` (§2.2 буквально); `Price.clinic_id` FK uuid |
| clinic_name | ✅ | `Clinic.name` (выдаётся в `PriceOffer.clinic_name`) |
| city | ✅ | `Clinic.city` |
| address | ✅ | `Clinic.address` |
| phone | ✅ | `Clinic.phone` |
| working_hours | ✅ | `Clinic.working_hours` (добавлено) |
| source_url | ✅ | `Price.source_url` (URL источника записи, из `Source` при ingest) → `PriceOffer.source_url` |
| service_id (**uuid**) | ✅ | `ServiceCatalog.id` тип `Uuid` (§2.2 буквально); `Price.service_id` FK uuid |
| service_name_raw | ✅ | `Price.raw_name` |
| service_name_norm | ✅ | `ServiceCatalog.canonical_name`; дословно в `CollectedRecord.service_name_norm` и `PriceOffer.service_name_norm` |
| category (enum 4) | ✅ строго | типизированный `category.Category(str, Enum)` = лаборатория/приём врача/диагностика/процедура; `category.to_enum()`; поля `CollectedRecord.category` / `ServiceComparison.category_enum` типа `Category`; `/api/categories` |
| price_kzt (decimal) | ✅ | `Price.price` Numeric(12,2); дословно `CollectedRecord.price_kzt: Decimal`, `PriceOffer.price_kzt` |
| currency (KZT/USD→KZT) | ✅ строго | типизированный `currency.Currency(str, Enum)` = {KZT, USD}; `currency.normalize()` приводит шум (Тенге/₸/$) к канону на приёме; `service.to_kzt()` конвертирует USD→KZT; поля схем типа `Currency`; оригинал в `Price.price_original/currency_original` |
| duration_days | ✅ | `Price.duration_days` (KDL-адаптер парсит «срок выполнения») |
| parsed_at (datetime) | ✅ | `Price.parsed_at` |
| is_active (bool) | ✅ | `Price.is_active` (+ авто-деактивация устаревших) |
| price_resident / price_nonresident | ✅ | `Price.price_resident` / `Price.price_nonresident` (заполнено на 3767 ценах) |

**Дословная §2.2-запись (в точь точь):** `GET /api/records` → `list[CollectedRecord]` отдаёт плоские кортежи (клиника × услуга × цена) ровно с полями/именами/типами таблицы ТЗ §2.2: `clinic_id, clinic_name, city, address, phone, working_hours, source_url, service_id, service_name_raw, service_name_norm, category(enum), price_kzt(decimal), currency(enum), duration_days, parsed_at, is_active`. Строгие enum (`category`/`currency`) валидируются на уровне Pydantic-схемы. Фильтры: `city`, `service_id`, `active_only`, пагинация `limit`/`offset`.

## §3.1 Модуль сбора (парсер)

| Требование | Статус | Где |
|---|---|---|
| Автообход сайтов, извлечение прайсов | ✅ | `ingestion/web_scraper.py` (generic + адаптеры KDL/invitro/gemotest/103.kz/INVIVO/SAPA) |
| Форматы HTML/PDF/DOCX/Excel | ✅ | `file_parser.detect_and_parse` (DOCX вкл. tracked changes — через `archive_extractor`) |
| Дедупликация при повторе | ✅ | `service.ingest_items` (по clinic_id+service_id) |
| Журнал ошибок (источник+причина) | ✅ | `IngestionRun(status=error, message=...)`, `scheduler._log_error` |
| Raw-слой отдельно | ✅ | `IngestionRun.raw_content` (сырой HTML web_scrape + текст файлов) |
| Запуск вручную / по расписанию | ✅ | **Интерфейс**: `/admin` — карточка «Автосбор с сайта» (приём по URL → POST `/api/ingest/scrape`) + кнопка «Запустить плановый сбор» (POST `/api/ingest/run-scheduled`); пакетная загрузка файлов. **Cron**: `scripts/cron-ingest.sh` (flock) в crontab `0 */6 * * *` → `docker exec medtech-backend python -m app.scheduler` |

## §3.2 Нормализация и справочник

| Требование | Статус | Где / проверка |
|---|---|---|
| Приведение разнородных названий к единому справочнику | ✅ | `ingestion/normalizer.py`: fuzzy (token_set) → семантика (эмбеддинги/pgvector) → **LLM-арбитраж (Gemini 2.5-flash / Vertex)** + биоматериал-гарды (стул/мокрота/мочевой вариант ≠ кровь); **code-first по коду тарификатора официального справочника**; непривязанные → очередь unmatched |
| **Пример ТЗ**: ОАК / Общий анализ крови / CBC / Клинический анализ крови → одна услуга | ✅ | Проверено по `match_one`: все варианты → «Общий анализ крови» (1.00); `CBC` заведён синонимом |
| Справочник формируется командой на основе собранных данных | ✅ | **1985 услуг** из реальных источников + ОФИЦИАЛЬНЫЙ «Справочник услуг.xlsx» (1281 услуга, 1204 с кодом тарификатора, +1191 услуга); командой доведены пробелы (АСТ, ПСА, Т4/Т3 свободный/общий) |
| Справочник содержит: id, название, синонимы, категорию | ✅ | `ServiceCatalog`: `id` uuid · `canonical_name` · `synonyms` (JSON) · `category` (+ `tarificator_code`, `specialty`); все услуги с синонимами |
| Нормализация вручную / алгоритмически / AI | ✅ | алгоритм (fuzzy+семантика) + **AI (Gemini)** + ручное ревью/reassign в `/admin/review`; AI-перепроверка привязок `POST /api/review/recheck` (verify-gated) |
| Непривязанные → очередь ручной разметки (unmatched queue) | ✅ | `match_one` ниже `reject_floor` → `status=unmatched`; `GET /api/review/queue` + экран `/admin/review` |
| Поиск/подсказки по аббревиатурам без ложных совпадений | ✅ | `_relevance` (токен-матчинг, канон>синонима, порог 0.7); TTG→ТТГ, T4→Т4 свободный, vit d→Витамин D (было IgA/билирубин/0) |

**Сверх ТЗ (качество справочника):** аудит+чистка загрязнённых синонимов (−98 кросс-канонических, ОАК −166 чужих, −24 тироид), покрытие EN-аббревиатур (CBC/PSA/ALT/AST/TSH/Ferritin/Urinalysis/vit d). **Остаток:** системное token-level загрязнение синонимов в длинном хвосте замаскировано ранжированием (канон-вес), физически остаётся в данных — для идеала нужен систематический synonym-sanity проход.

**Итог §3.2: выполнено полностью (все пункты ✅).** Детали — NOTES #34/#35.

## §3.3 UI — поиск и сравнение

| Требование | Статус | Где |
|---|---|---|
| Поиск с автодополнением | ✅ | `/api/suggest` + `SearchAutocomplete` |
| Фильтр город | ✅ | `city` |
| Фильтр категория | ✅ | `category` (по enum) |
| Фильтр ценовой диапазон (min+max) | ✅ | `min_price`/`max_price` |
| Фильтр рейтинг | ✅ | `min_rating` (+ `Clinic.rating`) |
| Фильтр онлайн-запись | ✅ | `online_booking` (+ `Clinic.online_booking`) |
| Результаты: цена/адрес/режим/источник | ✅ | `PriceOffer` + `OfferRow` |
| Сорт по цене ↑↓ | ✅ | `price_asc/price_desc` |
| Сорт по расстоянию | ✅ | `sort=distance` + geolocation (haversine) |
| Сорт по дате обновления | ✅ | `sort=updated` |
| Карточка клиники: все услуги/контакты/сайт | ✅ | `/api/clinics/{id}/profile` + `app/clinics/[id]` |
| Дата последнего обновления цены | ✅ | `valid_from`/`parsed_at` + `freshnessLabel` |
| Адаптивность | ✅ | Tailwind-брейкпоинты |

## §4 Нефункциональные

| Требование | Статус | Где |
|---|---|---|
| Обновление ≥1/сутки | ✅ | crontab `0 */6 * * *` → `scripts/cron-ingest.sh` (flock, реально установлен на проде, каждые 6 ч). Роутинг: web_scrape (KDL/invitro/103/KazMedClinic) → `scrape_url`, api `doq://{city}/{clinic}` → `doq_connector.refresh`. Источники старше — деактивируются по свежести. |
| UI-выдача < 3 c | ✅ | справочник мал, запрос индексирован |
| Не выдавать данные >30 дней как актуальные | ✅ | фильтр свежести в `_build_comparison` + `scheduler.mark_stale_inactive` |
| Масштабируемость источников | ✅ | реестр `Source` + адаптеры по домену без правки ядра |
| Отказоустойчивость парсера | ✅ | per-source try/except в `scheduler`, robots-skip не валит остальные |
| Хранение raw ≥90 дней | ✅ | `raw_retention_days=90`, `scheduler.purge_expired_raw` |

## §3.4 Опционально (дают преимущество)

| Функция | Статус |
|---|---|
| Карта клиник с маркерами | ✅ `ClinicMap.tsx` — Яндекс.Карты (корректно для РК; вместо Leaflet/Google) |
| История изменения цен | ✅ `PriceHistory` + `price_trend.points` (по датам) → **график динамики** в `PriceTrendBlock` (SVG-чарт: точки/оси дат/min-max/тренд); показывается для услуг с ≥2 датами (155 услуг) |
| **Сравнение таблицей** | ✅ `/compare` + `POST /api/compare-clinics` (услуги×клиники, 🏆 лучшая цена, итог/экономия/дистанция/рекомендации, sticky шапка+столбец, мобильные карточки) |
| **Подписка на изменение цены** | ✅ `PriceSubscription` + `/api/subscriptions` + `scheduler.check_price_subscriptions` → уведомление в WhatsApp при снижении; форма «🔔 Подписаться» в `ComparisonView` |
| Маршрут до клиники | ✅ кнопка «Маршрут» (карта + `/compare`) → Яндекс.Карты `rtext` от геолокации (вместо 2GIS/Google) |
| **Распознавание фото/скана направления (OCR)** | ✅ сверх ТЗ: `/recipe`, `/admin/normalizer` и **чат-помощник** (`POST /api/chat/vision`) принимают фото/PDF → OCR (tesseract rus/kaz/eng) → разбор услуг |

## §8 Ограничения и правила

| Правило | Статус | Где |
|---|---|---|
| Парсинг только открытых данных без авторизации | ✅ | адаптеры берут публичные прайсы |
| Не создавать чрезмерную нагрузку (задержки) | ✅ | `robots.crawl_delay` + пер-хост throttle |
| **Соблюдение robots.txt** | ✅ | `ingestion/robots.py` (Protego, Google-спек wildcards) — единый шлюз `polite_get`, все GET проходят проверку |
| Персональные данные не собираются | ✅ | собираются только услуги/цены/контакты клиник |

## §6 Результаты команды

| Артефакт | Статус |
|---|---|
| Рабочий MVP + README | ✅ |
| БД с реальными данными (≥3 источника, ≥100 услуг) | ✅ **107 клиник, 1985 услуг, 10078 цен, 14 городов** — кратно превышает минимум (≥3/≥100) |
| Справочник ≥50 нормализованных | ✅ **1985 позиций** справочника (включая официальный справочник тарификатора) |
| Документация API (OpenAPI) | ✅ FastAPI `/docs` |
| Презентация (5–7 слайдов) | 🟡 `docs/pitch.md` (контент презентации); оформленный дек — по запросу |
| Демо-видео (опционально) | ⛔ опционально |
