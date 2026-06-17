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

## TODO / куда расти
- Векторный матчинг (pgvector) для семантической нормализации.
- OCR сканов (Tesseract/EasyOCR) — сейчас только текстовый слой PDF.
- Админ-UI загрузки прайса + дашборд ingestion_runs.
- Запись на приём, отзывы (явно вне MVP хакатона).
