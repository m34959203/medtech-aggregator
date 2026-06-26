# MedArchive — чекпоинт возобновления (2026-06-26)

Директива Дмитрия: **сдаём MedPrice (наш текущий продукт), но платформа под капотом
должна уметь MedArchive** (обработка готового архива прайсов партнёров). Ведущий
single-price путь MedPrice НЕ трогаем — MedArchive добавляем параллельным движком.

Ветка: `feat/product-evolution`. Прод (`main`, medtech.technokod.kz) ЗАМОРОЖЕН.

## Входные данные (официальные, от организаторов)
Лежат в `docs/` на `origin/main` (НЕ в рабочей ветке). Выгрузить:
```
git show "origin/main:docs/Справочник услуг.xlsx" > /tmp/spr.xlsx
```
Для разработки уже распакованы в `/home/ubuntu/medtech-aggregator/.archive_samples/`
(8 прайсов + `Справочник услуг.xlsx` + 2 ТЗ docx). **В git не коммитить** (бинарь,
персональные прайсы) — это dev-фикстуры.

- **Справочник услуг.xlsx**: 1286 услуг, колонки `ID·Специальность·Code·Name_ru·TarificatrCode`.
  Формат кода `A02.004.000`. Синонимов НЕТ → матчинг по коду + нечётко по Name_ru.
- **8 прайсов**: Клиника 1 (pdf+docx), 2 (2×pdf), 3 (pdf), 4 (pdf), 5 (pdf),
  6 (xlsx), 7 (.xls OLE2), 8 (xlsx multi-sheet).

## Условия ТЗ MedArchive (что обязательно)
резидент/нерезидент-цены · OCR-сканы · DOCX+tracked-changes · .xls · multi-sheet ·
маппинг по TarificatrCode · валидации · версионирование · отчёт о качестве
(**цель ≥70% автонормализации**) · API `/services`,`/services/{id}/partners`,
`/partners`,`/partners/{id}/services`,`/search`,`/unmatched`,POST`/match` (OpenAPI).

## ✅ СДЕЛАНО — #1 Экстрактор
`backend/app/ingestion/archive_extractor.py` — проверен на всех 8 файлах:
**17143 позиции, 7758 с кодом.** API:
```python
from app.ingestion import archive_extractor as ae
fmt, items = ae.detect_and_parse(filename, content_bytes)  # items: list[ArchiveItem]
# ArchiveItem(name, code, price_resident, price_nonresident, price_original, currency)
ae.norm_code(s)      # 'В02.110.002'(кирилл) -> 'B02.110.002'(латин)
ae.parse_price(v)    # '10 002'/'10.002' -> 10002.0
```
Решённые гочи (см. историю): кириллическая буква в коде; «Код услуги» утекал в name;
резидент/нерезидент путались; разделитель тысяч; многострочная шапка; разорванные
числовые токены в PDF. Качество: xlsx/xls/docx чисто; текстовые PDF — данные + шум
строк-заголовков (нормализатор отсеет в needs_review); Клиника 5 частично.

Прогнать заново:
```
cd backend && python3 -c "
import glob,os; from app.ingestion import archive_extractor as ae
for f in sorted(glob.glob('../.archive_samples/Клиника*')):
    fmt,items=ae.detect_and_parse(os.path.basename(f),open(f,'rb').read())
    print(os.path.basename(f), fmt, len(items), sum(1 for i in items if i.code))
"
```

## ⬜ ОСТАЛОСЬ (порядок)
2. **Загрузчик справочника** → `ServiceCatalog` с `tarificator_code` + `specialty`.
   Идемпотентно (upsert по tarificator_code). Источник — Справочник услуг.xlsx.
3. **Нормализатор архива (code-first)**: точное совпадение `tarificator_code` → conf=1.0;
   иначе текущий `Normalizer` (fuzzy+семантика). Переиспользовать `ingestion/normalizer.py`.
4. **Модель (аддитивно, nullable — НЕ ломать прод/MedPrice)**:
   - `Price`: `price_resident`, `price_nonresident`, `service_code_source`, `tarificator_code`.
   - `ServiceCatalog`: `tarificator_code` (uniq, index), `specialty`.
   - `IngestionRun`: `file_name`, `raw_content` (для аудита), `parse_status`.
   - Alembic-миграция. Валидации: цена>0, нерезидент≥резидент (флаг review),
     дата не в будущем, |Δ|>50% к прошлой версии → аномалия.
5. **CLI `python -m app.archive_ingest <dir|zip>`**: прогнать архив → БД →
   `docs/quality-report.md` (документов, позиций, % auto-match, unmatched, по файлам)
   против цели ≥70%. Это обязательный артефакт сдачи.
6. **API-контракт MedArchive** поверх clinics/services: `/partners`,
   `/partners/{id}/services`, `/services/{id}/partners`, `/unmatched`, POST`/match`,
   с резидент/нерезидент в выдаче. OpenAPI (FastAPI `/docs`).

## Среда
- Сервер: tesseract НЕ установлен, pytesseract нет → OCR graceful (текстовый слой есть).
- deps есть: python-docx, xlrd, pdfplumber, pymupdf, lxml, openpyxl, rapidfuzz, fastembed.
- pip: `pip install --user --break-system-packages` (venv недоступен).
- Трекер задач: #1 done, #2–6 pending.
