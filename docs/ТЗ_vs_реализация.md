# Анализ ТЗ ↔ текущая реализация

Сверка двух ТЗ хакатона с прод-веткой `main` (актуально 2026-06-27).
Легенда: ✅ есть · 🟡 частично · ❌ нет.

**Прод-снимок:** 107 клиник, 1985 услуг (1191 из официального «Справочник услуг.xlsx»), 10078 цен, 14 городов; резидент/нерезидент заполнено на 3767 ценах; очередь unmatched — 4264.
**Стек нормализации:** fuzzy (rapidfuzz) → семантика (pgvector) → LLM **Gemini 2.5-flash (Vertex AI)** основной, Groq/AlemLLM — фолбэк.

---

## Кейс 1 — MedServicePrice.kz (агрегатор и сравнение цен)

| # | Требование ТЗ | Статус | Где / комментарий |
|---|---|:--:|---|
| 3.1 | Авто-обход сайтов, извлечение прайсов | ✅ | `web_scraper.py` (httpx+bs4, Playwright-хук), `load_real_data.py` |
| 3.1 | Форматы HTML / PDF / Excel | ✅ | `file_parser.py` (xlsx/xls/csv/pdf) + HTML-скрейп |
| 3.1 | Формат **DOCX** | ✅ | `archive_extractor.parse_docx` (+ приём tracked changes `_accept_tracked_changes`) |
| 3.1 | Дедупликация при повторном запуске | ✅ | `service.ingest_items` дедуп по (клиника, услуга); приоритет upload>api>web |
| 3.1 | Журналирование ошибок парсинга | ✅ | `IngestionRun` (status/parse_log), `/api/ingest/runs`, `/stats` |
| 3.1 | Raw-слой отдельно от нормализованного | ✅ | raw хранится ≥90 дней (`raw_retention_days=90`, `purge_expired_raw`); оригиналы файлов в `/data/uploads` |
| 3.1 | Запуск вручную + по расписанию (cron) | ✅ | `/ingest/run-scheduled`, `scheduler.py`, поле `Source.schedule` |
| 3.2 | Справочник: id, название, синонимы, категория | ✅ | `ServiceCatalog` (canonical_name, synonyms JSON, category) |
| 3.2 | Нормализация (алго/AI) | ✅ | fuzzy(rapidfuzz)→semantic(pgvector)→LLM **Gemini 2.5-flash** (Groq/AlemLLM фолбэк) — `normalizer.py` |
| 3.2 | Очередь ручной разметки (unmatched) | ✅ | `/api/review/queue` + `/admin/review` UI |
| 3.3 | Поиск с автодополнением | ✅ | `/api/suggest` |
| 3.3 | Фильтры: город, категория | ✅ | `SearchExperience.tsx` |
| 3.3 | Фильтры: ценовой диапазон | ✅ | min/max цены в UI и фильтре поиска |
| 3.3 | Фильтры: рейтинг клиники, онлайн-запись | ✅ | `Clinic.rating`, `Clinic.online_booking` |
| 3.3 | Список: цена, адрес, режим работы, ссылка на источник | ✅ | `Clinic.working_hours`, `Clinic.website`, `Price.source_url` |
| 3.3 | Сортировка по цене | ✅ | `sort=price_asc/desc` |
| 3.3 | Сортировка по расстоянию / дате обновления | ✅ | расстояние по haversine+гео, сорт по дате обновления |
| 3.3 | Карточка клиники (все услуги, контакты) | ✅ | `/clinic/[token]`, `clinics/{id}/prices` |
| 3.3 | Дата последнего обновления цены | ✅ | «Обновлено N дней назад» в UI |
| 3.3 | Адаптивный (мобильный) UI | ✅ | Next.js 15 + Tailwind |
| 3.4 | Карта с маркерами | ✅ | `ClinicMap.tsx` (Яндекс.Карты — корректно для РК); в балуне метки — «Отправить координаты в WhatsApp» (React-модалка ввода номера → `wa.me/<номер>` с адресом/координатами/маршрутом) |
| 3.4 | Подписка на изменение цены | ✅ | `PriceSubscription` + уведомления WhatsApp |
| 3.4 | Сравнение в режиме «таблица» | ✅ | `/compare`, `/api/compare-clinics` |
| 3.4 | История изменения цен | ✅ | `PriceHistory` + график |
| 3.4 | Маршрут 2GIS/Google Maps | ✅ | кнопка «Маршрут» → Яндекс.Карты (`rtext`) |
| 4 | Цена не старше 30 дней как актуальная | ✅ | `price_freshness_days=30`, `mark_stale_inactive` |
| 4 | Raw хранится ≥90 дней для аудита | ✅ | `raw_retention_days=90`, `purge_expired_raw` |
| 6 | Реальные данные: ≥3 источника, ≥100 услуг | ✅ | прод: 107 клиник, 10078 цен, 14 городов |
| 6 | Справочник ≥50 нормализованных позиций | ✅ | 1985 услуг, 1191 из официального «Справочник услуг.xlsx» |

**Сверх ТЗ (Кейс 1):** корзина-рецепт (`/recipe`, маршрут по направлению врача), покрытие ОСМС, лиды (`Lead` — монетизация), чат-виджет на Gemini 2.5-flash (Vertex) **+ OCR в чате** (`/api/chat/vision` — фото направления), **отправка координат клиники в WhatsApp** (модалка в балуне карты), петля обратной связи `PriceReport`, экспорт каталога, self-service портал клиники по токену.

---

## Кейс 2 — MedPartners (обработка архива прайсов партнёров)

