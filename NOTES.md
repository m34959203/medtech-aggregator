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

## Аудит Cowork + контакты (2026-06-18)
- BUG-1 (МРТ обещался в hero, но не в каталоге): добавлены SPEC МРТ/КТ головного мозга → «МРТ головного мозга» 8 клиник (диагностические центры).
- BUG-2 (мешались первичный/повторный/онлайн/детский приёмы, «Лучшая цена» врала): приёмы теперь только первичные взрослые — `_NONPRIM` exclude (повторн/онлайн/детск/дистанц/на дому/выезд).
- **Реальные контакты клиник:** `fetch_103kz_card` тянет из JSON-LD `LocalBusiness` на 103.kz реальные адрес+телефон+КООРДИНАТЫ (geo) каждого филиала (Organization-блок = шаблонный головной офис, игнор). Для лаб-сетей INVIVO/SAPA — `fetch_contact` (INVIVO даёт geo+адрес, SAPA/Gemotest/INVITRO — телефон через `tel:`). Итог: 0 клиник без телефона, у 103.kz-клиник реальные адреса И точные пины на карте (вместо джиттера вокруг центра города).

## Реальные данные (2026-06-17)
- На проде **75 реальных клиник/лабораторий в 7 городах: Алматы (24), Астана (25), Караганда (14), Актобе (5), Шымкент (5), Актау (1), Семей (1) — 50 услуг, 487 живых цен** — спарсено с публичных прайсов, не демо. Проверено: «Глюкоза 980–1700 ₸ · 16 предлож. во всех 7 городах», «УЗИ брюшной полости 2000–10000 ₸ · 44 клин.».
- КДЛ Олимп в 7 филиалах (Алматы/Караганда/Астана/Шымкент/Актобе/Актау/Семей) — слаги 103.kz: kdlolymp, olimp-36, olimp-15, olimp-41, olimp-kz-3, olimp-61, olimp-114.
- Расширение через 103.kz многоагентно (3 параллельных research-агента по городам): отбор по факту прогона адаптером (≥4–5 сравнимых услуг). Стоматологии/пластика/ЭКО автоматически отсеиваются (0 медицинских сравнимых → loader пропускает «0 позиций»).
- **INVIVO и SAPA ПОДКЛЮЧЕНЫ (2026-06-17)** через `scrape_lab_platform` — реверс их Django-AJAX: каталог отдаётся не в статике, а сессионным `GET /ru/ajax/<city>/a-and-c-search-with-panels/?service_type=anl` (любой ≠pac → отдельные анализы; pac=чек-ап пакеты). Нужны cookies (csrftoken/sessionid) со страницы /analyzes/, иначе 500. **Playwright НЕ нужен в рантайме** — использовался только для перехвата XHR при разведке эндпоинта (`page.on("response")`); рантайм — чистый httpx. Markup двух видов: INVIVO `.results-analyzes-item` (имя до «Код:»), SAPA строки `.row` с `.cell__value`. Добавлены: INVIVO Алматы/Астана, SAPA Алматы/Астана/Шымкент (INVIVO Караганда — 500, нет филиала).
- Расширение через 103.kz: +20 клиник одним универсальным адаптером (Damed, On Clinic, Medical Park, Рахат, Smart Health, Президентская клиника, Прогресс Мед, Ansar, КДЛ Олимп…); отобраны те, что дают ≥7 сравнимых услуг.
- Готча курации без LLM: органные ключи («брюшной полости», «почек») ловили операции/др. услуги и мержились в УЗИ (выброс 200000 ₸). Фикс: `_ULTRASOUND_ONLY` засчитывает их только при наличии «узи» в названии.
- Готчи нормализации ОАК (2026-06-17, баг «ОАК только 1 клиника в Караганде»): (1) лаборатории зовут ОАК «Клинический анализ крови»; (2) многопрофильные клиники отдают и анализы; (3) standalone-СОЭ ложно мержился в ОАК.
- **РЕФАКТОР нормализации на детерминированную карту (2026-06-17, «проверь остальные»):** аудит всех услуг вскрыл системные болезни fuzzy без LLM — дубли-каноны (ЭКГ↔Электрокардиограмма, ТТГ↔Тиреотропный, Глюкоза↔Анализ-на-глюкозу), кросс-загрязнение приёмов (ЛОР→гинеколог, кардиолог=0 офф), приём=процедуры (невролог до 305990₸). Решение в `load_real_data.py`: `SPECS` — упорядоченная карта `(ключ, эталон, категория, require, excludes)`, `_classify()` привязывает сырое имя к эталону НАПРЯМУЮ, минуя fuzzy. Приёмы require=консультация, exclude=процедуры/операции; аналиты exclude=панели; ЭхоКГ раньше ЭКГ. Загрузка детерминированная (conf=1.0, синонимы копятся для поиска). Итог: 51→27 услуг (дубли слиты), кардиолог 0→34, выбросы убраны, 802 цены. Normalizer (fuzzy+LLM) остаётся для живого `/api/ingest/upload`.
- **Фикс поиска (2026-06-17):** искал только по `canonical_name` → «ОАК/сахар/кровь/СРБ» не находили. Теперь поиск матчит и синонимы; `ALIASES` сеют народные названия (ОАК, сахар, диабет, УЗИ сердца…) в синонимы. SQLite хранит JSON-синонимы в `\uXXXX`-эскейпе → SQL-LIKE по кириллице не работает, поэтому фильтр синонимов в Python (`_matches`, справочник мал).
- Адаптеры скрапера (`web_scraper.py`, точные селекторы):
  - `invitro.kz` → `.analyzes-item` (имя + `.analyzes-item__total--price`);
  - `gemotest.kz` → `.analysis` (имя `a` + `.analysis-price`);
  - **универсальный `*.103.kz`** → карточки `.PersonalCardOfferItem`(вар. A) / `.PersonalOffers__item`(вар. B), пропуск «уточняйте». Покрывает десятки клиник РК (Emirmed, Сункар, Авиценна, Мой Доктор, Mediker, Мейірім…).
  - generic `<table>`: имя = самая текстовая ячейка, цена = макс. число (чинит таблицы с колонкой-нумератором, напр. «Луч»).
  - `scrape_url` сам выбирает адаптер по домену (suffix-match для платформ), иначе generic.
