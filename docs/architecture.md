# Архитектура

Пять слоёв, два канала сбора, **два пайплайна приёма** (MedPrice + MedArchive),
одна воронка нормализации, слой хранения оригиналов.

```
┌─────────────────────────────────────────────────────────────────────┐
│ ИСТОЧНИКИ                                                             │
│   ① Push — клиника грузит прайс (xlsx/csv/pdf/скан)                   │
│   ② Pull — автосбор: веб-парсер сайтов + API-коннекторы (по cron)     │
│   ③ Archive — документ тарификатора (PDF/скан/DOCX/XLSX·XLS)          │
└──────────┬──────────────────┬──────────────────────────┬─────────────┘
           │ push             │ pull                      │ archive
           ▼                  ▼                           ▼
┌──────────────────────────────────────────┐  ┌──────────────────────────┐
│ СЛОЙ 1а · MedPrice — ПРИЁМ (Кейс 1)       │  │ СЛОЙ 1б · MedArchive (К.2)│
│  file_parser web_scraper api_connector    │  │  archive_extractor:       │
│  scheduler                                │  │   PDF-текст / скан-OCR /   │
│  upload (1) · upload-batch (zip/N) ·      │  │   DOCX-tracked / XLSX·XLS  │
│  export каталога (xlsx/csv) → ingest_items│  │  POST /api/ingest/archive │
│                  │                        │  │   резидент/нерезидент +   │
│                  │                        │  │   §4.4-валидации          │
│                  │                        │  │   → ingest_archive        │
└──────────────────┼────────────────────────┘  └────────────┬─────────────┘
                   │                                          │
                   ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│   ★ НОРМАЛИЗАЦИЯ (общая воронка, по тирам):                          │
│     code-first(код тарификатора) → fuzzy(rapidfuzz) →                 │
│     семантика(fastembed+pgvector ≥0.85) → LLM-арбитраж(Gemini)        │
│     + биоматериал-гард · дедуп по приоритету · очередь unmatched      │
└───────────────────────┬───────────────────────────────────────────--┘
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ЯДРО ДАННЫХ · PostgreSQL 16 + pgvector                               │
│   clinics(=Partner) · service_catalog(=Service) · prices(=PriceItem) │
│   sources · ingestion_runs(=PriceDocument) · service_embeddings      │
│   price_history · price_subscriptions · leads                        │
└──────────┬──────────────────────────────────────────┬────────────────┘
           │                                            │ оригиналы
           ▼                                            ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│ СЛОЙ 2 · АГРЕГАТОР — FastAPI          │  │ СЛОЙ ХРАНЕНИЯ ОРИГИНАЛОВ      │
│  /api/search · /api/compare/{id}      │  │  /data/uploads/<run_id>      │
│  фильтры город/цена/категория         │  │  (том medtech_data)          │
│  /api/chat — 🤖 retrieval-injection   │  │  ingestion_runs.file_path →  │
│  (LLM Gemini/Vertex; фолбэк Alem/Groq)│  │   аудит и версионирование     │
│  /api/archive/quality · /api/unmatched│  │   (price_history)             │
└──────────────────────┬────────────────┘  └──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ВИТРИНА · Next.js 15 (App Router, TS, Tailwind)                      │
│   поиск · сравнение · карта (Яндекс) · 🤖 чат · /normalizer (демо)    │
│   /admin — дашборд приёма: статы · пакетная загрузка · экспорт · лог  │
└─────────────────────────────────────────────────────────────────────┘
```

> **Карточки ↔ карта связаны:** клик по карточке клиники центрирует карту и
> открывает её балун, клик по метке подсвечивает карточку в списке.

## Почему два канала
- **② Pull** быстро наполняет базу без участия клиник — пациенту сразу есть что сравнивать.
- **① Push** даёт точные, заверенные самой клиникой прайсы.
- Со временем клиники переходят с парсинга на официальную загрузку/API. `source_type` хранит происхождение каждой цены.

