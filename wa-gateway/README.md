# wa-gateway (medtech)

WhatsApp-туннель на Baileys как отдельный микросервис. Хранит auth-state в
Postgres (`whatsapp_sessions`), логирует входящие/исходящие в `whatsapp_messages`,
форвардит входящие в основное приложение через webhook. Таблицы создаёт сам
(`ensureSchema` на старте) — туннель самодостаточен.

Антибан: serial-очередь отправки, «печатает» (humanize presence), дневной лимит,
по умолчанию отправка ТОЛЬКО в чаты, где клиент написал первым
(`WA_REQUIRE_CLIENT_INITIATED`). 405-фикс: при недоступности
`fetchLatestBaileysVersion` (таймаут/блок raw.githubusercontent) — fallback-версия.

## Переменные окружения

| Переменная | Обяз. | Дефолт | Описание |
|---|---|---|---|
| `DATABASE_URL` | да | — | Postgres (та же БД, что у приложения). |
| `WA_API_SECRET` | да | `change-me` | Секрет в заголовке `X-API-Secret` на всех `/api/*`. |
| `PORT` | нет | `3200` | Порт HTTP. |
| `WA_INBOUND_WEBHOOK_URL` | нет | — | Куда POST'ить входящие (fire-and-forget). |
| `WA_INBOUND_WEBHOOK_SECRET` | нет | — | Заголовок `X-Webhook-Secret` на входящем webhook. |
| `WA_HUMANIZE` / `WA_HUMANIZE_MIN_MS` / `WA_HUMANIZE_MAX_MS` | нет | `true`/3000/15000 | Имитация набора. |
| `WA_DAILY_LIMIT` | нет | `100` | Лимит исходящих за 24ч. |
| `WA_REQUIRE_CLIENT_INITIATED` | нет | `true` | Отправлять только тем, кто написал первым. |
| `LOG_LEVEL` | нет | `info` | pino. |

## Endpoints (все `/api/*` требуют `X-API-Secret`)

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` | Liveness (без auth). |
| GET | `/api/status` | Статус соединения, номер, QR (data URL). |
| POST | `/api/connect` | Старт сессии / выдать QR. |
| POST | `/api/disconnect` | Закрыть сокет (сессия сохраняется). |
| POST | `/api/logout` | Выйти и стереть сессию. |
| POST | `/api/send` | `{ phone, message, leadId?, bypassGates? }`. |
| POST | `/api/check-number` | `{ phone }` — есть ли номер в WA. |
| GET | `/api/limits` | Лимиты/очередь. |

## Привязка (pairing)

1. `POST /api/connect` → GET `/api/status` пока `qr_ready` → отсканировать QR
   телефоном (WhatsApp → Связанные устройства). После — статус `connected`.
2. В medtech это делается через admin-проксю `/api/wa/*` (см. `routers/wa.py`).

## Локальная разработка

```bash
npm install
npm run dev          # tsx watch
# или
npm run build && npm start
```
