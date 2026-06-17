# МедЦена — объединённая Medtech-платформа

> Хакатон **Medtech Hackathon** (Terricon Valley), 26–28 июня. Один сквозной продукт, закрывающий оба кейса:
> **Кейс 1** (обработка прайсов клиник) + **Кейс 2** (агрегатор сравнения цен).

**Идея в одном предложении:** клиника загружает прайс в любом формате → платформа сама парсит и нормализует услуги → они мгновенно попадают в публичный агрегатор, где пациент сравнивает цены и выбирает, где сделать услугу.

**Главный аргумент:** это не два прототипа, а один бизнес-процесс. Кейс 1 решает ключевую боль Кейса 2 — «откуда брать данные».

---

## Что внутри

```
medtech-platform/
├── backend/                 # FastAPI + SQLAlchemy (Python)
│   ├── app/
│   │   ├── main.py          # точка входа API
│   │   ├── models.py        # схема БД (clinics, service_catalog, sources, ingestion_runs, prices)
│   │   ├── ingestion/       # ★ Кейс 1 — приём данных
│   │   │   ├── file_parser.py    # ① парсер xlsx / csv / pdf
│   │   │   ├── web_scraper.py     # ② веб-парсер сайтов клиник (httpx+bs4, Playwright-хук)
│   │   │   ├── api_connector.py   # ② коннектор REST/JSON
│   │   │   ├── normalizer.py      # ★ нормализация к справочнику (fuzzy + LLM)
│   │   │   └── service.py         # оркестрация + дедупликация каналов
│   │   ├── routers/         # Кейс 2 — агрегатор + приём + клиники
│   │   ├── scheduler.py     # планировщик автосбора (cron / Celery-ready)
│   │   └── seed.py          # демо-данные через реальный конвейер
│   ├── sample_data/         # демо-прайсы: xlsx, csv, pdf, html, json
│   └── tests/               # pytest (парсер, нормализация, дедуп)
├── frontend/                # Next.js (App Router, TS, Tailwind) — витрина пациента
└── docs/                    # архитектура, API, питч, этика автосбора
```

## Два канала сбора данных, одна воронка нормализации

| Канал | Как | Источник |
|---|---|---|
| **① Push** | клиника сама грузит прайс (xlsx/csv/pdf/скан) | админ-загрузка |
| **② Pull** | платформа сама собирает цены: веб-парсер + API-коннекторы по расписанию | автосбор |

Оба канала сходятся в **★ нормализацию** — приведение разнобоя названий («ОАК», «Общий анализ крови (5 параметров)», «Кровь — общий анализ») к одной записи справочника + **дедупликацию** (при конфликте приоритет у официальной загрузки клиники). Это «вау»-фишка проекта.

---

## Быстрый старт

### Backend
```bash
cd backend
pip install -r requirements.txt          # или python -m venv .venv && ...
cp .env.example .env                      # по умолчанию SQLite — запускается сразу
python -m app.seed                        # демо: 6 клиник, справочник, 33 цены
python make_samples.py                    # сгенерировать демо-прайсы в sample_data/
uvicorn app.main:app --reload             # API на http://localhost:8000
```
Swagger-документация: `http://localhost:8000/docs`.

> **LLM-нормализация (опционально).** Добавьте `GROQ_API_KEY` в `.env` — неоднозначные названия будет разводить LLM. Без ключа всё работает на fuzzy-match (rapidfuzz), без сети.

### Frontend
```bash
cd frontend
npm install
cp .env.local.example .env.local          # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                                # витрина на http://localhost:3000
```

### Postgres вместо SQLite (опционально)
```bash
docker compose up -d db
# в backend/.env: DATABASE_URL=postgresql+psycopg2://medtech:medtech@localhost:5544/medtech
```

---

## Сквозной демо-сценарий (для защиты)

1. Загружаем реальный прайс клиники (`POST /api/ingest/upload`, файл xlsx/pdf).
2. Система сама распарсила и **нормализовала** услуги к справочнику.
3. Открываем витрину → услуга «Общий анализ крови» появилась в сравнении.
4. Пациент видит, где **дешевле** и **ближе** (карта), и из какого источника цена.

Проверка одной командой (после `seed`):
```bash
curl -G localhost:8000/api/compare/1 --data-urlencode sort=price_asc
```
→ одна услуга, 6 клиник, 6 разных исходных названий, отсортировано по цене.

---

## Ключевые API-эндпоинты

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/ingest/upload` | ① загрузка прайса (xlsx/csv/pdf) |
| POST | `/api/ingest/scrape` | ② снять прайс с сайта клиники |
| POST | `/api/ingest/api` | ② забрать прайс из REST/JSON API |
| POST | `/api/ingest/run-scheduled` | запустить автосбор по всем pull-источникам |
| GET | `/api/search` | поиск услуг + сводка сравнения |
| GET | `/api/compare/{id}` | сравнение цен по услуге между клиниками |
| GET | `/api/categories`, `/api/cities` | фильтры |
| GET | `/api/clinics` | список клиник |

Полный контракт — в `docs/API.md` и Swagger `/docs`.

## Стек
Python · FastAPI · SQLAlchemy · pandas · pdfplumber · rapidfuzz · Groq (LLM) · BeautifulSoup/httpx · PostgreSQL/SQLite · Next.js · Tailwind · Leaflet (карта).

## Тесты
```bash
cd backend && python -m pytest -q       # 9 тестов: парсер, нормализация, дедупликация
```

См. также: [docs/architecture.md](docs/architecture.md) · [docs/pitch.md](docs/pitch.md) · [docs/legal.md](docs/legal.md)