- Загрузчик `backend/load_real_data.py`: создаёт реальные клиники + скрапит их прайсы + курирует к сравнимым услугам (лаборатории→анализы, клиники→приёмы/УЗИ/ЭКГ по keyword-whitelist), грузит через `ingest_items` (та же нормализация). **Перезалить реальные данные:** `docker exec -i -w /app medtech-backend python load_real_data.py`.
- Источники со СЛОЖНЫМ парсингом (отложены, нужен Playwright/JSON-API): INVIVO, SAPA (JS-рендер), КДЛ Олимп (anti-bot/redirect-loop). On Clinic/Rahat — свои таблицы, мини-парсеры на потом.
- Координаты клиник приблизительные (по адресу); перед акцентом на карту — перегеокодировать.

## Чат-помощник пациента (2026-06-17, на AlemLLM)
- **Бот = надстройка над агрегатором, а не «всезнающий» LLM.** Бэкенд `app/routers/chat.py`, `POST /api/chat` (`{messages:[{role,content}]}`). Паттерн **retrieval-injection**: сначала ПРИНУДИТЕЛЬНО ищем по тому же нормализованному справочнику, что и витрина (`_detect_city` + `_rank_services` фаззи → `_build_comparison`), вкладываем JSON-результаты в системный промпт, и модель отвечает строго по ним. Бот не выдумывает цены/клиники, помечает 🏆 самую дешёвую.
- **Провайдер на AlemLLM (казахстанская модель)** — нарративный плюс для KZ-хакатона, без geo-block. OpenAI-совместимый endpoint `https://llm.alem.ai/v1`, унифицированный httpx-вызов `_chat_completion` работает и для AlemLLM, и для Groq. Выбор через `LLM_PROVIDER` (auto/alem/groq), см. `config.chat_provider`. **Tool-calling НЕ используем — AlemLLM его не держит** (`tool_choice:auto` отклоняется, named-tool падает 500 на токенизаторе), поэтому и выбран retrieval-injection (надёжнее и провайдер-агностичен).
- **Демо живёт всегда:** без ключа провайдера (или при ошибке сети/квоты) endpoint деградирует в детерминированный `_fallback`.
- Прод-env: `LLM_PROVIDER=alem` + `ALEM_API_KEY=...` в backend (добавлены в `docker-compose.prod.yml`). Локально — `backend/.env` (в .gitignore), документация в `backend/.env.example`.
- Фронт: `components/ChatWidget.tsx` — плавающая кнопка → панель, бренд-токены `brand-*`, подсказки, карточки предложений с «Позвонить», дисклеймер. Подключён в `app/layout.tsx`. API: `lib/api.ts → chat()`.
- Тесты: `backend/tests/test_chat.py` (6). Всего backend **23 pytest зелёные**, фронт build зелёный. Проверено вживую: запрос «Где в Алматы дешевле ОАК?» → AlemLLM вернул «Клиника Б — 1900 ₸» строго по базе.

## Карта переведена на Яндекс.Карты (2026-06-17)
- `components/ClinicMap.tsx` уже был на **Яндекс JS API** (не Leaflet, как в раннем статусе выше). Ключ `NEXT_PUBLIC_YANDEX_MAPS_API_KEY` (бесплатный тариф «с ограничениями», domain-restrict по Referer `medtech.technokod.kz`). Прокинут: `.env.local` (dev), `.env.example`, build-arg в `docker-compose.prod.yml` ← `YANDEX_MAPS_API_KEY`. NEXT_PUBLIC вшивается на build → при смене ключа пересборка.
- Убраны мёртвые зависимости `leaflet/react-leaflet/@types/leaflet`.
- Гоча dev: ключ привязан к `medtech.technokod.kz` → на `localhost` карта пустая, добавить `localhost` в Referer-ограничения в кабинете Яндекса.

## ⚠️ Стратегия защиты (важно для жюри, 2026-06-17)
- **«Точность 100%» — палка о двух концах.** Bulk-загрузка реальных данных идёт через детерминированную карту `SPECS` в `load_real_data.py` (conf=1.0) — это по сути ручной маппинг. Умная нормализация (fuzzy+LLM, `Normalizer`) работает только на ЖИВОМ `/api/ingest/upload`. **На защите ОБЯЗАТЕЛЬНО показывать live-upload:** загрузить новый прайс с непривычным названием → движок сам свёл к справочнику. Иначе «вау»-фишка выглядит как хардкод. Сценарий демо держать наготове.
- **Правовой аспект автосбора — самый острый вопрос.** Реверснули сессионные AJAX INVIVO/SAPA с подстановкой cookies (агрессивнее robots.txt). Позиция: автосбор = временный bootstrap, целевая модель = официальный API + партнёрство; при подключении партнёра парсер отключается (дедуп уже отдаёт приоритет upload/api). Полный текст и фраза для питча — `docs/legal.md`.

## TODO / куда расти
- Векторный матчинг (pgvector) для семантической нормализации.
- OCR сканов (Tesseract/EasyOCR) — сейчас только текстовый слой PDF.
- Админ-UI загрузки прайса + дашборд ingestion_runs.
- Запись на приём, отзывы (явно вне MVP хакатона).

