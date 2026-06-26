# Отчёт о реальных данных (MedPrice, Кейс1 §6)

_Сгенерировано: `python -m app.seed_real`._

## Сводка
- Успешных источников: **73** (цель ТЗ ≥3)
- Клиник в базе: **42**
- Позиций справочника услуг: **600** (цель ≥50)
- Строк цен: **1908**
- Уникальных услуг с ценой: **600** (цель ≥100)
- Города (16): Абай, Актау, Актобе, Алматы, Астана, Байконуре, Еркинкала, Караганда, Кокшетау, Кызылорда, Павлодар, Семей, Тараз, Усть-Каменогорск, Шаян, Шымкент

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
| https://kazmedclinic.kz/ceny | web_scrape | KazMedClinic — Алматы | Алматы | 823 | — |
| doq:ЭМИРМЕД (doq) | upload | ЭМИРМЕД (doq) | Алматы | 9 | 3 |
| doq:Via Medical (doq) | upload | Via Medical (doq) | Алматы | 10 | 6 |
| doq:Alash Expert Clinic (doq) | upload | Alash Expert Clinic (doq) | Алматы | 10 | 8 |
| doq:ЭМИРМЕД (doq) | upload | ЭМИРМЕД (doq) | Астана | 10 | 8 |
| doq:Lucem Medical Clinic (Люцем Медикал Центр) (doq) | upload | Lucem Medical Clinic (Люцем Медикал Центр) (doq) | Астана | 10 | 10 |
| doq:МДС Сервис Плюс (doq) | upload | МДС Сервис Плюс (doq) | Астана | 10 | 9 |
| doq:ALDIMED (doq) | upload | ALDIMED (doq) | Караганда | 10 | 7 |
| doq:SAMED (doq) | upload | SAMED (doq) | Караганда | 10 | 10 |
| doq:Юта (doq) | upload | Юта (doq) | Караганда | 7 | 5 |
| doq:Эмирмед (doq) | upload | Эмирмед (doq) | Шымкент | 9 | 9 |
| doq:Murat Medical Center (doq) | upload | Murat Medical Center (doq) | Шымкент | 10 | 8 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Кокшетау | 4 | 3 |
| doq:Divera Кокшетау (doq) | upload | Divera Кокшетау (doq) | Кокшетау | 8 | 7 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Актобе | 4 | 4 |
| doq:Gravita clinic (doq) | upload | Gravita clinic (doq) | Актобе | 10 | 8 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Кызылорда | 5 | 4 |
| doq:Orhun Medical (doq) | upload | Orhun Medical (doq) | Кызылорда | 2 | 2 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Актау | 4 | 4 |
| doq:Orhun Medical (doq) | upload | Orhun Medical (doq) | Актау | 9 | 8 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Тараз | 4 | 4 |
| doq:Orhun Medical (doq) | upload | Orhun Medical (doq) | Тараз | 10 | 10 |
| doq:MedPro Clinic (doq) | upload | MedPro Clinic (doq) | Тараз | 10 | 8 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Усть-Каменогорск | 4 | 4 |
| doq:Divera Усть-Каменогорск (doq) | upload | Divera Усть-Каменогорск (doq) | Усть-Каменогорск | 10 | 9 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Павлодар | 3 | 3 |
| doq:"Umay med" Центр остеопатии Казахстана (doq) | upload | "Umay med" Центр остеопатии Казахстана (doq) | Павлодар | 2 | 1 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Семей | 4 | 4 |
| doq:Orhun Medical (doq) | upload | Orhun Medical (doq) | Семей | 1 | 1 |
| doq:Divera (doq) | upload | Divera (doq) | Семей | 9 | 9 |
| 103:ЭЛИФ-Ай (103.kz) | upload | ЭЛИФ-Ай (103.kz) | Алматы | 300 | 200 |
| 103:Smartmed (Смартмед) (103.kz) | upload | Smartmed (Смартмед) (103.kz) | Алматы | 71 | 57 |
| 103:Эмирмед (103.kz) | upload | Эмирмед (103.kz) | Алматы | 300 | 223 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Алматы | 3 | 3 |
| 103:Рахат (103.kz) | upload | Рахат (103.kz) | Астана | 300 | 248 |
| 103:Eltai Clinic (Элтай Клиник) (103.kz) | upload | Eltai Clinic (Элтай Клиник) (103.kz) | Астана | 113 | 96 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Астана | 282 | 234 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Астана | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Шымкент | 282 | 282 |
| 103:Aqua Lab (Аква Лаб) (103.kz) | upload | Aqua Lab (Аква Лаб) (103.kz) | Шымкент | 299 | 279 |
| 103:Венера (103.kz) | upload | Венера (103.kz) | Шымкент | 73 | 56 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Шымкент | 1 | 1 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Актобе | 282 | 282 |
| 103:INVITRO (Инвитро) (103.kz) | upload | INVITRO (Инвитро) (103.kz) | Актобе | 284 | 276 |
| 103:Микролабсервис (103.kz) | upload | Микролабсервис (103.kz) | Актобе | 1 | 1 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Актобе | 282 | 282 |
| 103:Sanguis (Сангвис) (103.kz) | upload | Sanguis (Сангвис) (103.kz) | Караганда | 205 | 183 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Караганда | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Караганда | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Караганда | 282 | 282 |
| 103:Helix (Хеликс) (103.kz) | upload | Helix (Хеликс) (103.kz) | Павлодар | 300 | 278 |
| 103:INVITRO (ИНВИТРО) (103.kz) | upload | INVITRO (ИНВИТРО) (103.kz) | Павлодар | 284 | 284 |
| 103:Sanguis (Сангвис) (103.kz) | upload | Sanguis (Сангвис) (103.kz) | Павлодар | 205 | 205 |
| 103:Аллергоскрин (103.kz) | upload | Аллергоскрин (103.kz) | Павлодар | 6 | 5 |
| 103:Гемотест (103.kz) | upload | Гемотест (103.kz) | Тараз | 300 | 240 |
| 103:INVITRO (ИНВИТРО) (103.kz) | upload | INVITRO (ИНВИТРО) (103.kz) | Актау | 284 | 284 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Актау | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Актау | 282 | 282 |
| 103:Гемотест (103.kz) | upload | Гемотест (103.kz) | Алматы | 299 | 288 |
| 103:INVITRO (ИНВИТРО) (103.kz) | upload | INVITRO (ИНВИТРО) (103.kz) | Алматы | 300 | 290 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Алматы | 282 | 282 |
| 103:Рахат (103.kz) | upload | Рахат (103.kz) | Алматы | 227 | 216 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Алматы | 3 | 3 |
| 103:AQmed (АКмед) (103.kz) | upload | AQmed (АКмед) (103.kz) | Алматы | 300 | 289 |

## Соблюдение правил ТЗ §8
- robots.txt соблюдается единым шлюзом `ingestion/robots.py` (Protego) — все GET через `polite_get`.
- crawl-delay пер-хост (не создаём чрезмерную нагрузку).
- Собираются только публичные прайсы; персональные данные не собираются.

_Прим.: invitro/doq/2gis отдают данные через JS/SPA-API, olymp/helix/medel/mck недоступны статикой с этого сервера — для них в `web_scraper` есть адаптеры, подключаемые по доступности (вкл. Playwright для SPA)._
