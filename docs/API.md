# API — контракт

Base URL: `http://localhost:8000` (локально), прод — `https://medtech.technokod.kz`.
Все прикладные роуты под префиксом `/api`. Интерактивная документация: `/docs` (Swagger), `/redoc`.

## Авторизация (админ-зона)

Админ-роуты защищены passwordless-токеном (`ADMIN_TOKEN`). Токен принимается из
httpOnly-cookie `mt_admin` или заголовка `Authorization: Bearer <token>`. Если
`ADMIN_TOKEN` не задан — админ-роуты закрыты (fail-closed), а не открыты.

- `POST /api/auth/login` `{token}` → ставит cookie (вход). `GET /api/auth/me` → статус. `POST /api/auth/logout`.
- **Только админ:** `/api/ingest/*` (кроме `preview`/`preview-file`), `/api/export/*`, `/api/review/*`, `/api/ingest/stats`, `/api/portal/issue/*`, `POST /api/clinics`, `GET /api/feedback/price-reports`, `GET /api/leads`, `POST /api/match`, `GET /api/subscriptions`.
- **Публичные:** поиск/сравнение/категории/города/услуги/онтология/история/автодополнение, чат, корзина-рецепт, карточка клиники, подписка на цену, агрегатор-партнёры/услуги/очередь, метрики качества архива, `ingest/preview`, `POST` жалобы и лида, портал по токену клиники (`/api/portal/{token}/*`).
- Вход в UI: `/admin?key=<ADMIN_TOKEN>` (magic-link) либо ввод ключа в форме.

## Rate-limit

Публичные POST и логин ограничены по IP (in-memory, скользящее окно): жалоба ~15/мин, лид ~10/мин, чат ~20/мин, корзина ~15/мин, подписка ~10/мин, `auth/login` ~10/мин, `ingest/preview` ~20/мин, `ingest/preview-file` ~10/мин. Превышение → `429` с `Retry-After`. Масштаб — вынести в Redis.

## Приём данных (Кейс 1)

### `POST /api/ingest/upload` — ① загрузка прайса
`multipart/form-data`: `clinic_id` (int), `file` (xlsx/csv/pdf).
```bash
curl -F clinic_id=1 -F file=@pricelist.xlsx localhost:8000/api/ingest/upload
```
→ `IngestionResult`:
```json
{"run_id":8,"clinic_id":1,"channel":"push","format":"xlsx",
 "items_found":7,"matched":7,"needs_review":0,"status":"normalized"}
```

### `POST /api/ingest/upload-batch` — ① пакетный приём архива
`multipart/form-data`: `files` (один `.zip` и/или несколько прайсов), `clinic_id` (int, опц.).
Архив разворачивается, каждый файл обрабатывается отдельно. Клиника на файл — по
префиксу имени `«<id>_прайс.xlsx»`, иначе общий `clinic_id`.
```bash
curl -F files=@archive.zip -F clinic_id=1 localhost:8000/api/ingest/upload-batch
```
→ единый отчёт:
```json
{"files":[{"file":"1_lab.csv","status":"ok","clinic_id":1,"format":"csv",
           "items":12,"matched":11,"needs_review":1,"run_id":9}],
 "totals":{"files":3,"ok":3,"items":40,"matched":37,"needs_review":3}}
```
`status` файла: `ok` | `empty` | `error` (с полем `error`).

### `POST /api/ingest/archive` — приём архива прайсов партнёров (Кейс 2, MedArchive)
`multipart/form-data`: `files` (один `.zip` и/или несколько прайсов), `clinic_id` (uuid, опц.).
**Только админ.** Полный архивный пайплайн (отличие от `/upload-batch`, Кейс 1): извлечение
тарифов **резидент/нерезидент** раздельно, §4.4-валидации (нерезидент ≥ резидент,
аномалия отклонения >50%), code-first нормализация (код тарификатора → fuzzy → семантика)
и **сохранение оригиналов** в `/data/uploads` для повторной обработки. Партнёр для файла —
из префикса имени `«<uuid>_…»`, общего `clinic_id`, либо из имени файла (авто-создание клиники).
До 1000 файлов за приём (`truncated:true` при обрезке).
```bash
curl -F files=@partners.zip localhost:8000/api/ingest/archive
```
→ единый отчёт:
```json
{"files":[{"file":"Клиника А.xlsx","status":"ok","clinic_id":"<uuid>","format":"xlsx",
           "run_id":42,"items":120,"services":118,"matched":90,"needs_review":28,
           "skipped":2,"anomalies":1,"parse_status":"ok","stored":true}],
 "totals":{"files":5,"ok":5,"items":600,"matched":430,"needs_review":150,
           "anomalies":3,"stored":5},
 "truncated":false}
```
`status` файла: `ok` | `empty` | `error`; `parse_status` отражает качество разбора документа.