## Чек-поинт 2026-06-18 — продуктовая эволюция (ветка feat/product-evolution)
Решение Дмитрия: строить продукт всерьёз. Guardrail: ПРОД заморожен на `main` до сдачи 26–28.06, эволюция только на ветке, мерж после хакатона.
- `docs/product-roadmap.md` — RICE по Tier 1/2/3 + нарезка на 3 спринта. Метрика пользы: доля сессий «нашёл дешевле медианы».
- **Спринт-1, стержень — модель «база + атрибуты варианта»** (готово, backend): `app/ingestion/variants.py` (`base_key` группирует варианты, `attributes` даёт теги биоматериал/тип приёма, `variant_label`); `ServiceComparison` обогащён `attributes` + `variants` (сёстры с ценами, считаются только в `/compare`, не в `search`). Схему БД НЕ трогали — атрибуты выводятся из канонического имени на чтении. 40 pytest (вкл. сквозной: батч→разведение моча/кровь→compare отдаёт теги+сёстру).
- Осталось в Спринте-1: фронт-теги сопоставимости + «другие варианты», свежесть данных на витрине, петля «цена неверная», мониторинг скраперов.

## Чек-поинт 2026-06-18 (#2) — Спринт-1 ЗАКРЫТ (ветка feat/product-evolution)
Все 5 пунктов Спринта-1 готовы, backend+frontend, 42 pytest + tsc чист. Прод по-прежнему на main (не тронут).
- **Модель вариантов** (стержень) — `variants.py`, `ServiceComparison.attributes/variants` (прошлый чек-поинт).
- **Теги сопоставимости + «другие варианты»** — `ComparisonView`: чипы тегов в заголовке, `VariantsBar` со ссылками на сёстры-варианты (разные продукты сравниваются отдельно).
- **Свежесть данных** — карточка: «обновлено N дней назад» с зелёной/янтарной точкой, устаревшие (>30 дн) приглушаются (opacity-60) + «данные старше 30 дней».
- **Петля «цена неверная»** — модель `PriceReport` (price_reports), `routers/feedback.py` (POST price-report / GET price-reports), кнопка `ReportPriceButton` (stopPropagation, чтобы не триггерить карту), `api.reportPrice`.
- **Мониторинг скраперов** — `/api/ingest/stats` + `empty_runs`/`failed_runs`/`reports_new`; в `/admin` баннер `HealthBanner` (зелёный «здоров» / янтарный список проблем).
Осталось (Спринт-2, после хакатона/при пилоте): needs_review UI, реальная геолокация, лид/запись. Спринт-3: портал клиник, pgvector+онтология, история цен, ОСМС.
Мерж в main — ТОЛЬКО после сдачи 26–28.06.

## Чек-поинт 2026-06-18 (#3) — Спринт-2 (ветка feat/product-evolution)
needs_review UI + лиды + геокодинг. 47 pytest (offline — conftest глушит LLM), tsc+next build чисты. Прод на main не тронут.
- **needs_review UI**: `routers/review.py` (`GET /api/review/queue` — низкая уверенность + новые жалобы; `POST /api/review/price/{id}` confirm/reassign/reject; `POST /api/review/report/{id}`); фронт `/admin/review` (подтвердить/переназначить через select услуг/удалить; жалобы → «обработано»). Ссылка из `/admin`.
- **Лиды/запись** (монетизация): модель `Lead`, `routers/leads.py` (POST с валидацией телефона ≥10 цифр, GET список), компонент `LeadButton` на карточке (инлайн-форма имя+телефон, stopPropagation).
- **Геолокация**: `app/ingestion/geocode.py` (Nominatim, без ключа; `build_query` игнорит заглушки, `is_geocodable` требует номер дома) + скрипт `backfill_geocode.py` (лимит 1 req/сек, `--all`). Живой прогон — вручную (сетевой), логика покрыта тестами.
- **Гоча тестов**: добавлен autouse-фикстура в `tests/conftest.py` — глушит LLM (`json_completion`→None + пустые ключи), иначе локально с ключом нормализатор ходил в сеть и давал новым услугам conf=1.0 (флаки + 8с→1с).
Спринт-2 закрыт. Спринт-3 (портал клиник, pgvector+онтология, история цен, ОСМС) — следующий, gated на пилот. Мерж в main только после сдачи.

