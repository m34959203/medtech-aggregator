# API — контракт

Base URL: `http://localhost:8000`. Интерактивная документация: `/docs` (Swagger), `/redoc`.

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

### `POST /api/ingest/preview` — сухой прогон нормализации (live-демо движка)
Прогоняет названия через тот же fuzzy+LLM-движок, что и боевой приём, но **без записи
в БД**. Для демонстрации, что нормализация не захардкожена: вход задаёт пользователь.
```json
{"names":["ОАК (5 параметров)","Кл. ан. крови развёрнутый","МРТ головного мозга"]}
```
→ `{"results":[{"raw":"...","canonical":"Общий анализ крови","category":"Анализы",
   "confidence":0.88,"method":"fuzzy","is_new":false,"candidates":[...]}, ...]}`
`method`: `fuzzy` | `fuzzy-weak` | `llm` | `new`. До 30 названий за запрос.

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

## Агрегатор (Кейс 2)

### `GET /api/search` — поиск услуг + сводка сравнения
Параметры: `q`, `city`, `category`, `max_price`, `sort` (`price_asc`|`price_desc`), `limit`.
→ `ServiceComparison[]`:
```json
[{"service_id":1,"canonical_name":"Общий анализ крови","category":"Анализы",
  "offers_count":6,"min_price":1900,"max_price":2700,"offers":[ ... ]}]
```

### `GET /api/compare/{service_id}` — сравнение цен по услуге
Параметры: `city`, `max_price`, `sort`.
→ один `ServiceComparison`. Каждый `PriceOffer`:
```json
{"clinic_id":4,"clinic_name":"Медцентр «Жан»","city":"Алматы","district":"Ауэзовский",
 "address":"...","lat":43.21,"lng":76.83,"phone":"...","price":1900,"currency":"KZT",
 "raw_name":"Общ. анализ крови","source_type":"web_scrape","match_confidence":0.93,
 "valid_from":"2026-06-17"}
```

### `GET /api/categories` → `string[]`
### `GET /api/cities` → `string[]`
### `GET /api/services?q=&category=&limit=` → `ServiceOut[]`

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

## Служебное
- `GET /health` → `{"status":"ok"}`