### `POST /api/ingest/archive/{run_id}/reprocess` — повторная обработка документа
**Только админ.** Перечитывает сохранённый **оригинал** прогона (`IngestionRun.file_path`) и
прогоняет архивный пайплайн заново на текущем справочнике (§2.1/§4.1). `404` — прогон/оригинал
не найден, `410` — файл недоступен на диске. → тот же блок статистики, что элемент `files[]` выше.

### `GET /api/ingest/stats` — сводка приёма (для админ-дашборда)
→ `{"clinics":75,"cities":7,"services":31,"prices":801,"runs":479,
   "needs_review":0,"by_source":{"web_scrape":801,"upload":12}}`

### `POST /api/ingest/preview` — сухой прогон нормализации (live-демо движка)
Прогоняет названия через тот же fuzzy+LLM-движок, что и боевой приём, но **без записи
в БД**. Для демонстрации, что нормализация не захардкожена: вход задаёт пользователь.
```json
{"names":["ОАК (5 параметров)","Кл. ан. крови развёрнутый","МРТ головного мозга"]}
```
→ `{"results":[{"raw":"...","canonical":"Общий анализ крови","category":"Анализы",
   "confidence":0.88,"method":"fuzzy","is_new":false,"candidates":[...]}, ...]}`
`method`: `fuzzy` | `fuzzy-weak` | `llm` | `new`. До 30 названий за запрос.

### `POST /api/ingest/preview-file` — распознать направление с фото/скана/PDF
`multipart/form-data`: `file`. OCR изображения/PDF рецепта → разбор строк тем же движком,
что `/preview` (gate + декомпозиция панелей + строгий матч), **без записи в БД**.
→ `{"results":[{"raw":...,"kind":...,"reason":...,"items":[...]}], "ocr_text":"…"}`.

### `POST /api/ingest/scrape` — ② веб-парсер
```json
{"clinic_id":3,"url":"https://clinic.kz/price","dynamic":false}
```
`dynamic:true` использует Playwright (нужна установка).

### `POST /api/ingest/scrape-html` — ② парсинг готового HTML (демо без сети)
```json
{"clinic_id":3,"html":"<table>...</table>"}
```

### `POST /api/ingest/api` — ② коннектор REST/JSON
```json
{"clinic_id":4,"endpoint":"https://clinic.kz/api/prices"}
```

### `POST /api/ingest/run-scheduled` — запустить автосбор по всем pull-источникам
→ `{"report":[{"source_id":1,"status":"ok","items":12}, ...]}`

### `GET /api/ingest/runs?limit=50` — журнал приёма
→ `IngestionRunOut[]`.

## Экспорт каталога (Кейс 1 — выходной артефакт)

### `GET /api/export/catalog?format=xlsx|csv`
Единый нормализованный каталог всех позиций (услуга · категория · клиника · город ·
район · адрес · телефон · цена · валюта · источник · уверенность · исходное название ·
актуально с). Отдаётся файлом-вложением. CSV — в `utf-8-sig` (корректная кириллица в Excel).
```bash
curl -OJ "localhost:8000/api/export/catalog?format=xlsx"
```

> **Гард нормализации.** Несопоставимые позиции не сливаются в одну услугу:
> - **Приёмы:** повторный / онлайн / детский приём → отдельная услуга, не «Приём X».
> - **Аналиты:** «Глюкоза в моче» ≠ «Глюкоза (в крови)», «Глюкозотолерантный тест» ≠ обычная глюкоза, «Креатинин в моче» ≠ «Креатинин».
>
> Иначе сравнение цен и «🏆 Лучшая цена» смешивали бы разные продукты. Уверенность
> сопоставления на витрине — реальная (`token_set_ratio` к эталону, пол 0.82), а не зашитые 100%.