## Чек-поинт 2026-06-18 (#4) — Спринт-3, флагман: портал клиники (ветка feat/product-evolution)
Self-service портал — мостик «автосбор → партнёрский актив» (стратегически #1 по анализу). Passwordless (доступ по токену). 53 pytest, tsc+next build чисты. Прод на main не тронут.
- **Модель**: `Clinic.access_token` (unique, выдаётся админом). ⚠️ ГОЧА деплоя: `create_all` НЕ добавит колонку в существующую прод-БД → при мерже нужен `ALTER TABLE clinics ADD COLUMN access_token VARCHAR(64)` (+ unique index). Тесты на свежей БД проходят.
- **Бэкенд** `routers/portal.py`: `POST /api/portal/issue/{clinic_id}` (админ выдаёт токен+ссылку), `GET /api/portal/{token}` (клиника видит свои цены), `PATCH /api/portal/{token}/price/{id}` (правка → source_type=upload, conf=1.0 → автосбор не перетирает), `POST /api/portal/{token}/confirm-all`, `POST /api/portal/{token}/upload` (свой прайс через ingest_items). Чужие цены/битый токен → 404.
- **Фронт**: `/clinic/[token]` (useParams) — таблица цен с инлайн-правкой, «подтвердить все», загрузка своего прайса, бейджи подтверждено/из автосбора; в `/admin` карточка `PortalIssueCard` (id клиники → ссылка). 6 тестов `test_portal.py`.
Осталось в Спринте-3 (тяжёлое/внешнее, следующие заходы): история цен+тренды, pgvector+онтология (нужен Postgres+эмбеддинги), ОСМС/ДМС, OCR сканов. Мерж в main только после сдачи 26–28.06.

## Чек-поинт 2026-06-18 (#5) — Спринт-3: история цен + тренды (ветка feat/product-evolution)
56 pytest, tsc+next build чисты. Прод на main не тронут.
- **Модель** `PriceHistory` (clinic/service/price/recorded_at). Авто-создаётся через create_all при деплое (в отличие от access_token-колонки — новые ТАБЛИЦЫ create_all делает, КОЛОНКИ нет).
- **Захват**: `record_price_history(db,...)` в `service.py` — пишет ТОЛЬКО при изменении цены (дедуп по последней). Вызывается в `ingest_items` (create + update-on-change) и в портале `edit_price`.
- **Тренд**: `_price_trend` в aggregator — медиана по дням, change_pct, direction (up/down/flat), нужно ≥2 дат. Проброшен в `ServiceComparison.price_trend` (только в /compare) + отдельный `GET /api/services/{id}/history`.
- **Фронт**: `PriceTrendBlock` в `ComparisonView` — SVG-спарклайн + «цена выросла/снизилась на N%» (красный/зелёный/серый). Скрыт, если истории <2 точек.
- 3 теста (дедуп истории, тренд-эндпоинт). **NB:** в текущем демо история односессионная → тренд не виден (честно); накапливается при повторных скрейпах. Опция для демо — синтетический бэкфилл истории (не делаю без явного запроса).
Осталось в Спринте-3: pgvector+онтология (нужен Postgres+эмбеддинги), ОСМС/ДМС, OCR сканов. Мерж в main только после сдачи.

## Чек-поинт 2026-06-18 (#6) — Спринт-3: OCR сканов/фото (ветка feat/product-evolution)
58 pytest (+1 skip OCR-roundtrip без tesseract локально), tsc чист. Прод на main не тронут.
- **Образ**: в `backend/Dockerfile` apt `tesseract-ocr` + `-rus` + `-kaz` (рус/каз/англ). +~120MB к образу.
- **Зависимости**: `pytesseract`, `Pillow`, `pymupdf` (рендер сканированных PDF без poppler).
- **Модуль** `app/ingestion/ocr.py`: `ocr_available()` (грациозная деградация без tesseract), `image_to_text`, `pdf_to_text_ocr` (PyMuPDF рендер→OCR, до 15 стр, dpi200), авто-выбор языков.
- **Парсер**: вынесен общий `_items_from_text` (дот-лидеры И одиночный пробел + валютные суффиксы); `parse_image` (картинки), `parse_pdf` OCR-фоллбэк если нет текстового слоя; `detect_and_parse` маршрутит .png/.jpg/... + сигнатуры JPEG/PNG → формат "scan". Все пути приёма (upload/batch/портал) получили OCR автоматически.
- **Фронт**: `accept` файл-инпутов (+картинки) в /admin и /clinic/[token].
- Тесты: `_items_from_text` (дот-лидеры/пробелы/шапка), маршрут image→scan, OCR-roundtrip (skip без tesseract — пройдёт в образе).
Осталось в Спринте-3: pgvector+онтология, ОСМС/ДМС. Мерж в main после сдачи.

## Чек-поинт 2026-06-18 (#7) — фича «корзина-рецепт» (идея Дмитрия; ветка feat/product-evolution)
Пользователь скидывает направление врача (текст/фото/скан) → система распознаёт анализы и говорит, где сдать выгодно/в одной клинике. Composит всё ядро: OCR→нормализатор→агрегатор→город. 63 pytest, tsc+build чисты. Прод на main не тронут.
- **Backend** `routers/basket.py`: `extract_service_names` (строки направления, срез нумерации/буллетов), `_recommend` (две стратегии: mixed=минимум по каждой услуге по разным клиникам; single=одна клиника на максимум услуг, тай-брейк по цене), `POST /api/basket/recommend` (text/names+city), `POST /api/basket/recommend-file` (фото/скан/PDF→OCR→`_extract_text_any`). Read-only `Normalizer.match` (fuzzy без записи/LLM), порог 0.6.
- **Frontend** `/recipe`: textarea+город+загрузка фото; результат — «минимум по разным клиникам» + «в одной клинике» (покрытие N/M, чего нет) + список распознанных услуг со ссылками + нераспознанные. Ссылка «По рецепту» в шапке.
- 5 тестов `test_basket.py` (text/names/file/coverage-tiebreak/422).
**Killer-сценарий**: превращает «листай цены» в «реши мою задачу». Демонстрируется даже на текущих данных (в отличие от трендов).

## Чек-поинт 2026-06-18 (#8) — Спринт-3: онтология + ОСМС-покрытие (ветка feat/product-evolution)
69 pytest, tsc+next build чисты. Прод на main не тронут.
- **Онтология** `app/ingestion/ontology.py`: курируемая карта по базовому ключу (`_okey` сводит варианты «в моче»/«повторный приём» к базе) → {code, group, osms} для 31 услуги; группы (Гематология/Биохимия/Гормоны/Иммунология/Консультации/УЗИ/Функц./Лучевая). Считается на чтении, схему БД не трогаем. Флаг ОСМС — справочный ориентир (не юр.заключение).
- **API**: `ServiceComparison.ontology` (в /compare) + `GET /api/ontology` (группы + код/группа/осмс по услугам).
- **Фронт**: в заголовке услуги — чип группы + бейдж «входит в ОСМС»/«вне ОСМС» (зелёный/серый, с тултипом-дисклеймером).
- 6 тестов `test_ontology.py` (база, наследование вариантами, ЭхоКГ≠ЭКГ, осмс-флаги, unknown→None, группы).
**Спринт-3 практически закрыт.** Остался только чистый pgvector-семантик — он требует Postgres + эмбеддинг-провайдера (инфра-решение, не код); онтология здесь — структурный фундамент под него. ОСМС/ДМС: покрытие ОСМС сделано (курируемое); ДМС упирается в данные конкретных страховых.
Мерж в main только после сдачи 26–28.06.

## Чек-поинт 2026-06-18 (#9) — ГОДНЫЙ ПРОДУКТ: миграции + Postgres-готовность (ветка feat/product-evolution)
Директива Дмитрия «делай годный продукт, не смотри на хакатон» → убираю инженерный долг (ручные ALTER, схема через create_all).
- **Alembic**: `alembic.ini` + `alembic/env.py` (URL из settings, render_as_batch для SQLite, compare_type) + начальная миграция `3a507c7fa04a` (autogenerate, все 9 таблиц + индексы вкл. access_token).
- **`app/migrate.py`**: устойчивое применение — свежая БД→upgrade head; уже-под-alembic→upgrade; ЛЕГАСИ (create_all без версии)→create_all недостающих таблиц + ALTER clinics.access_token + stamp head. Проверено на SQLite и Postgres (temp-контейнер на 5546).
- **entrypoint.sh**: `python -m app.migrate` вместо create_all; **main.py**: убран стартовый `init_db()` (схемой владеют миграции — единый источник правды; ушёл и deprecated on_event-warning).
- requirements: `alembic==1.14.0`. seed/load_real_data сами зовут init_db (dev-инструменты, ок).
- 2 теста `test_migrate.py` (свежая/легаси через subprocess) → 71 pytest.
**Дальше для продукта**: переключить прод-рантайм на Postgres (миграция данных SQLite→PG), pgvector-семантика поверх (теперь инфра готова), auth на admin/portal/review. Прод (main) пока НЕ деплоил — большое изменение, деплой/мерж под контролем.

## Чек-поинт 2026-06-18 (#10) — БЕЗОПАСНОСТЬ: авторизация админ-зоны (ветка feat/product-evolution)
Закрыты открытые admin/review/export/ingest-write/portal-issue эндпоинты. 76 pytest, tsc+next build чисты. Прод на main не тронут.
- **Passwordless токен** (по правилу «без ввода паролей»): `app/auth.py` (`require_admin`, cookie `mt_admin` httpOnly/samesite-lax/secure-по-настройке, либо `Authorization: Bearer`), `routers/auth.py` (login/logout/me). `ADMIN_TOKEN` пусто → fail-closed (503), не открыто. `COOKIE_SECURE` для HTTPS.
- **Защита**: review/export — на уровне include_router; ingest (кроме preview)/portal-issue/feedback-list/leads-list/clinics-POST — поштучно `dependencies=[Depends(require_admin)]`. Публичные: поиск/сравнение/онтология/история/чат/корзина/preview/жалоба-POST/лид-POST/портал-по-токену.
- **Фронт**: `components/AdminGate.tsx` (проверка `me`, magic-link `?key=` с зачисткой URL, ввод ключа, «Выйти»); `app/admin/layout.tsx` оборачивает /admin и /admin/review (контент монтируется только после авторизации).
- **Тесты**: conftest — автообход admin для прежних тестов + маркер `real_admin`; `test_auth.py` (5: 401 без токена, публичные открыты, Bearer/cookie-логин, неверный токен, logout). 76 pytest.
- `.env.example`: `ADMIN_TOKEN` (ген `secrets.token_urlsafe(32)`) + `COOKIE_SECURE`. API.md/CHANGELOG обновлены.
**Дальше**: Postgres как прод-рантайм (миграция данных), pgvector-семантика, rate-limit на публичные POST (жалоба/лид/чат). Прод/мерж — под контролем Дмитрия.

## Чек-поинт 2026-06-18 (#11) — БЕЗОПАСНОСТЬ: rate-limit (ветка feat/product-evolution)
Анти-абуз публичных POST и анти-брутфорс логина. 79 pytest, прод на main не тронут.
- **`app/ratelimit.py`**: in-memory скользящее окно per-IP (threading.Lock, периодическая чистка), `client_ip` (X-Forwarded-For/CF-Connecting-IP/peer — за CF/Next-прокси), фабрика-зависимость `rate_limit(name, limit, window)`, реестр `LIMITERS`. `settings.rate_limit_enabled`.
- **Лимиты**: feedback/price-report 15/мин, leads 10/мин, chat 20/мин, basket 15/мин (+file 10), ingest/preview 20/мин, **auth/login 10/мин** (анти-брутфорс). 429 + Retry-After.
- **Тесты**: conftest по умолчанию выключает (чтобы не мешать), `test_ratelimit.py` (юнит скользящего окна, 429 после лимита, выключение). 79 pytest.
- `.env.example` RATE_LIMIT_ENABLED, API.md/CHANGELOG.
**Гоча скрипта**: автопатч импортов сломал многострочный `from ..auth import (` в auth.py — поправил вручную. **Осталось по безопасности**: Redis для rate-limit на мультиворкер, security-headers (CSP/HSTS) — обычно на уровне Caddy/CF. Дальше для продукта: Postgres-рантайм, pgvector.

## Чек-поинт 2026-06-18 (#12) — ГОДНЫЙ ПРОДУКТ: Postgres как прод-рантайм (ветка feat/product-evolution)
80 pytest, прод на main не тронут.
- **db.py**: для не-sqlite движок с `pool_pre_ping=True`, `pool_size=5`, `max_overflow=5`, `pool_recycle=1800` (скромный пул для маленького VPS); sqlite-ветка без изменений.
- **docker-compose.prod.yml**: новый сервис `medtech-db` (postgres:16-alpine, healthcheck, volume `medtech_pgdata`); backend `DATABASE_URL` → postgres, `depends_on: condition: service_healthy`; добавлены env `ADMIN_TOKEN`/`COOKIE_SECURE`(true)/`RATE_LIMIT_ENABLED`. Схему накатывает entrypoint (migrate).
- **`copy_to_pg.py`**: разовый перенос SQLite→PG в FK-безопасном порядке + сброс PG-sequence (иначе дубль ключа на следующем INSERT). Проверено end-to-end на временном PG (5547): данные+access_token перенесены, новый insert ок. CI-тест `test_copy.py` (sqlite→sqlite).
- README/CHANGELOG: прод-Postgres + cutover + прод-env.
**КУТОВЕР НА ПРОДЕ (когда мержим)**: 1) поднять medtech-db, 2) `app.migrate` накатит схему в PG, 3) `python copy_to_pg.py sqlite:////data/medtech.db <pg_url>` из бэкенд-контейнера со старым SQLite-volume, 4) переключить DATABASE_URL. Прод сейчас НЕ трогаю. Дальше: pgvector-семантика (теперь PG есть), Redis для rate-limit.

