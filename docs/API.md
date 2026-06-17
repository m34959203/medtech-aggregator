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

## Клиники
- `GET /api/clinics?city=` → `ClinicOut[]`
- `POST /api/clinics` (тело `ClinicIn`) → `ClinicOut`
- `GET /api/clinics/{id}` → `ClinicOut`
- `GET /api/clinics/{id}/prices` → `PriceOut[]`

## Служебное
- `GET /health` → `{"status":"ok"}`
