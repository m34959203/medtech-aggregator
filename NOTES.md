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

## Чек-поинт 2026-06-26 (#18) — справочник всех 90 городов РК подключён в сид + фильтр
Возобновление прерванной (связь оборвалась) работы: файл-сирота `app/data/kz_cities.py` (канон-справочник 90 городов РК со статусами/областями, `all_cities/names/slugify`) был написан, но нигде не использовался и не закоммичен. Подключён:
- **`canonical_city(raw)`** в kz_cities: имя/slug/алиас источника (`almaty`, `uk`→Усть-Каменогорск, `nur-sultan`→Астана) → каноническое русское имя; неизвестный город не теряем (title); None/пусто→None.
- **Сид (`seed_real`)**: `_clinic()` нормализует город через canonical_city (иначе фильтр двоился `almaty`/«Алматы»); круговая раскладка локальных файлов берётся из справочника.
- **Фильтр (`aggregator`)**: `/api/cities` = все 90 городов ∪ города с данными (города с данными первыми) — полный охват §3.3/§7; новый `/api/cities/coverage` — каждый из 90 + `has_data`/`clinics` (без прайсов = «зарегистрирован, данных нет»).
- **Тесты**: `tests/test_kz_cities.py` (+5). Прогон: **132 зелёных, 1 skip** (было 127). Коммит `17b029d`.
- Фронт `/cities` пока НЕ потребляет (дропдауна городов нет) — отдельная фича. `docs/quality-report-medprice.md` остался с прежними несохранёнными правками от прошлого прогона сида (вне scope, не коммитил).

