# Отчёт о реальных данных (MedPrice, Кейс1 §6)

_Актуально на 2026-06-27 (живой Postgres). Детальная разбивка ниже — иллюстративный
снимок наполнения через `python -m app.seed_real` + боевой прогон архива._

## Сводка (текущий прод)
- Клиник в базе: **107** (цель ТЗ ≥3 источника — кратно превышена)
- Позиций справочника услуг: **1985** (цель ≥50); из них **1191** — официальный «Справочник услуг.xlsx» с кодами тарификатора
- Строк цен: **10 078** (цель ≥100)
- Города: **14** (Алматы, Астана, Караганда, Актобе, Шымкент, Актау, Семей, Павлодар, Петропавловск, Усть-Каменогорск, Тараз, Костанай, Талдыкорган, Кызылорда)
- Резидент/нерезидент (двойной тариф): **3767** цен; очередь ревью (unmatched): **4264**
- Источники: web-scrape (KDL/Invitro/103.kz и др.) + REST API (doq.kz) + upload-архив (Кейс 2)

## По источникам (иллюстративный seed-снимок)

| Источник | Канал | Клиника | Город | Позиций | Сопоставлено |
|---|---|---|---|---:|---:|
| https://www.kdlolymp.kz/pricelist/abay | web_scrape | KDL-Olymp — Абай | Абай | 219 | 219 |
| https://www.kdlolymp.kz/pricelist/baykonur | web_scrape | KDL-Olymp — Байконуре | Байконуре | 205 | 205 |
| https://www.kdlolymp.kz/pricelist/erkinkala | web_scrape | KDL-Olymp — Еркинкала | Еркинкала | 235 | 235 |
| https://www.kdlolymp.kz/pricelist/shayan | web_scrape | KDL-Olymp — Шаян | Шаян | 213 | 213 |
| Клиника 1 2026.pdf | upload | Клиника 1 | Алматы | 120 | 120 |
| Клиника 1 прайс 2024.docx | upload | Клиника 1 | Астана | 120 | 120 |
| Клиника 2 прайс 2025 год.PDF | upload | Клиника 2 | Шымкент | 120 | 120 |
| Клиника 2 прайс 2026.pdf | upload | Клиника 2 | Актобе | 120 | 120 |
| https://www.invitro.kz/analizes/ | web_scrape | Invitro — Алматы | Алматы | 2126 | — |
| https://kazmedclinic.kz/ceny | web_scrape | KazMedClinic — Алматы | Алматы | 823 | — |
| doq:ЭМИРМЕД (doq) | upload | ЭМИРМЕД (doq) | Алматы | 9 | 9 |
| doq:Via Medical (doq) | upload | Via Medical (doq) | Алматы | 10 | 10 |
| doq:Alash Expert Clinic (doq) | upload | Alash Expert Clinic (doq) | Алматы | 10 | 10 |
| doq:ЭМИРМЕД (doq) | upload | ЭМИРМЕД (doq) | Астана | 10 | 10 |
| doq:Lucem Medical Clinic (Люцем Медикал Центр) (doq) | upload | Lucem Medical Clinic (Люцем Медикал Центр) (doq) | Астана | 10 | 10 |
| doq:МДС Сервис Плюс (doq) | upload | МДС Сервис Плюс (doq) | Астана | 10 | 10 |
| doq:ALDIMED (doq) | upload | ALDIMED (doq) | Караганда | 10 | 10 |
| doq:SAMED (doq) | upload | SAMED (doq) | Караганда | 10 | 10 |
| doq:Юта (doq) | upload | Юта (doq) | Караганда | 7 | 7 |
| doq:Эмирмед (doq) | upload | Эмирмед (doq) | Шымкент | 9 | 9 |
| doq:Murat Medical Center (doq) | upload | Murat Medical Center (doq) | Шымкент | 10 | 10 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Кокшетау | 4 | 4 |
| doq:Divera Кокшетау (doq) | upload | Divera Кокшетау (doq) | Кокшетау | 8 | 8 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Актобе | 4 | 4 |
| doq:Gravita clinic (doq) | upload | Gravita clinic (doq) | Актобе | 10 | 10 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Кызылорда | 5 | 5 |
| doq:Orhun Medical (doq) | upload | Orhun Medical (doq) | Кызылорда | 2 | 2 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Актау | 4 | 4 |
| doq:Orhun Medical (doq) | upload | Orhun Medical (doq) | Актау | 9 | 9 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Тараз | 4 | 4 |
| doq:Orhun Medical (doq) | upload | Orhun Medical (doq) | Тараз | 10 | 10 |
| doq:MedPro Clinic (doq) | upload | MedPro Clinic (doq) | Тараз | 10 | 10 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Усть-Каменогорск | 4 | 4 |
| doq:Divera Усть-Каменогорск (doq) | upload | Divera Усть-Каменогорск (doq) | Усть-Каменогорск | 10 | 10 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Павлодар | 3 | 3 |
| doq:"Umay med" Центр остеопатии Казахстана (doq) | upload | "Umay med" Центр остеопатии Казахстана (doq) | Павлодар | 2 | 2 |
| doq:Цифровая клиника – EmAI (doq) | upload | Цифровая клиника – EmAI (doq) | Семей | 4 | 4 |
| doq:Orhun Medical (doq) | upload | Orhun Medical (doq) | Семей | 1 | 1 |
| doq:Divera (doq) | upload | Divera (doq) | Семей | 9 | 9 |
| 103:ЭЛИФ-Ай (103.kz) | upload | ЭЛИФ-Ай (103.kz) | Алматы | 300 | 300 |
| 103:Эмирмед (103.kz) | upload | Эмирмед (103.kz) | Алматы | 300 | 300 |
| 103:Smartmed (Смартмед) (103.kz) | upload | Smartmed (Смартмед) (103.kz) | Алматы | 71 | 71 |
| 103:Alatau Lab (Алатау Лаб) (103.kz) | upload | Alatau Lab (Алатау Лаб) (103.kz) | Алматы | 5 | 5 |
| 103:Рахат (103.kz) | upload | Рахат (103.kz) | Астана | 300 | 300 |
| 103:Eltai Clinic (Элтай Клиник) (103.kz) | upload | Eltai Clinic (Элтай Клиник) (103.kz) | Астана | 113 | 113 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Астана | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Астана | 282 | 282 |
| 103:Гемотест (103.kz) | upload | Гемотест (103.kz) | Шымкент | 300 | 300 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Шымкент | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Шымкент | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Шымкент | 282 | 282 |
| 103:Микролабсервис (103.kz) | upload | Микролабсервис (103.kz) | Актобе | 1 | 1 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Актобе | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Актобе | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Актобе | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Караганда | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Караганда | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Караганда | 282 | 282 |
| 103:INVITRO (ИНВИТРО) (103.kz) | upload | INVITRO (ИНВИТРО) (103.kz) | Павлодар | 284 | 284 |
| 103:Helix (Хеликс) (103.kz) | upload | Helix (Хеликс) (103.kz) | Павлодар | 300 | 300 |
| 103:Аллергоскрин (103.kz) | upload | Аллергоскрин (103.kz) | Павлодар | 6 | 6 |
| 103:Sanguis (Сангвис) (103.kz) | upload | Sanguis (Сангвис) (103.kz) | Павлодар | 205 | 205 |
| 103:Гемотест (103.kz) | upload | Гемотест (103.kz) | Тараз | 300 | 300 |
| 103:INVITRO (ИНВИТРО) (103.kz) | upload | INVITRO (ИНВИТРО) (103.kz) | Актау | 284 | 284 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Актау | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Актау | 282 | 282 |
| 103:Mediker Ondiris (Медикер Ондирис) (103.kz) | upload | Mediker Ondiris (Медикер Ондирис) (103.kz) | Кызылорда | 1 | 1 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Атырау | 285 | 285 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Атырау | 285 | 285 |
| 103:INVITRO (ИНВИТРО) (103.kz) | upload | INVITRO (ИНВИТРО) (103.kz) | Атырау | 284 | 284 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Атырау | 2 | 2 |
| 103:Митралия (103.kz) | upload | Митралия (103.kz) | Петропавловск | 300 | 300 |
| 103:Митралия (103.kz) | upload | Митралия (103.kz) | Петропавловск | 300 | 300 |
| 103:Med Elit (Мед Элит) (103.kz) | upload | Med Elit (Мед Элит) (103.kz) | Петропавловск | 194 | 194 |
| 103:INVITRO (ИНВИТРО) (103.kz) | upload | INVITRO (ИНВИТРО) (103.kz) | Семей | 284 | 284 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Семей | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Семей | 282 | 282 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Семей | 282 | 282 |
| 103:INVITRO (ИНВИТРО) (103.kz) | upload | INVITRO (ИНВИТРО) (103.kz) | Талдыкорган | 284 | 284 |
| 103:Областной кардиологический центр г. Талдыкорган (103.kz) | upload | Областной кардиологический центр г. Талдыкорган (103.kz) | Талдыкорган | 8 | 8 |
| 103:Гемотест (103.kz) | upload | Гемотест (103.kz) | Алматы | 299 | 299 |
| 103:INVITRO (ИНВИТРО) (103.kz) | upload | INVITRO (ИНВИТРО) (103.kz) | Алматы | 300 | 300 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Алматы | 282 | 282 |
| 103:Рахат (103.kz) | upload | Рахат (103.kz) | Алматы | 227 | 227 |
| 103:КДЛ ОЛИМП (103.kz) | upload | КДЛ ОЛИМП (103.kz) | Алматы | 3 | 3 |
| 103:AQmed (АКмед) (103.kz) | upload | AQmed (АКмед) (103.kz) | Алматы | 300 | 300 |
| 103chain:invitro-kz1 | upload | INVITRO (ИНВИТРО) (103.kz) | Алматы | 284 | 284 |
| 103chain:invitro-1 | upload | INVITRO (ИНВИТРО) (103.kz) | Алматы | 284 | 284 |
| 103chain:olimp-1 | upload | КДЛ ОЛИМП (103.kz) | Алматы | 2 | 2 |
| 103chain:invitro-kz | upload | INVITRO (Инвитро) (103.kz) | Актобе | 284 | 284 |
| 103chain:invitro-kz-1 | upload | INVITRO (Инвитро) (103.kz) | Актобе | 284 | 284 |
| 103chain:invitro-kz-2 | upload | INVITRO (Инвитро) (103.kz) | Актобе | 284 | 284 |
| 103chain:olimp-12 | upload | КДЛ ОЛИМП (103.kz) | Астана | 282 | 282 |
| 103chain:olimp-13 | upload | КДЛ ОЛИМП (103.kz) | Астана | 282 | 282 |
| 103chain:olimp-14 | upload | КДЛ ОЛИМП (103.kz) | Астана | 282 | 282 |
| 103chain:olimp-30 | upload | КДЛ ОЛИМП (103.kz) | Караганда | 282 | 282 |
| 103chain:olimp-31 | upload | КДЛ ОЛИМП (103.kz) | Караганда | 282 | 282 |
| 103chain:olimp-32 | upload | КДЛ ОЛИМП (103.kz) | Караганда | 282 | 282 |
| 103chain:olimp-41 | upload | КДЛ ОЛИМП (103.kz) | Шымкент | 282 | 282 |
| 103chain:invitro-17 | upload | INVITRO (ИНВИТРО) (103.kz) | Шымкент | 284 | 284 |
| 103chain:invitro-18 | upload | INVITRO (ИНВИТРО) (103.kz) | Шымкент | 284 | 284 |
| 103chain:invitro-26 | upload | INVITRO (ИНВИТРО) (103.kz) | Семей | 284 | 284 |
| 103chain:invitro-27 | upload | INVITRO (ИНВИТРО) (103.kz) | Павлодар | 284 | 284 |
| 103chain:invitro-31 | upload | INVITRO (ИНВИТРО) (103.kz) | Актау | 284 | 284 |
| 103chain:invitro-32 | upload | INVITRO (ИНВИТРО) (103.kz) | Атырау | 284 | 284 |
| 103chain:olimp-58 | upload | КДЛ ОЛИМП (103.kz) | Актау | 282 | 282 |
| 103chain:olimp-60 | upload | КДЛ ОЛИМП (103.kz) | Актау | 282 | 282 |
| 103chain:olimp-63 | upload | КДЛ ОЛИМП (103.kz) | Атырау | 285 | 285 |
| 103chain:olimp-65 | upload | КДЛ ОЛИМП (103.kz) | Атырау | 279 | 279 |
| 103chain:olimp-113 | upload | КДЛ ОЛИМП (103.kz) | Семей | 282 | 282 |
| 103chain:olimp-114 | upload | КДЛ ОЛИМП (103.kz) | Семей | 282 | 282 |
| 103chain:invitro22 | upload | INVITRO (ИНВИТРО) (103.kz) | Талдыкорган | 284 | 284 |
| 103chain:invitro24 | upload | INVITRO (ИНВИТРО) (103.kz) | Усть-Каменогорск | 284 | 284 |
| 103chain:genom-kst | upload | Геном (103.kz) | Костанай | 33 | 28 |
| 103chain:dnk-klinika | upload | ДНК клиника (103.kz) | Костанай | 299 | 264 |
| 103chain:gemotest-47 | upload | Гемотест (103.kz) | Тараз | 300 | 300 |
| 103chain:gemotest-48 | upload | Гемотест (103.kz) | Тараз | 300 | 300 |
| 103chain:gemotest-46 | upload | Гемотест (103.kz) | Тараз | 300 | 300 |
| 103chain:helix-pavlodar | upload | Helix (Хеликс) (103.kz) | Павлодар | 300 | 300 |
| 103.kz/chains | upload | 33 филиалов | 13 городов | 33 | — |

## Соблюдение правил ТЗ §8
- robots.txt соблюдается единым шлюзом `ingestion/robots.py` (Protego) — все GET через `polite_get`.
- crawl-delay пер-хост (не создаём чрезмерную нагрузку).
- Собираются только публичные прайсы; персональные данные не собираются.

_Прим.: invitro/doq/2gis отдают данные через JS/SPA-API, olymp/helix/medel/mck недоступны статикой с этого сервера — для них в `web_scraper` есть адаптеры, подключаемые по доступности (вкл. Playwright для SPA)._