## Агрегатор (Кейс 2)

### `GET /api/search` — поиск услуг + сводка сравнения
Параметры: `q`, `city`, `category` (по enum-категории ТЗ), `min_price`, `max_price`,
`min_rating`, `online_booking`, `user_lat`/`user_lng` (для сортировки по близости),
`sort` (`price_asc`|`price_desc`|`updated`|`distance`), `limit`. Возвращаются только услуги,
у которых есть хотя бы одна свежая цена.
→ `ServiceComparison[]`:
```json
[{"service_id":1,"canonical_name":"Общий анализ крови","category":"Анализы",
  "offers_count":6,"min_price":1900,"max_price":2700,"offers":[ ... ]}]
```

### `GET /api/compare/{service_id}` — сравнение цен по услуге
Параметры: `city`, `min_price`, `max_price`, `min_rating`, `online_booking`,
`user_lat`/`user_lng`, `sort` (`price_asc`|`price_desc`|`updated`|`distance`).
→ один `ServiceComparison` (с вариантами услуги и трендом цены). Каждый `PriceOffer`:
```json
{"clinic_id":4,"clinic_name":"Медцентр «Жан»","city":"Алматы","district":"Ауэзовский",
 "address":"...","lat":43.21,"lng":76.83,"phone":"...","price":1900,"currency":"KZT",
 "raw_name":"Общ. анализ крови","source_type":"web_scrape","match_confidence":0.93,
 "valid_from":"2026-06-17"}
```

### `GET /api/categories` → `string[]`
Enum-категории ТЗ (лаборатория/приём врача/диагностика/процедура), только реально присутствующие.
### `GET /api/cities` → `string[]`
Города, где **есть цены** (без пустых). Полный охват рынка — в `/api/cities/coverage`.
### `GET /api/cities/coverage`
Все 90 городов РК из справочника + флаг наличия данных:
`[{"name","region","status","status_label","slug","clinics","has_data"}, ...]`.
### `GET /api/services?q=&category=&limit=` → `ServiceOut[]`

### `GET /api/suggest?q=&limit=10` → `string[]`
§3.3 автодополнение по справочнику: только релевантные услуги (точный токен/префикс, не
подстрока внутри слова), отсортированные по релевантности. Пустой результат при `q` короче 2 символов.

### `GET /api/services/{service_id}/history` — история/тренд цены услуги
→ `{"service_id","canonical_name","trend":{"points":[{"date","median"}],"change_pct","direction"}}`.
`trend` = `null`, если точек истории меньше двух. Уникальный SEO-контент.

### `GET /api/records` — плоская выгрузка собираемых данных (§2.2)
Параметры: `city`, `service_id`, `active_only`, `limit` (1..1000), `offset`.
→ `CollectedRecord[]` — кортежи (клиника × услуга × цена) дословно по полям/типам ТЗ
(строгие enum `category`/`currency`, нормализованное имя из привязки к справочнику).

### `GET /api/ontology` — онтология справочника
→ `{"groups":[...],"services":[{"service_id","canonical_name", ...код/группа/ОСМС}]}`.

### `POST /api/compare-clinics` — сравнительная таблица клиник по набору услуг (§3.4)
Тело `ClinicCompareIn`:
```json
{"service_ids":["<uuid>", "..."],   // ≤8 услуг
 "clinic_ids":["<uuid>"],            // опц. 2–4 клиники; пусто → автоподбор по покрытию+цене
 "city":"Алматы", "user_lat":43.2, "user_lng":76.9, "require_all":false}
```
→ `ClinicCompareOut`: услуги-колонки, клиники-строки с ячейками (цена/🏆-лучшая/источник/
свежесть), `total`/`savings_vs_max`/`covers_all` по каждой клинике, `max_total` и
`recommendations` (`cheapest` / `nearest` / `best_balance`). «Не найдено» вместо нуля.

## Чат-помощник (🤖)

### `POST /api/chat` — диалоговый поиск по витрине
Бот = надстройка над агрегатором: сам ищет по нормализованному справочнику
(retrieval-injection) и отвечает строго по найденным данным, не выдумывая цены.
Провайдер LLM — AlemLLM (или Groq), переключается через `LLM_PROVIDER`. Без ключа
провайдера деградирует в детерминированный поиск-сводку.

