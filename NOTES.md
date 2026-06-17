# NOTES — живой журнал разработки

Хакатон Terricon Medtech, 26–28 июня. Объединённая платформа: Кейс 1 (приём прайсов) + Кейс 2 (агрегатор).

## Статус
- [x] Скелет репо, git init.
- [x] Backend: FastAPI + SQLAlchemy, схема БД (5 таблиц).
- [x] Кейс 1 — приём: file_parser (xlsx/csv/pdf), web_scraper (httpx+bs4 + Playwright-хук), api_connector.
- [x] ★ Нормализация: fuzzy (rapidfuzz) + LLM (Groq, опц.) + самообучение синонимов.
- [x] Дедупликация каналов с приоритетом upload > api > web_scrape.
- [x] Планировщик автосбора (cron-ready, /api/ingest/run-scheduled).
- [x] Кейс 2 — агрегатор: /api/search, /api/compare/{id}, фильтры город/цена/категория.
- [x] Seed: 6 клиник (Алматы/Астана с координатами), справочник 15 услуг, 33 цены через реальный конвейер.
- [x] Sample data: xlsx/csv/pdf/html/json генерируются make_samples.py.
- [x] Тесты: 9 pytest (парсер, нормализация, дедуп) — все зелёные.
- [x] Проверено вручную: upload xlsx→7 match, pdf→parsed, scrape-html→6 match, compare сортирует 6 разных raw-имён в одну услугу.
- [x] Docs: README, architecture, API, pitch, legal.
- [x] Frontend: Next.js витрина — поиск, сравнение, карта Leaflet; build зелёный.
- [x] Сквозная интеграция backend+frontend проверена (SSR тянет живые данные: «1900 ₸ / Лучшая цена / Официально от клиники»).
- [x] CI (GitHub Actions): pytest бэка + build фронта.

## Технические заметки / гочи
- На ЭТОМ сервере порт 8000 занят чужим процессом → тестировал на 8077. Канонический дефолт проекта = 8000.
- Ubuntu 24: python3.12-venv нет, sudo не работает → deps ставил `pip install --user --break-system-packages`.
- Без GROQ_API_KEY английские названия в PDF не матчатся на русский справочник → помечаются needs_review (ожидаемо). С ключом LLM их разведёт.
- Карта: Leaflet/OSM (2GIS-ключа нет).
- DATABASE_URL: SQLite по умолчанию (мгновенный запуск), Postgres через docker-compose опц.

## Деплой (technokod.kz)
- Прод-сборка: `docker compose -f docker-compose.prod.yml up -d --build` → 2 контейнера: `medtech-frontend` (:3000) + `medtech-backend` (uvicorn :8000, SQLite в volume `medtech_data`, auto-seed если пусто).
- Один публичный хост `medtech.technokod.kz` → фронт; `/api/*` и `/health` проксирует Next (rewrites → `http://medtech-backend:8000`). NEXT_PUBLIC_API_URL=https://medtech.technokod.kz вшит на build, INTERNAL_API_URL для SSR.
- Сеть `medtech_net`; контейнер `cloudflared-technokod` подключён к ней (`docker network connect medtech_net cloudflared-technokod`) → видит `medtech-frontend:3000`. Проверено throwaway-curl'ом.
- Хост-порты для локальной проверки: 8088→фронт, 8089→бэк (только 127.0.0.1).
- ✅ **ЖИВОЙ (2026-06-17):** `https://medtech.technokod.kz` проверен курлом — фронт 200, `/health` ok, `/api/*` 200. Public Hostname в CF Zero Trust добавлен.
- Гоча: если watchtower пересоздаст `cloudflared-technokod` — повторить `docker network connect medtech_net cloudflared-technokod`.

## Демо-данные / приём (2026-06-17)
- Демо-сид теперь **opt-in**: `entrypoint.sh` сидит только при `SEED_DEMO=1` (или `true`) И пустой БД. По умолчанию прод стартует **пустым** (только схема). Код `backend/app/seed.py` сохранён — локально `python -m app.seed`, на проде вернуть демо = выставить `SEED_DEMO=1` в compose + пересоздать.
- Прод-БД очищена от демо-данных: `docker volume rm medtech-platform_medtech_data` + recreate. Проверено: `/api/clinics`→`[]`, `/api/search`→`[]`.
- Реальный приём: сперва `POST /api/clinics` (создать клинику), затем `POST /api/ingest/upload` (clinic_id + xlsx/csv/pdf). DELETE-клиники в API нет.
- Багфикс парсера CSV: автодетект `sep=None` путал запятую внутри текста (`;`-файл с «Тариф, тенге») с разделителем и терял строки. Теперь перебор `; , \t None`, выбор по (макс. позиций, затем макс. колонок) — тай-брейк по колонкам ловит случай слипшихся имя+цена. Регресс-тесты: `test_csv_semicolon_with_commas_in_text`, `test_csv_plain_comma_not_merged`. 11 pytest зелёные.