## Чек-поинт 2026-06-26 (#19) — охват малых городов: рычаг найден, потолок честно зафиксирован
Запрос Дмитрия: «подтяни данные для всех городов» → «реши проблему малых городов».
- **Справочник 90 городов подключён в сид и фильтр** (см. #18): `kz_cities.canonical_city` нормализует город в `_clinic` (almaty/uk/«Алматы»→1 запись); `/api/cities` = все 90 ∪ города с данными; `/api/cities/coverage` = город+has_data. O103_CITIES расширен с 12 до всех 90.
- **Решение малых городов — филиалы сетей** (`seed_103_chains` + `o103.discover_chain_branches`/`CHAIN_SLUG_RE`): общий sitemap 103.kz (~9248) отсортирован по мегаполисам (скан «с головы» бесполезен), поэтому из него отбираются ФИЛИАЛЫ сетей (~406: olimp 182/invitro 139/gemotest 61/helix/kdl/genom), город каждого — из его карточки, кэп на город ради широты. Харвестер разбит на дешёвые шаги: `fetch_pricing` (1 запрос: город+позиции) → решение → `enrich_geo` (2-й запрос только для взятых). `harvest_one`/`harvest` сохранены. Тесты `test_o103_global.py` (+4), всего **135 зелёных**. Коммит `4bbfe70`.
- **Живой полный сид** (PID-фон, SQLite `backend/medtech.db`, ~25 мин из-за crawl-delay 103.kz): **53 клиники, 2356 цен, 633 услуги, 18 городов** (было 14). Отчёт перегенерён `docs/quality-report-medprice.md` (18:27, НЕ коммитил — генерится сидом, БД эфемерна).
- **ПОТОЛОК (честно)**: chains-проход дал «33 филиала / 13 городов», но в основном пересёкся с крупными. Причина в ИСТОЧНИКЕ: малые города на 103.kz почти не отдают цены статикой (карточки `/pricing/` React → `fetch_pricing`=None → отсев); doq API = только 12 городов. Потолок статически-снимаемого ≈ 18–20 городов — не дыра в коде, а отсутствие открытых статичных прайсов у малых городов.
- **Артефакты гигиены**: `Байконуре` (предложн. падеж), `Шаян`/`Еркинкала` — это KDL-локации-филиалы, не отдельные города; `canonical_city` не свёл (нет в 90 / падеж). TODO: фильтр KDL-локаций + падежная нормализация.
- **Рычаги дальше (по слову Дмитрия)**: (1) Playwright (уже стоит) — рендер JS-страниц малых городов = снять цены, которых нет в статике; (2) сетевой прайс+справочник филиалов сети → применить цену сети к каждому городу-филиалу. Платформа уже ЗНАЕТ все 90 (coverage), малые = «зарегистрирован, данных нет».

## Чек-поинт 2026-06-26 (#20) — ПРОД-ДЕПЛОЙ: cutover SQLite→Postgres+pgvector ВЫПОЛНЕН
По слову Дмитрия задеплоен merge `d401a8f` на прод `medtech.technokod.kz` (из `/home/ubuntu/medtech-platform`, проект medtech-platform). Чек-лист cutover (NOTES:189) исполнен:
1. **Бэкап** прод-SQLite → `backups/medtech-prebackup-cutover.db` (294КБ).
2. `git pull` прод-клона ff `b1914b9→d401a8f`; в `.env` добавлены `POSTGRES_PASSWORD`/`ADMIN_TOKEN` (secrets) + `COOKIE_SECURE=true`/`RATE_LIMIT_ENABLED=true` (YANDEX/ALEM сохранены).
3. `docker compose build`; **конфликт имени `medtech-db`** — мусорный контейнер от dev-клона (`project=medtech-aggregator`, образ postgres:16-alpine, status=created, пустой) удалён (изоляция проектов!). Поднят настоящий `pgvector/pgvector:pg16`, healthy.
4. **Перенос данных без простоя**: одноразовый `docker compose run --rm` — копия легаси-SQLite мигрирована (case-3 legacy: +access_token +additive-колонки, stamp head), схема PG поднята (alembic upgrade head + pgvector-расширение), `copy_to_pg.py` → **clinics 75, service_catalog 34, ingestion_runs 479, prices 801 = 1389 строк**. Живой SQLite-backend всё это время обслуживал сайт.
5. `up -d` — стек переключён на PG; entrypoint: migrate (no-op) + **семантика проиндексировала 34 услуги (pgvector)** + uvicorn. cloudflared уже в `medtech_net`.
- **ГОЧА (важная, решена)**: `/api/search` вернул 0 — перенесённые цены имели `is_active=NULL`, а фильтр свежести `aggregator.py:172 bool(getattr(price,"is_active",True))` трактует NULL как «не активна» (колоночный `default=True` НЕ применяется к ALTER-добавленным колонкам на старых строках). Бэкфилл в PG: `UPDATE prices SET is_active=true WHERE is_active IS NULL; parsed_at=now() WHERE NULL` (801+801). TODO в код: трактовать NULL как активную (`is_active IS NOT FALSE`) — иначе повторится при следующей миграции легаси.
- **Верификация end-to-end**: публичный `/health` 200, `/` 200, `/api/cities` (новый охват: города с данными + все 90 РК), `/api/search` через CF — Билирубин 28 предлож/мин 600₸, Витамин D 12, админ-логин по токену 200, `/api/ingest/stats` без токена 401. Контейнеры healthy. Прод НА Postgres+pgvector.
- **Хвосты**: POSTGRES_PASSWORD печатался в логе cutover (PG только во внутр. docker-сети, без хост-порта — низкий риск, при желании ротация); `is_active`-фикс в код; Redis для rate-limit (мультиворкер) при росте нагрузки.

## Чек-поинт 2026-06-26 (#21) — редеплой прода с is_active-фиксом
Фикс `is_active` (NULL=активна, commit 157b35c) влит в `main` (merge `5427b57`) и задеплоен на прод. Прод-клон pull main → ребилд ТОЛЬКО backend-образа (фронт не менялся) → `up -d medtech-backend` (PG/данные не тронуты, migrate no-op, семантика 34). **Доказательство фикса вживую**: `UPDATE prices SET is_active=NULL` всем 28 ценам услуги №8 → `/api/compare/8` вернул 28 предложений (до фикса было бы 0) → восстановлено `true`. Публично `medtech.technokod.kz`: /health 200, /api/search отдаёт данные. TODO из #20 закрыт.

## Чек-поинт 2026-06-26 (#22) — прод долит данными: 7 → 18 городов
Живой `seed_real` прогнан против ПРОД-PG (внутри medtech-backend, бэкап `backups/medtech-pg-before-seed.sql`). Прод: было 75кл/801ц/7гор → стало **103 клиники / 3098 цен / 18 городов**. Семантика переиндексирована (613 услуг). Существующие города целы (Алматы/Астана/Караганда…), добавлены Петропавловск/Павлодар/Костанай/Усть-Каменогорск/Тараз/Талдыкорган/Кызылорда. Публично проверено (поиск по Костанаю отдаёт цены). Прим.: 4 «города» — артефакты KDL-филиалов (Еркинкала/Байконуре/Абай/Шаян), реальных городов ≈14; чистка KDL-локаций — TODO из #19.

## Чек-поинт 2026-06-26 (#23) — /api/cities без пустых городов
По запросу: фильтр `/api/cities` отдавал все 90 городов РК ∪ с данными (пустые засоряли дропдаун). Теперь — ТОЛЬКО города с ценами (join Price), на проде = 18. Полный охват (90 + has_data) остался в `/api/cities/coverage`. Merge `3efc624` в main, прод-backend пересобран. Прим.: 4 из 18 — KDL-артефакты (Еркинкала/Байконуре/Абай/Шаян), они НЕ пустые (есть цены), но это локации-филиалы, не города → отдельная чистка (TODO #19).

## Чек-поинт 2026-06-26 (#24) — почищены KDL-артефакты: реальные 14 городов
KDL branch-страницы (abay/baykonur/erkinkala/shayan) давали «город» из h1 в предложном падеже (Байконуре/Еркинкала/Шаян/Абае) — суб-городские точки забора, не города. `KDL_BRANCHES=[]` в сиде (KDL-Olymp идёт через 103.kz-сети с городом из карточки). Прод-данные: удалены 4 клиники (id 76-79) + 286 цен транзакционно (FK-порядок: prices до ingestion_runs). Прод: 103кл/3098ц/18гор → **99 клиник / 2812 цен / 14 ГОРОДОВ** (все реальные: Актау/Актобе/Алматы/Астана/Караганда/Костанай/Кызылорда/Павлодар/Петропавловск/Семей/Талдыкорган/Тараз/Усть-Каменогорск/Шымкент). Merge `807f5f8`, backend пересобран, публично проверено. TODO #19 (чистка KDL-локаций) закрыт.

## Чек-поинт 2026-06-26 (#25) — кнопка «адрес в WhatsApp» в балуне карты
`ClinicMap.tsx`: в балуне клиники добавлена WA-кнопка (wa.me/?text=...) с названием, адресом и маршрутной ссылкой Яндекс.Карт `rtext=~lat,lng&rtt=auto` (от текущего местоположения к точке) — переслать адрес в WhatsApp для навигатора. tsc чист, фронт-образ пересобран, задеплоено (merge f7beccb). Видно на /service/[id] (где есть офферы с гео).

## Чек-поинт 2026-06-26 (#26) — WhatsApp-туннель (Baileys) задеплоен
Перенёс паттерн из technokod/wa-gateway: микросервис `wa-gateway/` (Baileys + PG auth-store + express), антибан (serial-очередь, humanize-presence, дневной лимит 100, отправка только тем, кто написал первым), 405-фикс (version fallback при недоступности fetchLatestBaileysVersion), fire-and-forget inbound webhook. Самодостаточен: `ensureSchema()` создаёт whatsapp_sessions/whatsapp_messages. Backend `routers/wa.py` — admin-проксь `/api/wa/{status,connect,disconnect,limits,send}` + приём `/api/wa/inbound` по X-Webhook-Secret; настройки WA_GATEWAY_URL/WA_API_SECRET/WA_INBOUND_WEBHOOK_SECRET (пусто→503). compose: сервис `medtech-wa` (порт 127.0.0.1:3200, та же PG). Задеплоено (merge 7570162): туннель /health ok, таблицы созданы, проксь 401 без токена / disconnected с токеном, limits ок. **Привязка (вручную, нужен телефон)**: `POST /api/wa/connect` → polling `GET /api/wa/status` до qrCode (data-URL) → скан в WhatsApp→Связанные устройства → connected. Inbound-бизнес-логика (лид/автоответ) — TODO в wa.py.

## Чек-поинт 2026-06-26 (#27) — admin-страница WhatsApp (QR) + скрытие админки
- **`/admin/whatsapp`**: привязка WA — кнопка «Подключить» → poll `GET /api/wa/status` (2.5с) → показ QR (data-URL) с инструкцией → connected (телефон + лимиты антибана); «Отключить»/«Выйти и стереть». WA-хелперы в `lib/api.ts` (waStatus/waConnect/waDisconnect/waLogout/waLimits) + backend `/api/wa/logout` проксь.
- **Скрытие админки**: убрана публичная ссылка «Приём данных» (/admin) из шапки `app/layout.tsx` — доступ ТОЛЬКО по magic-link `/admin?key=...` (AdminGate уже был). Навигация админ-разделов (Приём/Очередь/WhatsApp) перенесена в `app/admin/layout.tsx` ВНУТРЬ AdminGate — обычный пользователь её не видит.
- Задеплоено (merge debc7b6): фронт+бэк пересобраны, главная без admin-ссылки (0 вхождений, проверено мимо CF-кэша), /admin/whatsapp 200, проксь wa/status под токеном ок. Привязка: открыть `/admin?key=ADMIN_TOKEN` → вкладка WhatsApp → Подключить → скан QR.

## Чек-поинт 2026-06-26 (#28) — ИИ-разбор очереди ревью
`POST /api/review/ai-resolve` (admin): для каждой спорной цены (conf<0.78) LLM выбирает действие — confirm/reassign/new/junk — ВЫБИРАЯ услугу из top-K кандидатов справочника (rapidfuzz) + текущая привязка (retrieval-injection, [[feedback-ai-interaction-layer]]: справочник=истина, ИИ не выдумывает). apply применяет решения с confidence≥min_confidence; без LLM — graceful skip (не зацикл.). +action `new` в review_price (создаёт услугу из сырого имени). Фронт: панель «ИИ-разбор очереди» в /admin/review — цикл по батчам ×25 с прогрессом и защитой от зацикливания (стоп если очередь не убывает). +3 теста (140 pytest). Прод-проверка (живой AlemLLM): HE4/T-Uptake→confirm, NSE→reassign на канон, ЛДГ→верная ЛДГ; применено 5, очередь 529→524. Полный прогон ~524 — за оператором через кнопку (не льём 500+ мед-привязок на боевом без надзора). Merge 96be666. TODO: батчить N позиций в один LLM-вызов (сейчас 1/вызов, ~25с на 25).

## Чек-поинт 2026-06-26 (#29) — нормализатор по боевому отчёту + OCR-рецепт + ИИ-разбор safe-mode
Боевой отчёт по `/normalizer` (направление с шумом/панелями) → 5 задач закрыты. Параллельно: фронт-агент (UI+перенос в admin), AI-пасс очереди (фон).
- **TASK1 gate** `ingestion/line_gate.py`: отсев заголовков (вкл. одиночные «Направление/Результаты»), ФИО/дата/инструкции по `ключ:значение` и эвристикам; шум не матчится и не создаёт услуг.
- **TASK2 порог отказа** `reject_floor=0.6`: ниже — `status=unmatched` (нет ложных 100%/принудительной привязки). `sanitize_synonyms` — ТОЧЕЧНОЕ правило (синоним = имя другой услуги). **ГОЧА: агрессивная эвристика «короткая аббревиатура» снесла на проде 717 легит-синонимов и ухудшила матчинг → убрана; даже точечное правило сносит ~645 (сырые имена клиник = имена др. услуг) и ломает Ферритин → НА ПРОДЕ САНИТАЙЗ НЕ ГОНЯЕМ, оставляем синонимы как есть.**
- **TASK3 `_prefer_blood`**: дефолт кровь/сыворотка (Ферритин→Ферритин, не «в моче»). **TASK4 `ingestion/panels.py`**: словарная декомпозиция (липидо/коагулограмма, билирубин); generic-split НЕ делаем (сломал бы ОАК). `analyze()` оркестрация. **TASK5** фронт: `/admin/normalizer` (перенесён из публичной зоны), статусы matched/unmatched/noise, разбор панелей, строгий режим, **загрузка фото/скана** → `/api/ingest/preview-file`. Golden 18/18, **158 pytest**.
- **OCR фото/скан рецептов**: OCR (tesseract rus/kaz/eng) в проде уже работал — чинилась цепочка «текст→услуги»: рецепт (`basket`) теперь через `analyze()` (фильтр шума ФИО/дата/заголовок, декомпозиция панелей). Прод-смоук: «Направление»+«Пациент:» → noise, услуги распознаны; Ферритин✓/Глюкоза✓/Липидограмма→4✓/HbA1c✓.
- **ИИ-разбор очереди — боевой пасс под наблюдением**: confirm 258 (надёжны)+junk 2 (верны), но **reassign 116 ненадёжен (~40% ошибок: ИИ путает по общему слову — «арт.давление»→глазная тонометрия, «Токсокароз IgG»→«Трихомониаз IgG»)**. Прод откатан из бэкапа `backups/medtech-pg-before-aireview.sql` (3× restore по ходу отладки санитайза). `ai-resolve` получил `auto_actions=["confirm","junk"]` по умолчанию — reassign/new больше НЕ авто-применяются, только предложения оператору.
- **Остаточная гоча**: единичная пред-загрязнённость синонимов (напр. «АЛТ»→«Са+») остаётся в данных — лечить через ручную очередь, не авто-сweep. Merge `b45e6a8`, прод обновлён.

## Чек-поинт 2026-06-26 (#30) — §2.2: id клиник/услуг → uuid + source_url (на проде)
ТЗ §2.2 «структура данных»: сверка 13/15 → доведено до 15/15. Расхождения закрыты:
- **id клиник/услуг → uuid**: `Uuid` PK у `clinics`/`service_catalog` + все FK (prices/sources/leads/price_reports/price_history/service_embeddings); прочие PK (prices.id и т.п.) остались int. Тип `Uuid` портативен (PG native / SQLite CHAR32).
- **+`Price.source_url`** — URL источника записи, заполняется при ingest из `Source.url_or_endpoint`, отдаётся в offer (фолбэк — сайт клиники).
- Сквозь: Pydantic-схемы (uuid у id клиник/услуг), путь-параметры роутеров `uuid.UUID`, **ai-resolve через порядковые номера кандидатов** (LLM не повторяет uuid), upload-batch по uuid-префиксу файла, фронт `number→string` (агент), тесты под uuid (агент). 158 pytest.
- **Прод-cutover (data)**: бэкап `backups/medtech-pg-before-uuid.sql` → temp-БД `medtech_old` (int) → drop schema medtech → `create_all` (uuid) → **`remap_uuid.py`** (int→uuid с ремапом всех FK, отбрасывает None под NOT NULL-default): перенесено **6509 строк** (99 клиник/613 услуг/2812 цен/...) → `service_embeddings` (uuid) создана, reindex 613. Гочи: (1) старый бэкап без `source_url` → ALTER medtech_old; (2) NOT NULL working_hours при None → remap дропает None; (3) `service_embeddings` не модель → `migrate._ensure_pgvector_embeddings()` создаёт идемпотентно при create_all-деплое; (4) ИЗОЛЯЦИЯ: `docker compose` строго из `/home/ubuntu/medtech-platform` (после git checkout cwd уходит в dev-клон!). Прод проверен: service_id/clinic_id=uuid, source_url, /api/search/compare/cities, /health 200. Merge `26aec88`.

## Чек-поинт 2026-06-27 (#31) — §2.2 «в точь точь»: строгие enum + плоская запись
ТЗ §2.2 закрыт дословно (типы/имена один-в-один), а не только по смыслу:
- **`category` → `Category(str, Enum)`** {лаборатория/приём врача/диагностика/процедура} (`ingestion/category.py`); `to_enum()` возвращает `Category`; поля `CollectedRecord.category` и `ServiceComparison.category_enum` типизированы.
- **`currency` → `Currency(str, Enum)`** {KZT, USD} (`ingestion/currency.py`); `normalize()` приводит шум («Тенге»/«₸»/«$») к канону на приёме; `to_kzt` нормализует валюту; `PriceOut/PriceOffer.currency: Currency`. Хранимая цена всегда KZT, оригинал в `currency_original`.
- **`CollectedRecord`** + **`GET /api/records`** — плоская §2.2-запись (клиника×услуга×цена) ровно 16 полей ТЗ с именами/типами (`price_kzt: Decimal`, `service_name_norm` из привязки к справочнику); фильтры city/service_id/active_only + пагинация. `PriceOffer` тоже получил дословные `service_name_norm`/`price_kzt`.
- Строгость enum валидируется Pydantic-схемой (EUR/«Прочее» → ValidationError). **162 pytest** (+4). Прод пересобран (backend), проверено: `/api/records` отдаёт `category:"лаборатория"`/`currency:"KZT"`/`price_kzt:"1750.00"`, `/api/categories`=4 enum, `/api/compare|search` без регресса. Merge `4b22274` (+ подтянут docs `e9c2b28`).

## Чек-поинт 2026-06-27 (#32) — починка привязок нормализатором по очереди ревью
Жалоба: «Коагулограмма №1 (протромбин, МНО)» привязана к «Гемостаз для беременных…» с **conf=1.0** (вне обычной очереди conf<0.78). Разбор вскрыл корневую причину и дал инструмент:
- **БАГ uuid-миграции (#30)**: `semantic.match` возвращал `int(uuid)` → `db.get(ServiceCatalog, …)` падал на PG («cannot cast numeric to uuid»). **Семантический тир нормализации был отключён со вчера.** Починено: возвращает uuid; +`semantic.match_topk(k)`.
- **Усиленный пул кандидатов** `_ai_candidates`: объединение fuzzy(canonical) ∪ fuzzy(синонимы) ∪ семантика ∪ текущая. Раньше fuzzy-only терял верный канон; теперь «Протромбин, МНО (протромбиновое время, PT, INR)» попадает в пул.
- **verify-проход** `_ai_verify_same`: независимый строгий yes/no (биоматериал/метод/аналит/панель) — срезает 40%-ошибку reassign. Встроен в авто-применение `ai-resolve` И в новый recheck.
- **`POST /api/review/recheck`** (admin): детект ОШИБОЧНЫХ привязок с высокой уверенностью по низкому косинусу raw↔canonical (эмбеддинг-скан, дёшево), переразбор + reassign ТОЛЬКО после verify. Параметры scan_limit/offset/suspect_floor/apply/min_confidence/max_llm. Идемпотентно, ложный подозреваемый просто подтверждается.
- **Прод**: бэкап `backups/medtech-pg-before-recheck.sql`. Скан выявил **581 подозрительную привязку** (≈20% от conf≥0.78 — следствие сломанной семантики + прежних reassign #28-29). Контролируемый apply worst-50: применено 4 (точные дубли-каноны: HBsAg→HBsAg, Инсулин→Инсулин), verify отклонил 21 (включая мусор →Глюкоза и неточные УЗИ простаты→малого таза) — **precision-режим, верно**. Эталонный id=3098 починен точечно (reassign→«Протромбин, МНО…», verify=True).
- **Осталось оператору**: остальные ~577 подозрительных — циклом `recheck` (offset-батчами) под надзором; часть требует обогащения справочника (нет точного канона → verify абстейнит). UI-кнопка в /admin/review — TODO. **165 pytest.** Merge `811071d`.

## Чек-поинт 2026-06-27 (#33) — §3.1 хвост: cron на проде + кнопки автосбора + фикс секвенций
Закрыт реально пункт «запуск вручную через интерфейс ИЛИ по расписанию»:
- **ЕЩЁ один латентный баг uuid-cutover (#30)**: serial-секвенции int-PK таблиц (sources/ingestion_runs/prices/price_reports/price_history) после bulk-переноса остались на 1 → ЛЮБОЙ новый INSERT падал `duplicate key` (приём/scrape/cron были сломаны, просто никто не вставлял с момента cutover). Разовый `setval=max(id)` на проде + durable `migrate._resync_sequences()` (идемпотентно на старте, PG-only).
- **Cron**: `scripts/cron-ingest.sh` (flock, лог `backups/cron-ingest.log`) → `docker exec medtech-backend python -m app.scheduler`; crontab `0 */6 * * *` установлен. End-to-end проверено: прогон `OK`, источники собраны (299–300 поз.), purge/stale отработали.
- **Кнопки в /admin**: карточка «Автосбор с сайта» — приём по URL (`/api/ingest/scrape`, robots.txt + опц. динам.рендер) + «Запустить плановый сбор» (`/api/ingest/run-scheduled`). `api.ts`: scrapeSite()/runScheduled(). Фронт пересобран+задеплоен (карточка в бандле).
- Чек-лист §3.1/§4 поправлен (раньше cron был заявлен ✅, но фактически не установлен — теперь установлен реально).
- **§3.1 итог: 6/6 по-настоящему.** Merge `2e52451`. backend+frontend пересобраны, smoke: scrape 401 без токена, run-scheduled принят, /health ok.

## Чек-поинт 2026-06-27 (#34) — §3.2 аудит+чистка справочника (данные прода)
Запрос: «добавь CBC в синонимы ОАК, проверь справочник». Аудит вскрыл системное загрязнение синонимов (наследие старого слабого матчинга). Бэкап: `backups/medtech-pg-before-syn-cleanup.sql`. Сделано (правки ДАННЫХ, не кода — Normalizer перестраивает индекс на запрос, изменения уже живые):
- **+CBC** (+ Clinical/complete blood count) в синонимы ОАК.
- **#1 −98 кросс-канонических синонимов** (синоним = точный канон ДРУГОЙ услуги: ОАК←«Витамин D»/«Лактат», «Глюкоза»←«Резус» и т.п.).
- **#2 ОАК де-загрязнён**: из ~220 синонимов оставлено 54 реально-ОАК, удалено 166 чужих (тяжёлые металлы, витамины, гормоны, СОЭ, кал…) — ОАК был свалкой и «магнитом» ложных привязок.
- **#3 +EN-аббревиатуры** в 7 услуг (Ferritin/ALT/TSH/Cholesterol/Creatinine/Glucose/Urinalysis…).
- **+2 отсутствующие услуги**: «АСТ (аспартатаминотрансфераза)» и «ПСА общий» (распространённые анализы, которых НЕ было → их цены биндились мимо: AST→АФП, PSA→SCCA). Реиндекс эмбеддингов (615). + убрана ПСА-загрязнённость из «УЗИ щитовидки»/«ОАМ».
- **Итог**: справочник 613→**615**; покрытие 12 типовых EN-аббревиатур **6 пробелов → 0**; ТЗ-пример (ОАК/CBC/Клинический/Общий → одна услуга) сходится по рецептному пути `match_one`. Очередь unmatched: 2.
- **Остаток (долг данных)**: системное token-level загрязнение синонимов в длинном хвосте (напр. «Кальций»→«Витамин D в моче») — лечится отдельным систематическим synonym-sanity проходом (по аналогии с recheck, но для синонимов). Не код, а данные. `Normalizer.match()` (простой метод) в проде не вызывается — рецепт идёт через guard'ованный `match_one`.

## Чек-поинт 2026-06-27 (#35) — Gemini-LLM, compare-таблица, фикс поиска аббревиатур
- **LLM → Gemini 2.5-flash через Vertex AI** (SA zhezu-052026, us-central1). Провайдер `gemini` в `llm.py` (Vertex-токен из SA, кэш+refresh). Гочи: 2.0-flash недоступен (404)→2.5; thinking жрёт 1000-1400 ток.→ОТКЛЮЧЕН `thinking_budget=0` (иначе 55% skip). Фолбэк AlemLLM сохранён.
- **Перепрогон recheck на Gemini** (весь свод, бэкап `medtech-pg-before-gemini-sweep.sql`): 1144 предложения, confirm 211/reassign 598/new 324/junk 11; **применено 30** (verify-gated), 364 отклонено. AlemLLM ранее применил 107 — Gemini их подтверждает (confirm) и НЕ форсит сомнительные reassign. **Главное: 324 «new»** = сырьё без услуги в справочнике (Трансферритин, Золото сыворотка, АТ-МАГ, Хеликобактер-сумм…) — кандидаты на услуги (§3.2 «справочник формирует команда»). Авто-reassign-резерв в основном исчерпан; дальше — расширение справочника.
- **§3.4 таблица сравнения клиник** (доп-пункт ТЗ): `POST /api/compare-clinics` (услуги×клиники, 🏆 лучшая цена/услуга, итог/экономия/дистанция/рейтинг/свежесть/источник + рекомендации дешевле/ближе/баланс, «не найдено» вместо 0) + страница `/compare` (выбор услуг/город/2-4 клиники/гео/только-со-всеми, sticky шапка+столбец, мобильные карточки). Merge — задеплоено, /compare 200.
- **Фикс ложных совпадений аббревиатур** (поиск/подсказки/рецепт): корень — наивный подстрочный матч + системное загрязнение синонимов. `_relevance` = токен-матчинг (канон>синонима), порог 0.7, ранжирование. Данные: +4 тиреоидные услуги (Т4/Т3 своб/общий — их НЕ было, имена висели загрязнением на Билирубине/УЗИ/ОАМ), −24 тироид-загрязнения, +аббревиатуры (TTG/TSH→ТТГ, vit d→Витамин D). Прод-смоук: TTG→ТТГ, T4→Т4 свободный, vit d→Витамин D (было IgA/билирубин/0). Бэкап `medtech-pg-before-thyroid-fix.sql`.
- **Остаток**: системное token-level загрязнение синонимов в длинном хвосте лечится ранжированием (канон-вес), но физически остаётся в данных — для идеала нужен систематический synonym-sanity проход. 619 услуг.

## Чек-поинт 2026-06-27 (#36) — рычаг №1: добор услуг + чистка синонимов (Качество данных)
Бэкап: `backups/medtech-pg-before-lever1.sql`. Только ДАННЫЕ (живёт сразу, Normalizer читает свежее; деплой не нужен).
- **Добор услуг из 324 «new»-кандидатов Gemini** (181 уник.): пере-суждение Gemini против ОБНОВЛЁННОГО справочника (`_ai_decide`+verify) — самокорректирующе: action=new→создать+реассайн; найденный матч→привязать только после verify; verify-провал→создать как новую. Результат: **+163 услуги (619→782), 197 цен реассайнено** (new 110 / reassign 53 / confirm 13). Реиндекс эмбеддингов (782).
- **Чистка синонимов**: применено БЕЗОПАСНОЕ правило — синоним = ТОЧНОЕ имя ДРУГОЙ услуги (exact cross-canonical) → **−248 загрязнений** (после добора их стало больше видно: «Глюкоза»←«Группа крови», «РПГА Enterocolitica»←«РПГА pseudotuberculosis», «Пахиметрия»←«Аудиотон»). **ОТКЛОНЕНО**: fuzzy≥92 (687 — ловит легит «Приём X»←«Консультация X», ловушка NOTES #29) и авто-извлечение аббревиатур (376 — тащит generic IgG и компоненты панелей FIB-4→ОАК/АЛТ/АСТ = новое загрязнение).
- Итог: каталог **782 услуги** (+26%), 761 с ценой; ключевые кейсы целы (TTG/T4/vit d/ОАК/Глюкоза/Трансферритин). **Остаток (длинный хвост)**: новые услуги созданы с пустыми синонимами → их аббревиатуры (ГГТ→Гамма-глутамилтранспептидаза) пока не матчатся; безопасного авто-правила нет (риск>польза), лечится точечно/полу-ручным дозаведением синонимов. Бьёт по «Качеству данных» (вес 25%).

## Чек-поинт 2026-06-27 (#37) — Кейс 2 (MedArchive) доведён до 100% (строго аддитивно, Кейс 1 не тронут)
Контекст: Кейс 1 (MedPrice) = цель 100% (закрыт по коду ранее); Кейс 2 (MedArchive) добиваем «для полноты системы». Сверка по коду вскрыла 4 реальных недобора Кейс 2 — закрыты так, чтобы НЕ затрагивать Кейс 1 (его путь `ingest_items` делят web/api-сбор + тесты `test_case1`).
- **Оригиналы файлов не сохранялись (§2.1/§5)** → новый `ingestion/storage.py` (`store_original`/`read_original`), хранилище `/data/uploads` (постоянный том `medtech_data`, переживает ребилд). `ingest_archive(content=...)` пишет оригинал под `run_id` и проставляет `file_path`. CLI `archive_ingest` тоже передаёт `content`.
- **`PriceDocument` не выделен (§3.2)** → `IngestionRun` дополнен полями сущности: `clinic_id`(=partner_id), `effective_date`, `file_path` (+ уже было file_name/format=file_format/status=parse_status/message=parse_log/raw_content). Аддитивные nullable-колонки через `_ADDITIVE_COLUMNS` (идемпотентный ALTER), на проде применены entrypoint-миграцией (`+ingestion_runs.clinic_id/effective_date/file_path`).
- **UI-загрузка легче архивной по §4.4** → НЕ трогал `/upload-batch` (его тестит Кейс 1). Вместо этого новый эндпоинт **`POST /api/ingest/archive`** на архивном пайплайне (`archive_extractor`+`ingest_archive`): резидент/нерезидент, нерезидент≥резидент, аномалия >50%, code-first, сохранение оригиналов; партнёр из префикса/формы/имени файла (авто-создание). + **`POST /api/ingest/archive/{run_id}/reprocess`** — повторная обработка из сохранённого оригинала (демонстрирует смысл §2.1).
- **Тихий лимит `[:200]`** → новый эндпоинт обрабатывает до 1000 и возвращает `truncated: bool` (честный сигнал об обрезке).
- **Фронт**: чекбокс «Режим MedArchive (Кейс 2)» в карточке приёма → вызывает `uploadArchive`; показывает 💾-сохранение оригинала, аномалии, баннер обрезки. `tsc --noEmit` чисто.
- **Тесты**: +2 в `test_medarchive` (сохранение оригинала+резидент/нерезидент+reprocess; 404 reprocess без оригинала). Полный прогон на чистом окружении: **168 passed, 1 failed** (`test_parser` — предсуществующий PIL/окружение, не связан). `test_case1`/`test_pipeline` (Кейс 1) зелёные. ⚠️ внутри ПРОД-контейнера `test_auth`/`test_chat` падают из-за env (`GEMINI_API_KEY`/`ADMIN_TOKEN`) — не код.
- **Деплой**: `docker compose -f docker-compose.prod.yml up -d --build` (бэкенд+фронт пересобраны, миграция прошла). Смоук на проде: колонки есть, `/data/uploads` пишется/читается, `/archive` и `/archive/{id}/reprocess` → 401 (зарегистрированы), `/admin` → 200. Бэкап схемы: `backups/ingestion_runs-before-pricedoc.sql`.
- **NB**: изменения в рабочем дереве НЕ закоммичены (прод собран из working tree). Помимо Кейс 2 в сессии закрыт долг синонимов 28 новым услугам (+43 синонима из их же канон-имён, `backups/medtech-pg-before-syn-newsvc.sql`).

## Чек-поинт 2026-06-27 (#38) — фиксы боевого прогона Cowork (#1-3,7 + 2 находки прогона)
Отчёт Cowork: `docs/handoffs/2026-06-27-2.md`. Разобрано ПО КОДУ, не на веру.
- **#2 (нормализация, judge-visible, бьёт 25%+25%)**: корень — обратная связь синонимов (`normalize` добавлял сырое имя синонимом даже при ошибочном матче → «Кал на скрытую кровь»/«Копрограмма» висели exact-синонимами 1.0 на ОАК/ЭКГ, «Коронавирус» на IgA). Фикс: **биоматериал-гард** (стул/мокрота ≠ кровяная услуга) в `match()/normalize()/semantic/LLM-таргет`, при ЛЮБОЙ уверенности (\b чтобы не задеть «Калий»/«Кальций»; `копрограмм/копролог`, не `копро*` — иначе «копропорфирины»). +юнит-тест. Данные прода: **−91 загрязнённый синоним** (стул/мокрота/корона, доменный гард не тронул легит-стул-услуги типа «Дисбактериоз»), цены пере-привязаны (бэкап `medtech-pg-before-biomat-fix*.sql`). **Остаток**: не-биоматериальное загрязнение (Калий→ОАК-в-моче, мусор-сервис «ОАК в моче») — лечится recheck-проходом, долг.
- **#3**: `/api/archive/quality` считал по всему каталогу-агрегатору → auto_rate 100% при documents=0 (вводит жюри в заблуждение). Сделал архив-специфичной + **позиционной** (matched/needs_review на `IngestionRun`, до дедупа — иначе занижение 17% vs реальных 62%). `goal_70_met` только при docs>0. +`catalog_positions` контекст.
- **#1**: `/service/<числовой_id>` → 500. Невалидный uuid даёт 422 (не 404); страница теперь трактует 404 И 422 как `notFound()`.
- **#7**: кнопка «Маршрут» (Яндекс.Карты) в оффере при гео. Сорт «по дате обновления» уже был в дропдауне (Cowork не заметил).
- **+находки прогона** (не из отчёта): **потолок цены 100M KZT** в `parse_price` — OCR/склейка давали ≥10^10 → переполнение NUMERIC(12,2) и падение приёма. 
- **Боевой прогон архива хакатона на проде** (10 файлов, ВСЕ форматы PDF/скан/DOCX/XLSX/XLS, история 2024-2026): documents=10, positions=16760, **auto_rate 62.2%** (честно <70 цели; остаток в очереди ревью §4.3), резидент/нерезидент **3878 цен** (#4 закрыт), оригиналы в `/data/uploads`, история 7k+. Скрипты-чистки вне репо (gitignore). Кейс 1 не затронут (35→169 passed).

## Чек-поинт 2026-06-27 (#39) — auto_rate ≥70% + хвост синонимов (Phase 2)
**auto_rate (Кейс 2): 62.2% → 72.0%, goal_70_met=true.** Рычаг — загрузка ОФИЦИАЛЬНОГО «Справочник услуг.xlsx» (1281 строка, 1204 с кодом тарификатора): `load_official_catalog` мёржит по имени (добавляет код существующей услуге, +1191 новых), архивный прогон делает code-first exact-матч по этим кодам. Каталог 783→1983. Кейс 1 не пострадал (услуги без цен в поиск не лезут; ОАК/Глюкоза/CBC/ТТГ/Ферритин 200). Бэкап `medtech-pg-before-official-catalog.sql`.

**Хвост синонимов** (фид-бэк-петля `_add_synonym`: услуги-магниты впитали сотни чужих имён). Durable matcher (commit 23a51d3):
- `_fuzzy_guarded` — лучший кандидат БЕЗ конфликта биоматериала + **tie-break** (при равном token_set предпочесть совпадение биоматериала). `_biomat_conflict` расширен на urine: обычный аналит ≠ мочевой вариант. → «Глюкоза»→«Глюкоза (кровь)», «Глюкоза в моче»→мочевая, Креатинин/Холестерин корректны.
- **корень**: weak-fuzzy (step 3) больше НЕ добавляет синоним (иначе слабый матч = вечный exact-хит 1.0, растит магниты).
Данные прода: сняты магниты «ОАК в моче» (143), «Алюминий, ногти» (135), «Витамин D» (−41), +972 cross-canonical (self-consistent проход против чистых канонов). Калий/Натрий→«Электролиты (Na/K/Cl)» (приемлемо), Магний верно.
**Остаток (честно)**: «Кальций общий»→«Витамин D» через combo-синоним — token-правила не отделяют легит-комбо от мусора; trace-element/antibody хвост лечится LLM-verified recheck-проходом (`POST /api/review/recheck`), долг. Ключевые поиски 10/10. Скрипты-чистки вне репо (gitignore); данные-операции в бэкапах `backups/medtech-pg-*-{official-catalog,tail-cleanup}.sql`.

## Чек-поинт 2026-06-27 (#40) — OCR в чате + чат на Gemini
- **OCR в чате** (`POST /api/chat/vision`, commit 29b1a4f): пациент шлёт фото/скан направления в чат-виджет → OCR (tesseract rus/kaz/eng, переиспользован `_extract_text_any`/`extract_service_names` из `/recipe`) → нормализация к справочнику → ответ тем же retrieval-injection, что текстовый чат. Фронт: кнопка-камера в ChatWidget (`capture=environment`), чипы «Распознано». Поле `recognized` в ChatResponse. Деградация: нет OCR/ключа → детерминированная сводка. Фикс enum-репра валюты «Currency.KZT»→«KZT». OCR теперь в 3 точках: архив-сканы, `/recipe`, чат.
- **Чат на Gemini** (commit da60a8c): чат использовал свой httpx-вызов только к alem/groq → на проде без их ключей всегда фолбэк. Переключён на единую `llm.chat` (Gemini 2.5-flash/Vertex, как нормализатор/recheck), `_has_chat_key→llm.has_key()`. Прод-проверка: `llm=True`, разговорный ответ, grounded по витрине. Весь ИИ-слой (нормализация-арбитраж + recheck + чат текст/фото) теперь на одном `llm`-модуле (Vertex).
- Тесты +2 (vision); 171 passed. Доки актуализированы (README/API/architecture/ТЗ_vs/TZ_CHECKLIST).

## Чек-поинт 2026-06-27 (#41) — фиксы боевого прогона + WhatsApp-координаты + логотипы
- **Отправить координаты в WhatsApp** (`ClinicMap.tsx`, commit 1bb025e→f0c9f88): кнопка в балуне метки карты → **React-модалка** ввода номера → `wa.me/<номер>` с адресом, координатами (lat,lng), точкой на карте и маршрутом. Мост балун(Yandex HTML)→React через `__medtechWaOpen(id)` + `waDataRef`. Esc/клик-фон/Enter, валидация ≥10 цифр. Сначала была inline-форма в балуне, по просьбе переведена на модалку (Яндекс перехватывает фокус в попапе).
- **Баг заголовков** (commit 94f0f06): «Направление на анализы:» ловилось в услугу «Анализ пота» (слово «анализ» включало service-hint и срывало отсев). `line_gate`: директива «Направление на/для …» → шум ДО has_service; `extract_service_names` теперь гейтит строки (покрывает и чат-OCR, который не гейтил) — заголовки/нумерация/ФИО/дата отсеиваются.
- **«Глюкоза»≠моча в чате**: биоматериал-гард распространён на `_rank_services` (чат) — обычный аналит даёт кровяной канон (плановый дефолт), мочевой вариант отсекается. (match/normalize/match_one уже так делали.)
- **Логотипы в футере**: организатор (`organizer-logo.gif`, прозрачный фон → `filter:brightness(0)` чёрным, виден на белом) + спонсор (`sponsor-logo.png`, nomad.kz), подписи «Организатор/Спонсор хакатона».
- Тесты +2 (отсев заголовка; «Глюкоза»→кровь), 173 passed. Доки: README/ТЗ_vs/TZ_CHECKLIST.
- **Долг**: дубли-каноны «Глюкоза (в крови)»/«Глюкоза (кровь)» (наследие слияния офиц.справочника) — оба показываются в чате; почистить отдельным проходом.

## Чек-поинт 2026-06-27 (#42) — конечные действия чата (CTA) + единый парсер списков
- **Обрыв воронки устранён** (боевой отчёт «Трение»): чат доводил до цены+«Позвонить», но не было перехода к услуге/клинике. Теперь в каждом ответе чата:
  - чип распознанной услуги → `/service/{service_id}` (полное сравнение+карта+запись);
  - на карточке оффера основная кнопка «**Сравнить и записаться**» → `/service/{service_id}?clinic={clinic_id}` (подсветка клиники), вторичные «Маршрут» (Яндекс по lat/lng) и «Позвонить»;
  - итоговый CTA «🛒 **Собрать корзину**» → `/recipe?services=<id1,id2>` (префилл точными service_id).
- **API**: `ChatOffer` теперь несёт `service_id`/`clinic_id`/`lat`/`lng` (uuid+координаты) — раньше фронту нечем было линковать. `/service/[id]` принимает `?clinic=` → `ComparisonView.highlightClinicId` (стартовый `activeClinicId` = подсветка+скролл оффера). `/recipe` читает `?services=` (Suspense+useSearchParams) и зовёт `recommendBasket({service_ids})`.
- **Единый парсер списков** (`[BUG]` несогласованность экстракторов): `extract_service_names` + новый `_split_list_items` дробят перечисление в одной строке по запятой/`+`/`/` («ОАК, ОАМ»→2, «АЛТ/АСТ»→2). Один парсер на чат-OCR и `/recipe` (оба зовут `extract_service_names`) — расхождение «чат дробит, рецепт нет» закрыто. `/api/basket/recommend` принимает `service_ids` (точный префилл без повторного фаззи-матча; строка URL → `uuid.UUID`, иначе SQLite/PG не глотают str).
- Тесты +3 (inline-список, префилл по service_ids, CTA-поля оффера), 21 passed в чистом env-контейнере. tsc фронта чисто.
- **Деплой**: код в рабочем дереве; нужен ребилд `medtech-backend`+`medtech-frontend` (docker-compose.prod.yml) — не запускал без отмашки.

## Чек-поинт 2026-06-27 (#43) — дозаполнение рейтинга/часов/сайта клиник с 103.kz
- **Корень**: рейтинг был пуст у ВСЕХ 107 клиник прода (поле `rating` есть в модели и показывается на `/clinics/[id]` и `/compare`, но никогда не заполнялось) — «Рейтинг —» в сравнении.
- **Скрапер** (`web_scraper.fetch_103kz_card`): из того же JSON-LD `LocalBusiness` теперь тянем `url`→website, `openingHoursSpecification`→`working_hours`, `aggregateRating.ratingValue`→`rating`. `_format_opening_hours` схлопывает соседние дни с одинаковым интервалом («Пн–Пт 07:30–15:00, Сб …»); пустая строка при отсутствии данных (поле необязательное).
- **Бэкфилл** `backend/enrich_contacts.py` (dry-run по умолчанию, `--apply` для записи): идемпотентно заполняет ТОЛЬКО пустые поля по `sources(type=web_scrape, *.103.kz)`. Анонимные «Клиника N» без источника не трогаются.
- **Прогон на проде** (preview→apply, как договаривались): 22 клиники с 103.kz-источником → **17 получили рейтинг** (1.0–5.0); сайт/часы у них уже были (идемпотентно пропущены), сбоев фетча 0. Рейтинг прода 0→17/107. Видно на `/compare` и `/clinics/[id]` сразу (SSR из PG, код API не менялся).
- Тесты 179 passed в чистом env-контейнере. tsc фронта без изменений (типы `rating/working_hours/website` уже были).
- **Долг деплоя**: новый `web_scraper.py` пока только в рантайм-контейнере (docker cp); чтобы будущие ingestion-прогоны тоже захватывали рейтинг/часы — ребилд образа `medtech-backend` (общий ребилд из #42).
- **Деплой #42+#43 выполнен**: ребилд+рекрит `medtech-backend`+`medtech-frontend`, проверено публично (health/home 200, рейтинг 17/107, чат отдаёт CTA-поля оффера). Коммиты `1b049bd`+`3674ea3` запушены в `origin/main`.

## Чек-поинт 2026-06-27 (#44) — слияние дублей-канонов «Глюкоза (кровь)» (долг #41)
- **Корень**: официальный `Справочник услуг.xlsx` содержит `Глюкоза (кровь)`+`Глюкоза (кровь) экспресс`, а SPECS (`load_real_data.py`) — `Глюкоза (в крови)`. `load_official_catalog` создавал канон на каждое несовпадающее имя → 3 кровяных канона-дубля в чате/сравнении.
- **Данные** (`backend/merge_glucose.py`, dry-run→`--apply`, бэкап `backups/medtech-pg-before-glucose-merge.sql`): 7 кровяных цен → `Глюкоза (в крови)` (37→44), +6 чистых синонимов (129), 2 пустых дубля удалены. Перенесена `price_history` (8 строк) и подписки (0). **Аномалия**: `Глюкоза (сахар) в моче ВО` за 1 333 002 ₸ (мочевой тест под кровяным дублем + парс-мусор) — удалена из `prices` и `price_history`. Мочевые/`Глюкозотолерантный тест` НЕ тронуты (другой биоматериал/методика).
- **Анти-рецидив** (`refcatalog.py`): `_CANON_ALIASES` — имена справочника, вливаемые в существующий канон вместо создания дубля (`глюкоза (кровь)`/`…экспресс`→`глюкоза (в крови)`): имя оседает синонимом, код подтягивается, `created` не растёт. +тест `test_official_catalog_alias_folds_into_existing_canon`.
- **Фильтр шума синонимов**: пакетные/длинные сырые имена («…Комплекс обследования супружеской пары») в синонимы не кладём (болезнь кросс-загрязнения).
- Тесты 180 passed в чистом env-контейнере. Прод: канонов «глюкоз» 8→6, кровь едина (44 цены), мусор-цена убрана.

## Чек-поинт 2026-06-27 (#45) — достоверность данных: скрытие анонимных клиник + чистка сирот
- **Аудит достоверности (по запросу «все клиники/услуги правдивые»)**: из 10897 цен **6837 (63%) висели на 8 обезличенных «Клиника 1…8»** — это намеренно анонимизированные организаторами файлы Кейса 2 (имена файлов «Клиника N прайс 2026.pdf»), без имени/города/контактов/гео. Прайсы реальные, но клиника не идентифицируема. Остальные 99 клиник — реально спарсены (103.kz/лаб-платформы).
- **Решение Дмитрия**: (1) анонимные — скрыть из публичного агрегатора (оставить в MedArchive/Кейс-2 + админке); (2) услуги-сироты — удалить.
- **`Clinic.is_public`** (новая колонка, alembic `c3d8e1f20a4b`, идемпотентно + авто-скрытие «Клиника N» regex на PG): публичные эндпоинты фильтруют `is_public=True` — `_build_comparison` (⇒ compare+чат+корзина), `_fresh_cheapest_by_clinic` (поиск), `/cities`, `/cities/coverage`, `/records`, `/api/clinics`, guard в `compare-clinics`. `/api/partners` (Кейс-2) и админка НЕ фильтруют. Прод: 8 скрыто, 99 публичных.
- **Чистка сирот** (`backend/prune_orphan_services.py`, dry-run/`--apply`, бэкап `backups/medtech-pg-before-truthful-cleanup.sql`): удалено **428 услуг без единой цены** (каталог 2014→1586, сирот 0). FK price_history/подписки обработаны. Услуги, которые предлагают только анонимы, сохранены (у них есть цены) — просто не видны публично.
- **Парсер проверен в админке вживую** (через API с auth-кукой): preview-нормализация (ОАК/глюкоза/липидограмма-сплит/УЗИ — 100%), живой scrape реальной клиники (282 позиции), контактная карточка 103.kz отдаёт адрес/телефон/гео/сайт/часы. Матрица покрытия: цена — все адаптеры; телефон/адрес/гео/часы/сайт — 103.kz+doq; не-103.kz адаптеры и файл-загрузки дают только цену (контакты — из карточки клиники).
- Тесты **181 passed** в чистом env-контейнере (+тест скрытия анонимов, +фикс migration-теста: regex `~` только на PG). Ребилд бэкенда (миграция в образе), проверено публично: `/api/clinics` 99/0 анонимных.
- **Долг**: Distance-«чекпоинт» на главной/предложениях — backend готов (haversine), нужен персист геолокации на фронте (фича сравнения ниже использует расстояние только на странице услуги).

## Чек-поинт 2026-06-27 (#46) — сравнение одной услуги в 2–4 клиниках (оркестратор)
- **Реализовано** через Workflow-оркестрацию (4 агента: Build×2 параллельно → Integrate → Verify): на странице услуги в каждой карточке клиники чекбокс «Сравнить», мультивыбор 2–4, закреплённая нижняя панель (чипы выбранных + «Очистить» + «Сравнить (N)»), модалка-таблица сравнения.
- **Новые файлы**: `frontend/lib/distance.ts` (`haversineKm`/`formatDistance`); `frontend/components/ServiceComparePanel.tsx` (панель+модалка; строки-метрики Цена/Рейтинг/Расстояние/Онлайн-запись/Адрес/Режим работы/Обновлено; лучшее per-метрика подсвечивается, ties-aware через `leaders()`; расстояние client-side из `coords`+offer.lat/lng).
- **Интеграция** в `ComparisonView.tsx`: `selectedIds`+`toggleSelect` (cap 4), пропсы в `OfferRow`, рендер панели; в `OfferRow` чекбокс с `stopPropagation` (не триггерит выбор-на-карте), кольцо `ring-brand-400` у выбранной. Приоритет колец: isActive > selected > isCheapest.
- **Данные**: всё из существующего `/api/compare/{id}` (`PriceOffer`: price/rating/online_booking/working_hours/address/lat-lng/valid_from). Бэкенд не трогали.
- Verify: `tsc --noEmit` 0 ошибок, `next build` успешно. Прод: ребилд `medtech-frontend`, `/service/[id]` 200, 30 чекбоксов «Сравнить» в DOM.
- **Долг**: distance в таблице = «—» пока пользователь не дал геолокацию (кнопка «Показать расстояние» в строке зовёт `requestGeo`); ручной UI-прогон в браузере не делал (только сборка+SSR-маркеры).

## Чек-поинт 2026-06-27 (#47) — краткое описание услуги рядом с названием
- **Запрос**: при просмотре предложений рядом с названием услуги показывать краткое описание.
- **Данные**: новое поле `ServiceCatalog.description` (alembic `d4a1b2c3e5f6`, idempotent). Сгенерировано батч-скриптом `backend/generate_descriptions.py` (Gemini/Vertex через `llm.json_completion`, батч=25, dry-run/`--apply`, идемпотентно — только пустые, public-first). Прод: **1586/1586 услуг** с описанием, 0 сбоев. Описания короткие, нейтральные, без диагнозов («Глюкоза (в крови)» → «Измерение уровня сахара в крови для оценки углеводного обмена»).
- **API**: `description` добавлен в `ServiceComparison` (страница услуги + поиск) и `ServiceOut`; `_build_comparison` отдаёт `service.description`.
- **Фронт**: показ под названием услуги в шапке `ComparisonView` (страница услуги) и в `ServiceCard` (карточки поиска, `line-clamp-2`). Тип `ServiceComparison.description?`.
- Verify: tsc 0 ошибок, ребилд backend+frontend. Прод: `/api/compare` и `/api/search` отдают description, рендерится в HTML страницы услуги и карточках.

## Чек-поинт 2026-06-27 (#48) — адреса для офферов без адреса
- **Жалоба**: в списках предложений не все услуги с адресами. Аудит: из публичных клиник без адреса ровно **2** — «Invitro — Алматы» (451 цена) и «KazMedClinic — Алматы» (349), но из-за объёма цен они часто в выдаче.
- **Причина**: спарсены не-103.kz адаптерами (`invitro.kz/analizes`, `kazmedclinic.kz/ceny`) — те дают только цену+имя; JSON-LD сайтов адрес/гео не отдаёт (parser `fetch_contact` достал лишь телефоны).
- **Фикс данными** (бэкап `backups/medtech-pg-before-addr-fix.sql`): Invitro — реальный филиал с `invitro.103.kz` (Кунаева 32 + гео 43.2662/76.9492 + Пн–Вс 07:00–18:00); KazMedClinic — с офиц. сайта (мкр. Дархан-2, 29 + часы). Заполнены только пустые поля. Гоча: `docker exec` БЕЗ `-i` не пробрасывает stdin → heredoc-SQL молча не выполняется.
- Прод: публичных клиник без адреса **0**; `/api/compare` офферы все с адресом. Правка только данных — ребилд не нужен.

## Чек-поинт 2026-06-27 (#49) — расстояние-«чекпоинт» на страницах с поиском
- **Запрос**: учитывать расстояние на страницах с поиском (главная + выдача), геопозиция как «чекпоинт».
- **Чекпоинт** `frontend/lib/geolocation.ts`: `loadGeo/saveGeo/clearGeo/requestBrowserGeo` — геопозиция в localStorage (`medtech_geo`), один источник на всё приложение (поставил раз — работает везде).
- **SearchExperience (главная/выдача)**: `GeoControl` «Рядом со мной — учесть расстояние» (запрос геолокации → сохранение чекпоинта → бейдж «Местоположение учтено» + «сбросить»); сорт **«Ближе»** (`sort="distance"`, при выборе без чекпоинта сам просит геолокацию); `user_lat/lng` передаётся в `/api/search`; список услуг сортируется клиентски по расстоянию до ближайшей клиники.
- **ServiceCard**: бейдж «📍 N км» = расстояние до ближайшей клиники с услугой (helper `nearestKm` по офферам, client-side haversine). Показывается только при заданном чекпоинте.
- **ComparisonView (страница услуги)**: подхватывает тот же чекпоинт (`loadGeo` на маунте) и сохраняет (`saveGeo` при запросе гео) — единый чекпоинт между главной/выдачей/услугой.
- Бэкенд не трогали (search/compare уже принимали user_lat/lng + haversine). Verify: tsc 0, next build ок. Прод: на главной кнопка-чекпоинт и сорт «Ближе», `/api/search?sort=distance&user_lat&user_lng` → 200. Гоча: бейдж расстояния — клиентский (нужна геолокация браузера), в SSR-HTML не виден.

## Чек-поинт 2026-06-27 (#50) — удалена страница /compare (мульти-услуга × мульти-клиника)
- **Запрос**: удалить `/compare` — не нужна, функционал работает иначе (сравнение одной услуги в 2–4 клиниках реализовано прямо на странице услуги, #46).
- Удалено: `frontend/app/compare/page.tsx`; ссылка «Сравнение» из шапки (`layout.tsx`); осиротевший `compareClinics()` + импорты `ClinicComparison`/`ClinicCompareRequest` в `api.ts`. Типы `CompareColumn/CompareCell/ClinicComparison` в `types.ts` оставлены (безвредные, без рантайма).
- Бэкенд `/api/compare-clinics` оставлен (не вызывается, вреда нет; убирать = ребилд бэка). Гоча: после удаления страницы `tsc` ругался на устаревшие `.next/types/app/compare/*` — лечится `rm -rf .next/types` + ребилд.
- Прод: `/compare` → 404, главная 200, ссылок на /compare 0. Только фронт-ребилд.

## Чек-поинт 2026-06-27 (#51) — «координаты в WhatsApp»: ПК через наш шлюз, мобайл через wa.me
- **Жалоба**: кнопка «отправить координаты в WhatsApp» открывала `wa.me` (публичный click-to-chat), а не слала через наш шлюз.
- **Решение Дмитрия**: на ПК — слать сразу с нашего номера (обойти гейт «клиент написал первым»); на мобиле — оставить `wa.me` (открывает нативное приложение).
- **Шлюз** (`wa-gateway`): новый флаг `transactional` в `/api/send` — обходит ТОЛЬКО `REQUIRE_CLIENT_INITIATED`, дневной лимит/humanize остаются (анти-бан-подушка).
- **Бэкенд** (`wa.py`): ПУБЛИЧНЫЙ `POST /api/wa/share-location` (без admin) — строит сообщение (название/адрес/координаты/карта/маршрут Яндекс) и шлёт через шлюз с `transactional:true`. Валидация номера ≥10 цифр.
- **Фронт** (`ClinicMap.tsx`): в модалке `send()` определяет мобайл по UA → `wa.me`; иначе POST `shareLocationWA` (`lib/api.ts`), состояния «Отправляем…/Отправлено ✓/ошибка».
- Verify: фронт tsc 0; шлюз TS скомпилировался в Docker; эндпоинт публичный (короткий номер→400, валидный доходит до шлюза). Ребилд wa+backend+frontend.
- **ВАЖНО (операционный долг)**: `whatsapp_sessions` пуста — WA-номер НЕ привязан, поэтому отправка с ПК сейчас вернёт «WhatsApp not connected». Нужно привязать номер по QR в `/admin/whatsapp` (creds хранятся в PG `whatsapp_sessions`, переживают ребилд; auto-connect на старте при наличии creds). Гоча: у `medtech-wa` нет volume для auth — это ОК, т.к. auth в Postgres, не в ФС.

## Чек-поинт 2026-06-27 (#52) — оптимизация /admin (пикер клиник + авто-обновление + WA-статус + вёрстка)
- **Запрос Дмитрия**: удобство (пикер клиник вместо UUID), авто-обновление + состояния, визуальный дизайн.
- **Пикер клиник** `ClinicPicker` — поиск по названию/городу вместо ручного ввода `clinic_id (uuid)`; во всех карточках (автосбор/портал/загрузка). Источник — `/api/partners` (все 107 клиник вкл. обезличенные, грузится 1 раз). +`getPartners()`/`Partner` в api.ts.
- **Авто-обновление**: статистика/журнал/WA-статус рефрешатся раз в 30с + кнопка «Обновить» (со спиннером) и «обновлено N сек назад». Скелетоны вместо «—» при первой загрузке (HealthBanner/StatsGrid/RunsTable).
- **Блок статуса WhatsApp** на дашборде (`waStatus()` — точка/подпись connected/disconnected/qr_ready + телефон, ссылка на `/admin/whatsapp`). Быстрые ссылки: очередь/WhatsApp/нормализатор.
- **Вёрстка**: шапка с RefreshControl, верхний ряд health+WA, числа статов с `toLocaleString`, загрузка — в грид-ряд.
- Бэкенд не трогали (`/api/partners` уже публичный, отдаёт id+name+city). Verify: tsc 0, next build ок (/admin 6.45→8.31 kB), ребилд frontend. Гоча: контент /admin за AdminGate — в SSR-HTML маркеры не видны (рендер клиентом после `?key=`).

## Чек-поинт 2026-06-27 (#53) — панель завершения приёма + конечные действия оператора (Персона D)
- **Жалоба (боевой прогон)**: после «Обработать» только строка-сводка — тупик: непонятно «куда делись позиции», как открыть «на проверку», завершён ли прогон.
- **[BUG критичный найден]**: очередь ревью делала INNER JOIN на справочник → нераспознанные (`service_id IS NULL`) НЕ попадали. Прод: счётчик 6132, а в очереди реально ~5 (с услугой), **6127 нераспознанных без пути к разбору**. Фикс: **OUTER JOIN** + null-обработка в UI («не распознано — назначьте услугу», confirm выкл. без услуги). Теперь очередь=6132, фильтр по прогону отдаёт реальные N.
- **Панель завершения** (`CompletionPanel` в `BatchUploadCard`): статус ✅ + судьба позиций (в каталоге·видны / на проверке·скрыты / аномалии / 💾 оригинал) + CTA на каждый прогон: «Проверить N→» `/admin/review?run={id}`, «Открыть прогон» `/admin/runs/{id}`, «Переобработать» (reprocess).
- **Бэкенд**: `review/queue?run_id=N` (+`total`, outer join); новый `GET /api/ingest/runs/{id}` (метаданные + позиции raw→норм., статус, резидент/нерезидент). api.ts: `getReviewQueue(runId)`, `getRunDetail`, `reprocessRun`.
- **Страница прогона** `/admin/runs/[id]`: статы + таблица позиций + CTA проверки/переобработки. Счётчик «на проверке» → ссылка на ревью; строки журнала кликабельны.
- **Ревью**: читает `?run=` (фильтр + баннер «прогон #N · показать все»).
- **Отложено** (нужно подтверждение/доработка): откат прогона (деструктивно), фильтр аномалий (флаг не хранится на Price). Зафиксировано в `docs/handoffs/2026-06-27-4.md`.
- Verify: tsc 0, next build ок (+маршрут `/admin/runs/[id]`), ребилд backend+frontend; прод: run-detail #1276 = 1012 поз/391 каталог/621 проверка, ревью по прогону total=621, глобальная очередь total=6132 (совпала со счётчиком).

## Чек-поинт 2026-06-27 (#54) — откат прогона + детерминированный фильтр аномалий
- **Фильтр аномалий** + **фикс п.2 (недетерминированность)**: аномалия была «>50% к предыдущей версии» → плясала из-за дублей прогонов (105→4→0). Заменено на **детерминированный флаг** `Price.is_anomaly` (alembic `e5b2c6a9f1d3`) = `nonresident < resident` (валидация позиции, стабильно). Счётчик аномалий в `archive_service` считает по флагу. Бэкфилл прода: **146 аномалий** / 12823 цен.
- **Ревью-фильтр** `?filter=anomaly` (`is_anomaly=True` вместо conf<threshold); карточка ревью показывает бейдж «⚠ аномалия» + рез/нерез цены. Run detail отдаёт `counts.anomalies` + `is_anomaly` в позициях; CTA «Показать N аномалий» в панели завершения и на странице прогона.
- **Откат прогона** `POST /api/ingest/runs/{id}/rollback` (admin, деструктивно): удаляет цены прогона, помечает run `rolled_back`. Кнопка на странице прогона с `window.confirm` → редирект на дашборд. Проверено: 404 на несуществующий, 401 без admin.
- api.ts: `getReviewQueue(runId, filter)`, `rollbackRun`. Тесты 181 passed, ребилд backend+frontend.
- **Долг (аудит 9 пунктов, см. handoff #4)**: п.1 идемпотентность (один файл → 3 дубль-прогона 1274/1275/1276 — НЕ блокируется), п.3 счётчик прогонов смешивает скрап+документы, п.4 нет фильтра журнала, п.5 подписка молчит (WA не привязан), п.6 нет агрегата %нормализации (69%<70%), п.8 ключ в URL/нет аудита оператора, п.9 нет dry-run. Откат теперь позволяет вручную убрать дубли 1274/1275.

## Чек-поинт 2026-06-28 (#55) — управление источниками автосбора + видимость cron
- **Запрос**: нет возможности запуска по расписанию (cron) и выбора списка сайтов для парсинга.
- **Источники (CRUD)**: новые admin-эндпоинты `GET/POST/PATCH/DELETE /api/ingest/sources` (модель `Source` уже была: enabled/schedule/last_run_at). Страница **`/admin/sources`**: список сайтов с тумблером вкл/выкл (= что берёт cron), добавление (пикер клиники+тип+URL), «снять сейчас», удаление (отвязывает прогоны, history цел). Ссылка в шапке дашборда.
- **Расписание (cron)**: уже было — `scripts/cron-ingest.sh` каждые 6ч (`python -m app.scheduler` → run_all_sources по enabled). На странице блок «Автосбор каждые 6 часов · включено N из M · последний прогон» + «Запустить сейчас» (фоновый run-scheduled из #b562874). Смена интервала = правка crontab (ops); выбор сайтов из UI = тумблер enabled.
- **Рефактор**: `ClinicPicker` вынесен в `components/ClinicPicker.tsx` (общий для /admin и /admin/sources).
- Verify: tsc 0, build ок (+маршрут `/admin/sources`), 181 passed, ребилд backend+frontend. Прод: 75 источников (все enabled), PATCH/DELETE/auth проверены.