## ★ Нормализация (ядро ценности)
`backend/app/ingestion/normalizer.py`. Тиры от дешёвого/точного к умному:
1. **code-first** — совпадение по коду тарификатора (`conf = 1.0`, без сети);
2. **fuzzy-match** (rapidfuzz, `token_set_ratio`) против `canonical_name` и всех синонимов;
3. **семантика** — fastembed (multilingual MiniLM) + pgvector (таблица `service_embeddings`),
   авто-применяется при сходстве **≥ 0.85**;
4. в зоне неоднозначности — **LLM-арбитраж** (Gemini 2.5-flash через Vertex AI; фолбэк
   AlemLLM/Groq) выбирает из top-кандидатов либо предлагает чистое эталонное имя + категорию;
5. иначе позиция уходит в очередь `unmatched` на ручную проверку (catalog растёт сам только в
   MedPrice-пути; в MedArchive справочник организаторов read-only).

Каждое успешно сопоставленное сырое имя (в MedPrice-пути) добавляется в `synonyms` услуги — справочник самообучается.

**Биоматериал-гард.** Позиции с иным биоматериалом (стул/мокрота/мочевой вариант) не сливаются
с одноимённой кровяной услугой — иначе «🏆 Лучшая цена» сравнивала бы несопоставимое.

**Гард не-первичных приёмов.** Для категории «Приём врача» `token_set_ratio` ложно давал 100% на «Повторный/Вторичный/Онлайн/Детский приём X» (первичное название — подмножество). Поэтому модификатор приёма (`_appt_modifier`) отводит такие позиции в отдельную услугу («Повторный приём X» / «Онлайн-консультация X» / «Приём детского X»), а не сливает с первичным.

## 🤖 Чат-помощник (retrieval-injection)
`backend/app/routers/chat.py`. Бот — надстройка над агрегатором, отвечающая строго по данным:
1. из последнего сообщения вытягиваем услугу и город (`_detect_city` + фаззи `_rank_services`);
2. **сами ищем** по той же воронке, что и витрина (`_build_comparison`) — это retrieval;
3. найденные предложения (JSON) вкладываем в системный промпт — это injection;
4. LLM формулирует ответ **только по вложенным данным**, выделяя самую дешёвую клинику.

Основной провайдер — **Gemini 2.5-flash через Vertex AI**; фолбэк — OpenAI-совместимые
AlemLLM/Groq, переключаемые через `LLM_PROVIDER`. Tool-calling не используется намеренно:
AlemLLM его не поддерживает, а retrieval-injection провайдер-агностичен и исключает
галлюцинации цен. Без доступного провайдера endpoint деградирует в детерминированный
поиск-сводку (`_fallback`) — демо работает всегда.

## Дедупликация
`backend/app/ingestion/service.py`. Для пары (клиника, услуга) держим одну цену. Приоритет источника при конфликте: **upload > api > web_scrape** — официальная загрузка клиники не перезаписывается парсером. Внутри одной пачки дубли схлопываются по минимальной цене.

## Схема БД
Имя в коде = сущность ТЗ:
- **clinics** (= Partner) — клиники (+ координаты для карты).
- **service_catalog** (= Service) — единый справочник: `canonical_name`, `category`, `synonyms` (jsonb), `tarificator_code`, `specialty`.
- **prices** (= PriceItem) — цены: `service_id` (связь со справочником), `source_type`, `raw_name`, `price`, `match_confidence`, `valid_from`.
- **ingestion_runs** (= PriceDocument) — журнал запусков/документов приёма: `clinic_id`, `file_name`, `format`, `status`, `message`, `raw_content`, `effective_date`, `file_path`, `matched`, `needs_review`.
- **sources** — реестр источников (тип, url/endpoint, cron, enabled, last_run_at).
- **service_embeddings** — векторы услуг (pgvector) для семантического матчинга.
- **price_history** — версии цен (версионирование при переприёме архива).
- **price_subscriptions** — подписки на изменение цены услуги/клиники.
- **leads** — заявки/лиды из витрины.