## Реальные данные (2026-06-17)
- На проде **65 реальных клиник/лабораторий в 5 городах: Алматы (22), Астана (22), Караганда (14), Актобе (4), Шымкент (3) — 46 услуг, 419 живых цен** — спарсено с публичных прайсов, не демо. Проверено: «Приём терапевта 1270–15000 ₸ · 29 клин.», «УЗИ брюшной полости 2000–10000 ₸ · 44 клин. (все 5 городов)».
- Расширение через 103.kz многоагентно (3 параллельных research-агента по городам): отбор по факту прогона адаптером (≥4–5 сравнимых услуг). Стоматологии/пластика/ЭКО автоматически отсеиваются (0 медицинских сравнимых → loader пропускает «0 позиций»).
- **INVIVO и SAPA ПОДКЛЮЧЕНЫ (2026-06-17)** через `scrape_lab_platform` — реверс их Django-AJAX: каталог отдаётся не в статике, а сессионным `GET /ru/ajax/<city>/a-and-c-search-with-panels/?service_type=anl` (любой ≠pac → отдельные анализы; pac=чек-ап пакеты). Нужны cookies (csrftoken/sessionid) со страницы /analyzes/, иначе 500. **Playwright НЕ нужен в рантайме** — использовался только для перехвата XHR при разведке эндпоинта (`page.on("response")`); рантайм — чистый httpx. Markup двух видов: INVIVO `.results-analyzes-item` (имя до «Код:»), SAPA строки `.row` с `.cell__value`. Добавлены: INVIVO Алматы/Астана, SAPA Алматы/Астана/Шымкент (INVIVO Караганда — 500, нет филиала).
- Расширение через 103.kz: +20 клиник одним универсальным адаптером (Damed, On Clinic, Medical Park, Рахат, Smart Health, Президентская клиника, Прогресс Мед, Ansar, КДЛ Олимп…); отобраны те, что дают ≥7 сравнимых услуг.
- Готча курации без LLM: органные ключи («брюшной полости», «почек») ловили операции/др. услуги и мержились в УЗИ (выброс 200000 ₸). Фикс: `_ULTRASOUND_ONLY` засчитывает их только при наличии «узи» в названии.
- Адаптеры скрапера (`web_scraper.py`, точные селекторы):
  - `invitro.kz` → `.analyzes-item` (имя + `.analyzes-item__total--price`);
  - `gemotest.kz` → `.analysis` (имя `a` + `.analysis-price`);
  - **универсальный `*.103.kz`** → карточки `.PersonalCardOfferItem`(вар. A) / `.PersonalOffers__item`(вар. B), пропуск «уточняйте». Покрывает десятки клиник РК (Emirmed, Сункар, Авиценна, Мой Доктор, Mediker, Мейірім…).
  - generic `<table>`: имя = самая текстовая ячейка, цена = макс. число (чинит таблицы с колонкой-нумератором, напр. «Луч»).
  - `scrape_url` сам выбирает адаптер по домену (suffix-match для платформ), иначе generic.
- Загрузчик `backend/load_real_data.py`: создаёт реальные клиники + скрапит их прайсы + курирует к сравнимым услугам (лаборатории→анализы, клиники→приёмы/УЗИ/ЭКГ по keyword-whitelist), грузит через `ingest_items` (та же нормализация). **Перезалить реальные данные:** `docker exec -i -w /app medtech-backend python load_real_data.py`.
- Источники со СЛОЖНЫМ парсингом (отложены, нужен Playwright/JSON-API): INVIVO, SAPA (JS-рендер), КДЛ Олимп (anti-bot/redirect-loop). On Clinic/Rahat — свои таблицы, мини-парсеры на потом.
- Координаты клиник приблизительные (по адресу); перед акцентом на карту — перегеокодировать.

## TODO / куда расти
- Векторный матчинг (pgvector) для семантической нормализации.
- OCR сканов (Tesseract/EasyOCR) — сейчас только текстовый слой PDF.
- Админ-UI загрузки прайса + дашборд ingestion_runs.
- Запись на приём, отзывы (явно вне MVP хакатона).