## Чек-поинт 2026-06-18 (#13) — ГОДНЫЙ ПРОДУКТ: pgvector-семантика (ветка feat/product-evolution)
Главный «ров»: нормализация понимает СМЫСЛ, а не буквы. 83 pytest, tsc+next build чисты. Прод на main не тронут.
- **`app/ingestion/semantic.py`**: эмбеддинги `fastembed` (модель `paraphrase-multilingual-MiniLM-L12-v2`, 384-dim, ONNX без torch; нормализуем → косинус=dot). Двойное хранилище: **Postgres+pgvector** (`service_embeddings`, поиск `embedding <=> q`) ИЛИ **in-process numpy** (SQLite/dev, кэш по сигнатуре каталога). `available()` → грациозная деградация (нет fastembed/модели или `semantic_enabled=False` → нормализатор остаётся на fuzzy+LLM).
- **Интеграция**: тир семантики в `normalize()` (после fuzzy, ДО LLM; гарды вариантов моча/повторный применяются) + `Normalizer.match` (корзина-рецепт) + `preview` (метод "semantic" в /normalizer). Порог `semantic_threshold=0.72`.
- **Инфра**: миграция `b2f1a9c4d7e8` (PG-only: `CREATE EXTENSION vector` + `service_embeddings vector(384)`); образ Postgres → `pgvector/pgvector:pg16` (prod+dev); Dockerfile **предзагружает модель** в слой (иначе первый запрос ~30с); entrypoint best-effort `semantic.reindex` на старте; админ `POST /api/semantic/reindex` + публичный `GET /api/semantic/match`.
- **Проверено**: pgvector end-to-end на temp-контейнере (`<=>`): «кровь на сахар»→Глюкоза 0.85, «ультразвук почек»→УЗИ почек 0.74, «сердечный врач»→Приём кардиолога 0.95. 3 теста `test_semantic.py` (gated моделью, in-process). conftest по умолчанию выключает семантику (не грузим модель).
- **Гочи**: fastembed multilingual-e5-small НЕ поддержан → взял paraphrase-multilingual-MiniLM; косинусы сжаты (медтекст 0.5–0.95) → семантика как РЕРАНК в неоднозначной зоне (fuzzy<порога), а не абсолютный порог; новые услуги от live-ingest попадут в pgvector только после reindex (in-process авто-ребилд по сигнатуре).
**Спринты 1–3 + продакшен-хардненинг ЗАВЕРШЕНЫ на ветке.** Осталось по желанию: Redis для rate-limit (мультиворкер), реиндекс семантики после ingest, ДМС-данные. Мерж/деплой прод — по слову Дмитрия (cutover SQLite→PG + ADMIN_TOKEN + pgvector-образ).

