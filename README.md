# МедЦена — объединённая Medtech-платформа

[![CI](https://img.shields.io/github/actions/workflow/status/m34959203/medtech-aggregator/ci.yml?branch=main&label=CI)](https://github.com/m34959203/medtech-aggregator/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%C2%B7%20Next.js-black)]()
[![Hackathon](https://img.shields.io/badge/Terricon-Medtech%20Hackathon-7c3aed)]()

> Хакатон **Medtech Hackathon** (Terricon Valley), 26–28 июня. Один сквозной продукт, закрывающий оба кейса:
> **Кейс 1 — MedPrice** (агрегатор сравнения цен) + **Кейс 2 — MedArchive** (обработка архива прайсов клиник). Оба кейса закрыты на 100%.

**Идея в одном предложении:** клиника загружает прайс в любом формате → платформа сама парсит и нормализует услуги → они мгновенно попадают в публичный агрегатор, где пациент сравнивает цены и выбирает, где сделать услугу.

**Главный аргумент:** это не два прототипа, а один бизнес-процесс. Кейс 2 решает ключевую боль Кейса 1 — «откуда брать данные».

**В проде** (`medtech.technokod.kz`, живой Postgres): **107 клиник**, **1985 услуг** в каталоге (из них **1191** из официального «Справочник услуг.xlsx» с кодами тарификатора), **10 078 цен** в **14 городах**, тарифы резидент/нерезидент на **3767 ценах**, очередь ревью — **4264** позиции.

---

## Что внутри

```
medtech-platform/
├── backend/                 # FastAPI + SQLAlchemy + pgvector (Python)
│   ├── app/
│   │   ├── main.py          # точка входа API
│   │   ├── models.py        # схема БД (clinics, service_catalog, sources, ingestion_runs,
│   │   │                    #          prices, price_history, price_subscriptions, leads)
│   │   ├── ingestion/       # ★ приём данных (оба кейса)
│   │   │   ├── file_parser.py    # парсер xlsx/xls / csv / pdf (текст+OCR) / docx
│   │   │   ├── web_scraper.py     # веб-парсер сайтов клиник (httpx+bs4, Playwright-хук)
│   │   │   ├── api_connector.py   # коннектор REST/JSON
│   │   │   ├── normalizer.py      # ★ нормализация к справочнику (fuzzy → семантика pgvector → Gemini LLM + биоматериал-гарды)
│   │   │   └── service.py         # оркестрация + дедупликация каналов
│   │   ├── routers/         # агрегатор + приём архива + клиники
│   │   │   └── chat.py      # 🤖 чат-помощник пациента (retrieval-injection, Gemini/Vertex)
│   │   ├── scheduler.py     # планировщик автосбора (cron 6ч)
│   │   └── seed.py          # демо-данные через реальный конвейер
│   ├── sample_data/         # демо-прайсы: xlsx, csv, pdf, html, json
│   └── tests/               # pytest (парсер, нормализация, дедуп, чат)
├── frontend/                # Next.js (App Router, TS, Tailwind) — витрина пациента
│   └── components/          # ClinicMap (Яндекс.Карты) · ChatWidget (🤖 помощник)
└── docs/                    # архитектура, API, питч, этика автосбора
```

## Два канала сбора данных, одна воронка нормализации

| Канал | Как | Источник |
|---|---|---|
| **① Push** | клиника сама грузит прайс (xlsx/csv/pdf/скан) | админ-загрузка |
| **② Pull** | платформа сама собирает цены: веб-парсер + API-коннекторы по расписанию | автосбор |

Оба канала сходятся в **★ нормализацию** — приведение разнобоя названий («ОАК», «Общий анализ крови (5 параметров)», «Кровь — общий анализ») к одной записи справочника + **дедупликацию** (при конфликте приоритет у официальной загрузки клиники). Это «вау»-фишка проекта.

> **Движок можно проверить вживую** — страница `/normalizer` (`POST /api/ingest/preview`): введите любые «кривые» названия → увидите, как и каким методом (нечёткое сопоставление / семантика pgvector / LLM-арбитраж Gemini) движок сводит их к справочнику, с уверенностью. Вход контролирует пользователь — это доказывает, что нормализация **не захардкожена**. Сухой прогон, в БД ничего не пишется.
>
> Двухуровневость по дизайну: bulk-сид реальных данных курируется детерминированной картой (контроль качества), а боевой приём новых прайсов идёт через каскад **fuzzy → семантика (fastembed + pgvector) → Gemini-арбитраж + биоматериал-гарды** — тот самый, что на `/normalizer`.

---

## Кейс 2 — MedArchive: обработка архива прайсов партнёров ✅ закрыт 100% + боевой прогон

Платформа обрабатывает **готовый архив прайс-листов клиник-партнёров**
на **официальном справочнике услуг** (1191 позиция с кодом тарификатора): разобрать
разнородные документы, извлечь цены с тарифами **резидент/нерезидент**, нормализовать
к справочнику и собрать верифицированную базу «кто оказывает услугу и по какой цене».

| Возможность | Как |
|---|---|
| Форматы | DOCX (с **принятием tracked changes**), XLSX/XLS (многострочная шапка, все листы), PDF-текст, PDF-скан → **OCR** (tesseract rus/kaz/eng) |
| Тарифы | раздельно **резидент / нерезидент** |
| Нормализация | **code-first** по коду тарификатора (точно → 100%) → нечётко (rapidfuzz) → семантика (fastembed + pgvector) → **Gemini-арбитраж** + биоматериал-гарды |
| Валидации (§4.4) | цена>0 и ≤100M KZT, нерезидент≥резидент, аномалия цены >50% к прошлой версии, версионирование |
| Оригиналы | сохранение исходных файлов в `/data/uploads` + **reprocess из оригинала** |
| Артефакт | **дашборд качества обработки** (`GET /api/archive/quality`): документы, % автонормализации, очередь |

> **Боевой прогон** (архив хакатона): **10 документов** во всех форматах, **16 760 позиций**,
> автонормализация **72.0 %** (цель ≥70 % достигнута), **4690** позиций ушло в ручную ревью-очередь.

```bash
# приём архива через API: ZIP или набор файлов, тарифы резидент/нерезидент
curl -F file=@archive.zip localhost:8000/api/ingest/archive
```

API-контракт MedArchive: `POST /api/ingest/archive` (+`/{run_id}/reprocess`),
`/api/partners`, `/api/partners/{id}/services` (с резидент/нерезидент),
`/api/services/{id}/partners`, `/api/unmatched`, `POST /api/match`, `GET /api/archive/quality`.
Очередь несопоставленных позиций — обучающая: каждый ручной `POST /match` запоминается
синонимом, и охват автонормализации растёт с использованием.

---

## 🤖 Чат-помощник пациента

Диалоговый поиск по витрине: пациент спрашивает «где дешевле общий анализ крови в Алматы?» — бот находит и сравнивает клиники. Ключевой принцип — **бот не выдумывает цены**: это надстройка над агрегатором, а не «всезнающий» LLM.

- **Retrieval-injection.** Помощник сначала **сам ищет** по тому же нормализованному справочнику, что и витрина (фаззи-подбор услуги + детект города), вкладывает найденные предложения в контекст модели, и та отвечает **строго по этим данным**, выделяя самую выгодную клинику.
- **OCR в чате.** Пациент может прислать **фото/скан направления** прямо в виджет (`POST /api/chat/vision`): OCR (tesseract rus/kaz/eng, тот же движок, что у `/recipe`) распознаёт услуги → нормализатор привязывает их к справочнику → бот отвечает теми же ценами витрины. На телефоне кнопка-камера открывает съёмку сразу.
- **LLM — Gemini 2.5-flash** (через Vertex AI, единая точка `llm.chat` с нормализатором/recheck) с фолбэком на **AlemLLM/Groq** через `LLM_PROVIDER`. Tool-calling намеренно не используется (retrieval-injection надёжнее и провайдер-агностичен).
- **Демо живёт всегда.** Без ключа/SA провайдера (или при сбое сети) бот деградирует в детерминированный поиск-сводку по базе.

Бэкенд: `backend/app/routers/chat.py` (`POST /api/chat`, `POST /api/chat/vision`). Фронт: `frontend/components/ChatWidget.tsx` (плавающий виджет на всех страницах, с приёмом фото).

---

## Быстрый старт

### Backend
```bash
cd backend
pip install -r requirements.txt          # или python -m venv .venv && ...
cp .env.example .env                      # по умолчанию SQLite — запускается сразу
python -m app.migrate                     # схема через Alembic-миграции (идемпотентно)
python -m app.seed                        # демо: 6 клиник, справочник, 33 цены
python -m app.seed_real                   # РЕАЛЬНЫЕ данные: живой парсинг KDL-Olymp
                                          # (с соблюдением robots.txt) + реальные прайсы клиник
python make_samples.py                    # сгенерировать демо-прайсы в sample_data/
uvicorn app.main:app --reload             # API на http://localhost:8000
```
Swagger-документация: `http://localhost:8000/docs`.

> **LLM-нормализация (опционально).** Настройте Vertex AI (Gemini 2.5-flash) или добавьте `ALEM_API_KEY`/`GROQ_API_KEY` в `.env` — неоднозначные названия разводит LLM-арбитраж. Без ключа всё работает на каскаде fuzzy (rapidfuzz) → семантика (fastembed + pgvector), без внешней сети.
>
> **Чат-помощник (опционально).** По умолчанию — Gemini 2.5-flash (Vertex), фолбэк `LLM_PROVIDER=alem`/`groq` + соответствующий ключ в `backend/.env`. Без ключа бот отвечает детерминированным поиском по базе.
>
> **Карта.** Фронту нужен `NEXT_PUBLIC_YANDEX_MAPS_API_KEY` (бесплатный ключ Яндекс.Карт, ограничен по домену). Без ключа вместо карты — аккуратный плейсхолдер. В балуне метки клиники — кнопка **«Отправить в WhatsApp»** (React-модалка ввода номера → `wa.me/<номер>` с адресом, координатами, точкой на карте и маршрутом).

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local                # NEXT_PUBLIC_API_URL + NEXT_PUBLIC_YANDEX_MAPS_API_KEY
npm run dev                                # витрина на http://localhost:3000
```

### Postgres (прод-рантайм; в dev — опционально)
SQLite хватает для разработки. Прод (`docker-compose.prod.yml`) поднимает Postgres
(`medtech-db`); схема применяется миграциями на старте (`entrypoint → python -m app.migrate`).
```bash
docker compose up -d db                     # dev: локальный Postgres на :5544
# в backend/.env: DATABASE_URL=postgresql+psycopg2://medtech:medtech@localhost:5544/medtech
python -m app.migrate                       # применить схему
```
**Перенос данных SQLite → Postgres** (разовый cutover):
```bash
python copy_to_pg.py sqlite:////data/medtech.db \
  postgresql+psycopg2://medtech:medtech@medtech-db:5432/medtech
```
Прод-env: `POSTGRES_PASSWORD`, `ADMIN_TOKEN` (иначе админ-зона закрыта), `COOKIE_SECURE=true`.

---

## Сквозной демо-сценарий (для защиты)

0. (Опц., но сильно) Открываем `/normalizer`, жюри само вводит кривые названия → движок сводит к справочнику вживую (доказывает, что не хардкод). Или грузим «грязный» прайс `backend/sample_data/dirty_pricelist.csv`.
1. Открываем **`/admin`** → загружаем **архив** прайсов (.zip / несколько файлов) одним пакетом, видим отчёт по каждому файлу и журнал прогонов; выгружаем единый каталог в xlsx/csv (артефакт Кейса 1).
2. Система сама распарсила и **нормализовала** услуги к справочнику.
3. Открываем витрину → услуга «Общий анализ крови» появилась в сравнении.
4. Пациент видит, где **дешевле** и **ближе** (карта), и из какого источника цена.
5. Спрашиваем 🤖 **чат-помощника** «где дешевле общий анализ крови?» → бот находит и называет самую выгодную клинику строго по базе.

Проверка одной командой (после `seed`):
```bash
curl -G localhost:8000/api/compare/1 --data-urlencode sort=price_asc
```
→ одна услуга, 6 клиник, 6 разных исходных названий, отсортировано по цене.

---

## Ключевые API-эндпоинты

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/services` · `/api/services/{id}/partners` | каталог услуг и кто их оказывает |
| GET | `/api/partners` · `/api/partners/{id}/services` | клиники и их прайс (резидент/нерезидент) |
| GET | `/api/search` · `/api/suggest` | поиск услуг + автодополнение |
| GET | `/api/unmatched` · POST `/api/match` | очередь ревью и ручное сопоставление |
| POST | `/api/ingest/archive` (+`/{run_id}/reprocess`) | приём архива (.zip / N файлов), reprocess из оригинала |
| POST | `/api/ingest/upload-batch` | пакетный приём прайсов → один отчёт |
| POST | `/api/ingest/preview` | сухой прогон нормализации (live-демо движка, без записи в БД) |
| GET | `/api/archive/quality` | дашборд качества обработки архива |
| POST | `/api/compare-clinics` | сравнение-таблица клиник по услуге |
| GET | `/api/clinics/{id}/profile` | карточка клиники |
| POST | `/api/subscriptions` | подписка на снижение цены (WhatsApp) |
| POST | `/api/chat` | 🤖 чат-помощник пациента (диалоговый поиск по витрине, Gemini/Vertex) |
| POST | `/api/chat/vision` | 🤖 OCR в чате: фото/скан направления → распознавание услуг → ответ по витрине |

Полный контракт — в `docs/API.md` и Swagger `/docs`.

## Стек
Python · FastAPI · SQLAlchemy · PostgreSQL 16 + **pgvector** · fastembed (multilingual MiniLM) · pandas · pdfplumber · tesseract-OCR · rapidfuzz · BeautifulSoup/httpx · **Gemini 2.5-flash (Vertex AI)** с фолбэком AlemLLM/Groq (чат-помощник + LLM-арбитраж нормализации) · WhatsApp-gateway (Baileys) · Next.js 15 · Tailwind · Яндекс.Карты (карта клиник) · Docker Compose (`docker-compose.prod.yml`).

## Тесты
```bash
cd backend && python -m pytest -q       # парсер, нормализация, дедуп, чат, приём архива, экспорт
```

## Roadmap

- [x] Оба кейса закрыты на 100% в одном сквозном продукте (приём/архив → нормализация → агрегатор + чат-помощник)
- [x] Прод задеплоен на `medtech.technokod.kz` (Docker Compose, Postgres 16 + pgvector)
- [ ] Личный кабинет клиники (статусы загрузок, ручная модерация спорных сопоставлений)
- [ ] Расширение pull-источников и устойчивый Playwright-скрапинг JS-сайтов
- [ ] Прод-релиз `v1.0.0`

Подробно: [docs/roadmap.md](docs/roadmap.md).

## Вклад и лицензия

- Как участвовать: [CONTRIBUTING.md](CONTRIBUTING.md)
- История изменений: [CHANGELOG.md](CHANGELOG.md)
- Лицензия: [MIT](LICENSE)

См. также: [docs/architecture.md](docs/architecture.md) · [docs/pitch.md](docs/pitch.md) · [docs/legal.md](docs/legal.md)
