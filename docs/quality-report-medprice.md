# Отчёт о реальных данных (MedPrice, Кейс1 §6)

_Сгенерировано: `python -m app.seed_real`._

## Сводка
- Успешных источников: **30** (цель ТЗ ≥3)
- Клиник в базе: **26**
- Позиций справочника услуг: **491** (цель ≥50)
- Строк цен: **1162**
- Уникальных услуг с ценой: **491** (цель ≥100)
- Города (8): Абай, Актобе, Алматы, Астана, Байконуре, Еркинкала, Шаян, Шымкент

## По источникам

| Источник | Канал | Клиника | Город | Позиций | Сопоставлено |
|---|---|---|---|---:|---:|
| https://www.kdlolymp.kz/pricelist/abay | web_scrape | KDL-Olymp — Абай | Абай | 219 | 85 |
| https://www.kdlolymp.kz/pricelist/baykonur | web_scrape | KDL-Olymp — Байконуре | Байконуре | 205 | 203 |
| https://www.kdlolymp.kz/pricelist/erkinkala | web_scrape | KDL-Olymp — Еркинкала | Еркинкала | 235 | 231 |
| https://www.kdlolymp.kz/pricelist/shayan | web_scrape | KDL-Olymp — Шаян | Шаян | 213 | 213 |
| Клиника 1 2026.pdf | upload | Клиника 1 | Алматы | 120 | 32 |
| Клиника 1 прайс 2024.docx | upload | Клиника 1 | Астана | 120 | 112 |
| Клиника 2 прайс 2025 год.PDF | upload | Клиника 2 | Шымкент | 120 | 98 |
| Клиника 2 прайс 2026.pdf | upload | Клиника 2 | Актобе | 120 | 113 |
| https://www.invitro.kz/analizes/ | web_scrape | Invitro — Алматы | Алматы | 2126 | — |
| doq:ЭМИРМЕД (doq) | upload | ЭМИРМЕД (doq) | Алматы | 11 | 5 |
| doq:Via Medical (doq) | upload | Via Medical (doq) | Алматы | 12 | 7 |
| doq:Alash Expert Clinic (doq) | upload | Alash Expert Clinic (doq) | Алматы | 12 | 9 |
| doq:AQMED (doq) | upload | AQMED (doq) | Алматы | 12 | 11 |
| doq:ЭМИРМЕД (doq) | upload | ЭМИРМЕД (doq) | Астана | 12 | 9 |
| doq:Lucem Medical Clinic (Люцем Медикал Центр) (doq) | upload | Lucem Medical Clinic (Люцем Медикал Центр) (doq) | Астана | 12 | 11 |
| doq:МДС Сервис Плюс (doq) | upload | МДС Сервис Плюс (doq) | Астана | 12 | 11 |
| doq:Alanda clinic (doq) | upload | Alanda clinic (doq) | Астана | 11 | 11 |
| doq:Эмирмед (doq) | upload | Эмирмед (doq) | Шымкент | 11 | 10 |
| doq:Murat Medical Center (doq) | upload | Murat Medical Center (doq) | Шымкент | 12 | 10 |
| doq:Венера (doq) | upload | Венера (doq) | Шымкент | 11 | 10 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Актобе | 4 | 3 |
| doq:Gravita clinic (doq) | upload | Gravita clinic (doq) | Актобе | 12 | 9 |
| doq:DiVera (doq) | upload | DiVera (doq) | Актобе | 12 | 11 |
| 103:Гемотест (103.kz) | upload | Гемотест (103.kz) | Алматы | 299 | 219 |
| 103:INVITRO (ИНВИТРО) (103.kz) | upload | INVITRO (ИНВИТРО) (103.kz) | Алматы | 300 | 271 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Алматы | 282 | 220 |
| 103:Рахат (103.kz) | upload | Рахат (103.kz) | Алматы | 227 | 180 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Алматы | 3 | 3 |
| 103:AQmed (АКмед) (103.kz) | upload | AQmed (АКмед) (103.kz) | Алматы | 300 | 234 |
| 103:Smartmed (Смартмед) (103.kz) | upload | Smartmed (Смартмед) (103.kz) | Алматы | 71 | 54 |

## Соблюдение правил ТЗ §8
- robots.txt соблюдается единым шлюзом `ingestion/robots.py` (Protego) — все GET через `polite_get`.
- crawl-delay пер-хост (не создаём чрезмерную нагрузку).
- Собираются только публичные прайсы; персональные данные не собираются.

_Прим.: invitro/doq/2gis отдают данные через JS/SPA-API, olymp/helix/medel/mck недоступны статикой с этого сервера — для них в `web_scraper` есть адаптеры, подключаемые по доступности (вкл. Playwright для SPA)._