## Чек-поинт 2026-06-26 (#14) — MedArchive под капотом MedPrice (ветка feat/product-evolution)
Директива: **сдаём MedPrice, но платформа должна уметь MedArchive** (обработка готового архива прайсов партнёров на ОФИЦИАЛЬНОМ справочнике). Организаторы выложили в `docs/` на `origin/main` 2 ТЗ + архив 8 клиник + `Справочник услуг.xlsx` (1286 услуг, колонки `ID·Специальность·Code·Name_ru·TarificatrCode`, синонимов нет). MedArchive добавлен ПАРАЛЛЕЛЬНЫМ движком — single-price путь MedPrice не тронут. **89 pytest зелёные** (+6 MedArchive), прод на main не тронут.
- **Экстрактор `ingestion/archive_extractor.py`** (`ArchiveItem{name,code,price_resident,price_nonresident,price_original}`): DOCX с **принятием tracked changes** (lxml: вырезает `<w:del>`, раскрывает `<w:ins>`), XLSX/XLS (pandas+xlrd; **автодетект строки-заголовка**, **многострочная шапка** складывается вертикально, колонка ценовая если price-хинт ИЛИ резидент/нерезидент-маркер), PDF (extract_tables → иначе **реконструкция строк по координатам слов**, склейка разорванных числовых токенов). Проверен на всех 8: 17143 позиции, 7758 с кодом. Гочи: код в прайсах с кириллической буквой (`В02`→`B02`, `norm_code` транслитерует); `'Код услуги'` содержит «услуг» → code-first классификация чтобы не утёк в name; резидент/нерезидент путались («иностранцев» есть и в РК-колонке) → сильные маркеры + nonres проверяется первым; `parse_price('10.002')`→10002 (3 цифры после разделителя = тысячи); строка-данные с хинтом «анализ» ошибочно поглощалась как продолжение шапки → продолжение шапки = есть хинт И НЕТ разбираемых цен.
- **Загрузчик `ingestion/refcatalog.py`**: `Справочник услуг.xlsx` → ServiceCatalog с `tarificator_code`+`specialty`, идемпотентно (1281 услуга, 1204 с кодом). Категория витрины выводится из специальности.
- **Нормализатор**: `Normalizer.match_archive(raw, code)` — **READ-ONLY** (справочник фиксирован): code-first (точный TarificatrCode → conf=1.0) → fuzzy; ниже порога → (None, conf), позиция уходит в unmatched с `service_id=NULL`, БЕЗ создания услуг/синонимов (иначе индекс раздувался до 17k → O(N²), и пачкался официальный справочник). `code_index` в `_reload`.
- **Модель (аддитивно, nullable — прод не ломается)**: Price.`price_resident`/`price_nonresident`/`service_code_source`/`tarificator_code`; ServiceCatalog.`tarificator_code`(index)/`specialty`; IngestionRun.`file_name`/`raw_content`. `migrate.py._ensure_additive_columns()` — ALTER ADD COLUMN по месту (без новых Alembic-ревизий).
- **Приём `ingestion/archive_service.py`** (`ingest_archive`): валидации ТЗ (цена>0, нерезидент≥резидент, имя не пустое, **аномалия >50%** к прошлой версии), дедуп в документе (matched→по service_id, unmatched→по сырому имени), версионирование через `record_price_history`.
- **CLI `python -m app.archive_ingest <dir|zip> --catalog ... [--semantic-pass] --report docs/quality-report.md`**: миграция→справочник→обход (партнёр=Clinic по имени файла, справочник+ТЗ исключаются)→приём→**отчёт о качестве**. Семантика в bulk ОТКЛЮЧЕНА (O(N×каталог), душит CPU) — это фишка live-демо одиночных запросов.
- **Семантический 2-й проход `ingestion/semantic_backfill.py`** (`--semantic-pass`): unmatched — это в основном НАСТОЯЩИЕ услуги с иной формулировкой (в справочнике нет синонимов). Батчевый дизайн: эмбеддинги справочника и уникальных сырых имён считаются ОДИН раз, сопоставление векторным умножением матриц (не per-item!). Поднимает % автонормализации легитимно.
- **API-контракт MedArchive `routers/partners.py`**: `/api/partners`, `/api/partners/{id}/services` (с резидент/нерезидент), `/api/services/{id}/partners`, `/api/unmatched` (очередь), POST `/api/match` (ручное сопоставление+синоним), `/api/archive/quality` (метрики дашборда). OpenAPI в `/docs`.
- **Метрика**: 1-й проход (код+fuzzy) ≈49% на сыром архиве (строгий порог 0.78, синонимов в справочнике нет, много шума в текстовых PDF); семантический проход поднимает. Отчёт — `docs/quality-report.md`. Цель ТЗ ≥70% — добиваем семантикой + чисткой шума.
- **Среда**: tesseract на сервере НЕТ (OCR graceful — текстовый слой PDF есть). Dev-фикстуры архива в `.archive_samples/` (в git НЕ коммитим). Чекпоинт возобновления: `backend/app/ingestion/MEDARCHIVE_CHECKPOINT.md`.

