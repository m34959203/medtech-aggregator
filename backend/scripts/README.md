# scripts/ — одноразовые скрипты обслуживания данных

Утилиты, запускавшиеся вручную при сопровождении прод-БД (не часть рантайма API).
Все идемпотентны и по умолчанию работают в режиме dry-run (запись — с `--apply`).

| Скрипт | Назначение |
|---|---|
| `enrich_contacts.py` | дозаполнение сайт/часы/рейтинг клиник из 103.kz JSON-LD |
| `generate_descriptions.py` | генерация кратких описаний услуг (Gemini, батчами) |
| `merge_glucose.py` | слияние дублей-канонов «Глюкоза (кровь)» → «Глюкоза (в крови)» |
| `prune_orphan_services.py` | удаление услуг-сирот (без единой цены) |
| `backfill_geocode.py` | геокодирование адресов клиник |
| `remap_uuid.py` | разовый перенос int→uuid идентификаторов |

Запуск (из каталога `backend/`): `PYTHONPATH=. python scripts/<name>.py [--apply]`
(в контейнере: `docker exec -w /app -e PYTHONPATH=/app medtech-backend python scripts/<name>.py --apply`).

`generate_kk.py` — перевод каталога на казахский (name_kk/description_kk).