| # | Требование ТЗ | Статус | Где / комментарий |
|---|---|:--:|---|
| 4.1 | Приём ZIP через интерфейс/CLI | ✅ | `/ingest/upload-batch` разворачивает zip |
| 4.1 | Авто-определение типа файла | ✅ | `detect_and_parse()` |
| 4.1 | Очередь обработки со статусом | ✅ | `IngestionRun` (=PriceDocument): status/parse_log per-документ |
| 4.1 | Сохранение оригиналов для реобработки | ✅ | `storage.py` → `/data/uploads/<run_id>` (постоянный том); reprocess из оригинала |
| 4.2 | PDF текстовый (таблицы) | ✅ | `pdfplumber`/pymupdf |
| 4.2 | PDF скан → OCR + постобработка | ✅ | `ocr.py` (tesseract rus/kaz/eng) |
| 4.2 | XLSX: все листы, поиск строки заголовков | ✅ | обход всех листов + эвристика заголовков |
| 4.2 | **DOCX + tracked changes** (принять правки) | ✅ | `archive_extractor.parse_docx`, `_accept_tracked_changes` |
| 4.3 | Сопоставление: точное + синонимы + нечёткое | ✅ | `normalizer.py` |
| 4.3 | Порог уверенности конфигурируемый | ✅ | `match_confidence_threshold=0.78`, `semantic_threshold=0.72` |
| 4.3 | Unmatched-очередь + ручное сопоставление | ✅ | `/review/queue`, `/review/price/{id}` (confirm/reassign/reject) |
| 4.4 | Валидация: цена>0, число | ✅ | цена>0 и ≤100M KZT |
| 4.4 | Правило «нерезидент ≥ резидент» | ✅ | валидация `price_nonresident ≥ price_resident` |
| 4.4 | Правило «отклонение >50% → аномалия» | ✅ | флаг аномалии при отклонении >50% |
| 4.4 | Дата прайса не в будущем | ❌ | проверки даты в будущем нет |
| 4.4 | Версионирование (старая цена в архив) | 🟡 | `PriceHistory` пишет историю изменений |
| 4.5 | REST API + **OpenAPI** | ✅ | FastAPI авто-`/docs` + `/openapi.json` |
| 4.5 | `/services`, `/services/{id}/partners` | 🟡 | есть аналоги (`/services`, `/compare`, `/clinics/{id}/prices`), но **не теми путями** ТЗ |
| 4.5 | `/partners`, `/partners/{id}/services` | 🟡 | реализовано как `/clinics`… (нейминг clinic, не partner) |
| 4.5 | `/search`, `/unmatched`, `/match` | 🟡 | `/search`✅, unmatched=`/review/queue`, match=`/review/price` (другие пути) |
| 4.6 | UI: поиск → партнёры с ценами рез/нерез | ✅ | `price_resident`/`price_nonresident` (заполнено на 3767 ценах) |
| 4.6 | Админ: загрузка архива, статус, очередь верификации | ✅ | `/admin`, `/admin/review` |
| 4.6 | Дашборд: обработано / % нормализации / в очереди | ✅ | `/ingest/stats` + админ-дашборд |
| 5 | Точность нормализации ≥70% авто | ✅ | боевой прогон: 10 документов, 16760 позиций, **72.0%** (цель ≥70% достигнута) |
| 5 | Исходные файлы не удаляются | ✅ | оригиналы в `/data/uploads/<run_id>` (см. 4.1) |

### Схема БД — расхождения с Кейсом 2

| Поле ТЗ | В реализации |
|---|---|
| `partner.bin` (БИН) | ❌ нет поля у `Clinic` |
| `partner.contact_email` | ❌ нет (есть только phone) |
| `PriceDocument` (doc_id, file_name, parse_status, raw_content…) | ✅ роль играет `IngestionRun`: status/parse_log/file_name/clinic_id/effective_date/file_path/matched/needs_review |
| `PriceItem.price_resident_kzt` / `price_nonresident_kzt` | ✅ `price_resident`/`price_nonresident` (заполнено на 3767 ценах) |
| `PriceItem.price_original` / `currency_original` (USD/RUB) | ✅ конвертация USD→KZT с сохранением оригинала |
| `PriceItem.is_verified` / `verification_note` | 🟡 верификация через review (`matched`/`needs_review`), отдельных полей нет |
| `PriceItem.effective_date` | ✅ `effective_date` на `IngestionRun` (+ `valid_from` у цены) |
| `Service.icd_code` (МКБ) | ❌ нет |
| `Service.synonyms`, `category` | ✅ есть |

---

## Главные пробелы (приоритет для доведения под ТЗ)

Большинство прежних пробелов закрыто (DOCX+tracked changes, резидент/нерезидент, конвертация валют, хранение оригиналов ≥90 дней, бизнес-правила валидации, UI-фильтры, подписка/маршрут). Остаётся:

1. **Поля БД Кейса 2**: `partner.bin` (БИН), `partner.contact_email`, `Service.icd_code` (МКБ) — отсутствуют.
2. **Правило «дата прайса не в будущем»** — единственная невыполненная проверка §4.4.
3. **Эндпоинты под нейминг ТЗ** (`/partners`, `/services/{id}/partners`, `/match`, `/unmatched`) — функционал есть, но под именами `clinic`/`review`; нужны алиасы под Swagger-контракт.
4. **Поля `is_verified`/`verification_note`** у цены — верификация идёт через review (`matched`/`needs_review`), отдельных полей нет.

## Что закрыто сильнее ТЗ
Семантическая нормализация (pgvector) + Gemini 2.5-flash (Vertex AI), онтология+ОСМС, корзина-рецепт, лиды/монетизация, история цен, чат, self-service портал клиник, авторизация админки + rate-limit, Alembic-миграции, Postgres16/pgvector-рантайм, боевой прогон автонормализации архива (72.0%), CI.