## Чек-поинт 2026-06-26 (#15) — Кейс1 MedPrice доведён до 100% ТЗ (ветка feat/product-evolution)
Директива Дмитрия: **ТЗ должно быть выполнено на 100%** (дополнения сверху — можно). Прочитаны оба ТЗ (`.archive_samples/ТЗ_Кейс1_MedPrice.docx`, `ТЗ_Кейс2_MedArchive.docx`); §2.1 (источники парсинга), что прислал Дмитрий, — из Кейс1. Кейс2 MedArchive был закрыт ранее. Аудит кода против Кейс1 (3 параллельных агента: модель §2.2 / парсер §3.1+§4 / UI §3.3-3.4) выявил дыры — закрыты. Построчный чек-лист: `docs/TZ_CHECKLIST_MEDPRICE.md`. Тесты 89→**111 зелёных**.
- **robots.txt (ТЗ §8, было ПОЛНОСТЬЮ отсутствует)**: `ingestion/robots.py` — единый шлюз `polite_get`, через который идут ВСЕ сетевые GET парсера. Protego (Scrapy, Google-спек wildcards `*`/`$`) с graceful-fallback на stdlib; stdlib молча НЕ обрабатывает `/appointments/*`, `/*results/` — а их юзают doq.kz/kdlolymp.kz. Кэш robots per-host (TTL), crawl-delay пер-хост throttle, 4xx/нет файла → allow-all. 9 тестов (офлайн через `seed_robots`). Маршрутизированы scrape_url/fetch_contact/103kz/lab_platform/scrape_dynamic; RobotsDisallowed → 403.
- **Модель §2.2 (было 6 полей нет, 3 неверный тип)**: Clinic.working_hours/website/rating/online_booking; Price.parsed_at/is_active/duration_days/price_original/currency_original. category→ENUM 4 значения через `ingestion/category.to_enum` (лаборатория/приём врача/диагностика/процедура). currency USD→KZT через `service.to_kzt` (курс `usd_kzt_rate`, оригинал сохраняется). Всё аддитивно nullable, `migrate._ADDITIVE_COLUMNS` (прод/MedArchive не ломаются).
- **Парсер §3.1**: DOCX в основном канале (`file_parser.parse_docx` → reuse archive_extractor с tracked-changes); raw-слой для web_scrape (`scrape_url_raw` → `IngestionRun.raw_content`); ошибки автосбора → `IngestionRun(status=error)` в scheduler (раньше только в report). KDL-адаптер `web_scraper._kdl` (kdl.kz/kdlolymp.kz, ~219 анализов/филиал, парсит срок выполнения).
- **Нефункц. §4**: фильтр свежести 30 дней в выдаче (`_build_comparison`, не выдаём stale как актуальное) + `scheduler.mark_stale_inactive`; retention raw ≥90 дней (`purge_expired_raw`); cron `0 */6 * * *`; отказоустойчивость per-source try/except.
- **UI/API §3.3**: `/api/suggest` автодополнение; фильтры min+max цена/рейтинг/онлайн-запись; сортировки updated + distance (haversine+geolocation); offer обогащён working_hours/source_url/website/rating/duration_days; `/api/clinics/{id}/profile` + фронт `app/clinics/[id]`. Фронт собран (tsc clean, next build ok) — агент. Готово ✅ Все 7 пунктов.
- **§3.4 опционально**: карта (Яндекс) ✅, история цен ✅; подписка/маршрут/таблица — НЕ делал (в ТЗ помечены «опционально»).
- **Реальные данные §6**: `app/seed_real.py` — живой парсинг KDL-Olymp (robots-compliant) + реальные файлы клиник из `.archive_samples` (cap 4 файла × 120 поз., семантика off в bulk). Источники РК, разные города. Метрики наполнения — `docs/quality-report-medprice.md` (генерится сидом).
- **Среда-гочи**: invitro/doq/2gis — React-SPA (статикой цен нет); olymp.kz таймаутит, helix.kz→.ru, medel/mck robots 404. С этого сервера статикой надёжно берётся KDL-Olymp; остальное — через готовые адаптеры по доступности/Playwright. КОММИТ: после прогона seed_real (метрики) — ещё НЕ закоммичено.