Тело (`messages` — история диалога, роли `user` / `assistant`):
```json
{"messages":[{"role":"user","content":"Где дешевле общий анализ крови в Алматы?"}]}
```
→ `ChatResponse`:
```json
{
  "reply": "Самая выгодная — INVITRO Алматы, 520 ₸. Цены справочные, уточняйте в клинике.",
  "offers": [
    {"service":"Общий анализ крови","clinic_name":"INVITRO Алматы","city":"Алматы",
     "district":"Алмалинский","address":"...","phone":"+7 727 ...","price":520,
     "currency":"KZT","is_cheapest":true}
  ],
  "grounded": true,   // ответ построен на реальных данных витрины
  "llm": true         // отвечал LLM (false = детерминированный фолбэк)
}
```
```bash
curl -X POST localhost:8000/api/chat -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"сколько стоит ОАК?"}]}'
```

## Клиники
- `GET /api/clinics?city=` → `ClinicOut[]`
- `POST /api/clinics` (тело `ClinicIn`) → `ClinicOut`
- `GET /api/clinics/{id}` → `ClinicOut`
- `GET /api/clinics/{id}/prices` → `PriceOut[]`
- `GET /api/clinics/{id}/profile` → карточка клиники (§3.3): контакты, сайт (фолбэк — URL
  источника прайса), режим работы, рейтинг, гео + ВСЕ услуги с ценами (нормализованное имя,
  срок, источник, дата обновления, флаг `is_active`), `services_count`.

## Подписки на снижение цены (§3.4, опц.)

Пользователь оставляет номер + услугу (опц. клинику/город); планировщик уведомляет в WhatsApp при снижении.

- `POST /api/subscriptions` (rate-limited ~10/мин) — оформить подписку.
  Тело: `{"service_id":"<uuid>","clinic_id":"<uuid>?","city":"?","phone":"+7..."}`.
  Идемпотентно по (телефон, услуга, клиника). → `{"ok":true,"id","tracking_price"}`
  (или `{"ok":true,"id","already":true}` для существующей).
- `DELETE /api/subscriptions/{id}` — отписаться (деактивирует). → `{"ok":true}`.
- `GET /api/subscriptions` — список подписок. **Только админ.**

## MedArchive — обработка архива прайсов партнёров (Кейс 2)

Контракт «кто оказывает услугу и по какой цене» поверх единой платформы
(партнёр = клиника, услуга = справочник). Приём архива — через HTTP
`POST /api/ingest/archive` (см. раздел «Приём данных») либо CLI
`python -m app.archive_ingest <папка|zip> --catalog "Справочник услуг.xlsx" [--semantic-pass]`,
выходной артефакт — `docs/quality-report.md` (отчёт о качестве обработки).

- `GET /api/partners?city=` → партнёры с числом услуг (`partner_id`/`name`/`city`/`address`/`phone`/`services_count`).
- `GET /api/partners/{id}/services` → все услуги партнёра с ценами **резидент/нерезидент**
  (`tarificator_code`, `category`, `specialty`, `match_confidence`).
- `GET /api/services/{id}/partners` → кто оказывает услугу, от дешёвой цены (резидент/нерезидент).
- `GET /api/unmatched?limit=200` → очередь несопоставленных позиций (`service_id IS NULL`), для операторов.
- `POST /api/match` `{price_id, service_id}` — ручное сопоставление (запоминает синоним). **Только админ.**
- `GET /api/archive/quality` → метрики дашборда качества обработки **архива** (по архивным прогонам, не по всему каталогу):
  ```json
  {"documents":10,"positions":..., "auto_normalized":..., "auto_rate_percent":72.0,
   "unmatched_queue":..., "with_tarificator_code":..., "goal_70_met":true,
   "catalog_positions":...}
  ```
  `goal_70_met` = `true` при `documents>0` и `auto_rate_percent ≥ 70`. `catalog_positions` —
  объём всего каталога-агрегатора (Кейс 1) для контекста.

Нормализация трёхтировая: **код тарификатора** (точно) → нечётко (rapidfuzz) →
семантика (эмбеддинги). Цены резидент/нерезидент извлекаются раздельно из
DOCX (с принятием tracked changes), XLSX/XLS (многострочная шапка) и PDF.

## Служебное
- `GET /health` → `{"status":"ok"}`
