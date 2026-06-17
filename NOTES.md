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

## TODO / куда расти
- Векторный матчинг (pgvector) для семантической нормализации.
- OCR сканов (Tesseract/EasyOCR) — сейчас только текстовый слой PDF.
- Админ-UI загрузки прайса + дашборд ingestion_runs.
- Запись на приём, отзывы (явно вне MVP хакатона).