## Чек-поинт 2026-06-26 (#16) — полный охват источников: doq API + invitro статика + 103.kz харвестер
Запрос Дмитрия: «подключи Playwright и сними invitro/doq, нужен полный охват клиник». Решение через разведку (не в лоб Playwright): invitro — СТАТИКА на `/analizes/` (~2126 цен, адаптер `_invitro` уже работал, нужен был лишь URL); doq — открытый REST API `api.doq.kz/api/v1/` (528 клиник × 12 городов). Команда из 3 агентов (doq-коннектор / invitro→103-харвестер / аудит источников). Playwright+chromium поставлены и работают (`--no-sandbox`) — оставлены как fallback для SPA (INVIVO/Helix/Emirmed).
- **`ingestion/doq_connector.py`**: цена прячется в `GET /doctors-meta/?city=&service=&clinic=` → {min_price,max_price}; `fetch_cities/fetch_clinics/fetch_prices/fetch_all`, robots через polite_get, 5 офлайн-тестов. city.id числовой (slug даёт 400).
- **invitro**: статика `/analizes/`, класс `analyzes-item__total--price`; подключён в seed через EXTRA_WEB (адаптер уже был). Орфан `invitro_scraper.py` (запасной city-парсер, 3 теста) оставлен, не подключён.
- **`ingestion/o103_harvester.py`**: 103.kz `{slug}.103.kz/pricing/` → `web_scraper._103kz` + `fetch_103kz_card` (гео/город/телефон из JSON-LD). `discover_slugs` (sitemap-personals.xml.gz ≈9248 поддоменов / городские листинги), `harvest`, `harvest_known` (gemotest/invitro/kdlolymp/rahat/olimp/aqmed/smart-med). 5 офлайн-тестов.
- **Сид расширен** (`seed_real.py`: seed_doq + seed_103 + invitro): **30 источников, 26 клиник, 1162 цены, 491 услуга, 8 городов** (вкл. все 4 приоритетных ТЗ: Алматы/Астана/Шымкент/Актобе). Отчёт `docs/quality-report-medprice.md`, охват в `docs/TZ_CHECKLIST_MEDPRICE.md §2.1`. Тесты **124 зелёных**.
- **Гочи среды**: doq crawl-delay 1с/вызов → каждая услуга = 1 API-запрос, объём в сиде ограничен (4 города × 4 клиники × 12 услуг). olymp.kz timeout, bioline.kz 403 WAF, synevo/aksai/dina DNS-нет. Аудит дал быстрые победы на будущее: KazMedClinic `/ceny` (996 цен статикой), SAPA, Gemotest через 103.

## Чек-поинт 2026-06-26 (#17) — все города РК + планировщик под коннекторы
Запрос Дмитрия: «подключи KazMedClinic и все города Казахстана» + «доделай планировщик».
- **Все города**: `seed_real` масштабирован — doq на все 12 городов (`DOQ_CITIES=[]`→fetch_cities), 103.kz `discover_slugs` по 12 городам + harvest_known, KazMedClinic `/ceny` (823 поз. через generic-парсер, кастом не нужен). crawl-delay в сиде 0.5с (doq=узкое место, каждая услуга=1 API-вызов). Итог сида: **42 клиники, 73 источника, 1908 цен, 600 услуг, 14 городов** (Алматы/Астана/Караганда/Шымкент/Кокшетау/Актобе/Тараз/Усть-Каменогорск/Павлодар/Семей + KDL-локации).
- **Планировщик (§4) под коннекторы**: cron `0 */6 * * *`. web_scrape (KDL/invitro/KazMedClinic/**103.kz** — у 103 источник хранит `/pricing/`-URL, адаптер `_103kz` по суффиксу) обновляются `scrape_url`. doq — раньше generic `fetch_api` не умел его API; теперь источник хранит машинный ref `doq://{city_id}/{clinic_id}`, `scheduler` парсит (`doq_connector.parse_ref`) и зовёт `doq_connector.refresh(clinic_id, city_id)`. 3 теста маршрутизации (`test_scheduler_routing.py`) + отказоустойчивость. Тесты **127 зелёных**.
- **Гоча**: doq-источники получают `doq://`-ref только при (ре)сиде; старые human-URL doq-записи в текущей БД роутинг не подхватит до пересева (Бv gitignore, эфемерна).