Ключевые связки:
- `prices.service_id → service_catalog.id` — сравнение «одной и той же» услуги между клиниками.
- `prices.source_type` — происхождение цены (доверие + дедуп).
- `service_embeddings.service_id → service_catalog.id` — pgvector-поиск кандидатов.

**Аддитивные поля MedArchive** (nullable — single-price путь MedPrice не ломается):
`prices.price_resident/price_nonresident` (раздельные тарифы), `prices.service_code_source/tarificator_code`,
`service_catalog.tarificator_code/specialty` (целевой справочник организаторов),
`ingestion_runs.file_name/raw_content` (исходный документ для аудита). Миграция —
`migrate._ensure_additive_columns()` (ALTER ADD COLUMN по месту, без новых Alembic-ревизий).

## MedArchive — конвейер обработки архива (Кейс 2)

Параллельный приёму MedPrice движок (`ingestion/archive_extractor.py` +
`archive_service.py` + `refcatalog.py` + `semantic_backfill.py`, CLI `app/archive_ingest.py`):

```
архив(zip/папка) ─▶ детект формата ─▶ извлечение (резидент/нерезидент + код)
   DOCX(tracked changes) / XLSX·XLS(многостр. шапка, все листы) / PDF(таблицы→слова)
        │
        ▼ валидации (цена>0, нерезидент≥резидент, аномалия>50%, версионирование)
   нормализация match_archive(): код тарификатора(точно) → fuzzy → семантика(≥0.85)
        │                                   │
        ▼ сматчено → prices(service_id)     ▼ ниже порога → unmatched(service_id=NULL)
                                               очередь оператора /api/unmatched + POST /match (учит синоним)
        ▼
   оригиналы → /data/uploads/<run_id> (том medtech_data) · версии → price_history
        ▼
   метрика качества GET /api/archive/quality (% автонормализации, позиционная, до дедупа)
```

Принцип: **точность важнее охвата** — семантика авто-применяется только при высокой
уверенности (≥0.85), иначе позиция идёт оператору как подсказка; ложный маппинг хуже
unmatched, т.к. портит сравнение цен. Справочник организаторов (приоритет — код тарификатора)
фиксирован → `match_archive` read-only (не создаёт услуг/синонимов на приёме).

**Хранение оригиналов.** Каждый принятый документ сохраняется как есть в
`/data/uploads/<run_id>` (постоянный том `medtech_data`), путь пишется в
`ingestion_runs.file_path` — для аудита, переразбора и версионирования (`price_history`).

## Стек и деплой
- **Backend**: FastAPI + SQLAlchemy + PostgreSQL 16 + pgvector.
- **Frontend**: Next.js 15 (App Router, TypeScript, Tailwind).
- **LLM**: Gemini 2.5-flash через Vertex AI (фолбэк AlemLLM/Groq).
- **Семантика**: fastembed (multilingual MiniLM) + pgvector.
- **WhatsApp-gateway**: Baileys (сервис `medtech-wa`).
- **Деплой**: Docker Compose (`docker-compose.prod.yml`) — сервисы `medtech-db`,
  `medtech-backend`, `medtech-wa`, `medtech-frontend`; миграция в entrypoint; постоянные
  тома `pgdata` (БД) и `medtech_data` (оригиналы документов в `/data`).

## Масштабирование
- Планировщик: `scheduler.py` (cron) → Celery + Redis beat в проде.
- Веб-парсер: httpx+BeautifulSoup для статики, Playwright-хук (`scrape_dynamic`) для SPA.
- БД: единый `DATABASE_URL` (PostgreSQL 16 + pgvector в проде).
- Семантика уже в проде: fastembed + pgvector (`service_embeddings`) поверх fuzzy+LLM.

## Прод-числа (2026-06-27)
- 107 клиник · 1985 услуг (1191 из официального справочника) · 10 078 цен · 14 городов.
- MedArchive: 10 документов, 72.0% автонормализации.
