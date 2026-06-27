"""WhatsApp-туннель: тонкая проксь от приложения к микросервису wa-gateway.

Секрет туннеля (`WA_API_SECRET`) живёт ТОЛЬКО на бэкенде — фронт/админ ходят сюда,
а сюда — за `require_admin`. Входящие сообщения туннель шлёт на `/api/wa/inbound`
с заголовком `X-Webhook-Secret` (проверяем). Если туннель не настроен — 503, не падаем.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..auth import require_admin
from ..config import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wa", tags=["whatsapp"])


def _gateway() -> tuple[str, dict]:
    if not settings.wa_gateway_url or not settings.wa_api_secret:
        raise HTTPException(503, "WhatsApp-туннель не настроен (WA_GATEWAY_URL/WA_API_SECRET)")
    return settings.wa_gateway_url.rstrip("/"), {"X-API-Secret": settings.wa_api_secret}


async def _proxy(method: str, path: str, json: dict | None = None) -> dict:
    base, headers = _gateway()
    try:
        async with httpx.AsyncClient(timeout=30.0) as cli:
            r = await cli.request(method, f"{base}{path}", headers=headers, json=json)
    except Exception as e:  # туннель недоступен по сети
        raise HTTPException(502, f"WA-туннель недоступен: {str(e)[:80]}")
    if r.status_code >= 400:
        # пробрасываем причину туннеля (лимит/не подключён/клиент не писал первым)
        detail = (r.json().get("error") if "application/json" in r.headers.get("content-type", "") else r.text)
        raise HTTPException(r.status_code, detail or "WA-туннель вернул ошибку")
    return r.json()


@router.get("/status")
async def wa_status(_: bool = Depends(require_admin)):
    """Статус туннеля + QR (data URL) для привязки телефона."""
    return await _proxy("GET", "/api/status")


@router.post("/connect")
async def wa_connect(_: bool = Depends(require_admin)):
    """Запустить сессию (далее опрашивать /status до qr_ready → отсканировать QR)."""
    return await _proxy("POST", "/api/connect")


@router.post("/disconnect")
async def wa_disconnect(_: bool = Depends(require_admin)):
    return await _proxy("POST", "/api/disconnect")


@router.post("/logout")
async def wa_logout(_: bool = Depends(require_admin)):
    """Выйти из WhatsApp и стереть сохранённую сессию (потребуется новая привязка)."""
    return await _proxy("POST", "/api/logout")


@router.get("/limits")
async def wa_limits(_: bool = Depends(require_admin)):
    return await _proxy("GET", "/api/limits")


@router.post("/send")
async def wa_send(payload: dict, _: bool = Depends(require_admin)):
    """Отправить сообщение через туннель. Body: {phone, message, leadId?, bypassGates?}."""
    phone = (payload or {}).get("phone")
    message = (payload or {}).get("message")
    if not phone or not message:
        raise HTTPException(400, "phone и message обязательны")
    body = {"phone": phone, "message": message}
    if payload.get("leadId") is not None:
        body["leadId"] = payload["leadId"]
    if payload.get("bypassGates") is not None:
        body["bypassGates"] = bool(payload["bypassGates"])
    return await _proxy("POST", "/api/send", json=body)


@router.post("/share-location")
async def wa_share_location(payload: dict):
    """ПУБЛИЧНО: отправить координаты клиники на WhatsApp пользователя через наш шлюз.

    Транзакционная отправка по явному запросу пользователя (он сам ввёл свой номер,
    чтобы получить адрес) — обходит гейт «клиент написал первым», но дневной лимит
    шлюза остаётся как анти-бан-подушка. Используется кнопкой карты на ПК (на мобиле
    фронт открывает нативный WhatsApp через wa.me).
    """
    p = payload or {}
    phone = "".join(ch for ch in str(p.get("phone", "")) if ch.isdigit())
    if len(phone) < 10:
        raise HTTPException(400, "Введите номер с кодом страны")
    name = (p.get("clinic_name") or "клиника").strip()
    address = (p.get("address") or "").strip()
    try:
        lat = float(p["lat"]); lng = float(p["lng"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, "Неверные координаты")
    lines = [f"📍 {name}"]
    if address:
        lines.append(address)
    lines += [
        f"Координаты: {lat:.6f}, {lng:.6f}",
        f"На карте: https://yandex.ru/maps/?pt={lng:.6f},{lat:.6f}&z=17&l=map",
        f"Маршрут: https://yandex.ru/maps/?rtext=~{lat:.6f},{lng:.6f}&rtt=auto",
    ]
    message = "\n".join(lines)
    return await _proxy("POST", "/api/send",
                        json={"phone": phone, "message": message, "transactional": True})


@router.post("/inbound")
async def wa_inbound(payload: dict, request: Request,
                     x_webhook_secret: str | None = Header(default=None)):
    """Приём входящих от туннеля (fire-and-forget). Аутентификация — по секрету.

    Туннель уже залогировал сообщение в whatsapp_messages; здесь — точка для
    бизнес-логики (лид/чат-автоответ). Пока: проверка секрета + структурный лог.
    """
    if settings.wa_inbound_webhook_secret and x_webhook_secret != settings.wa_inbound_webhook_secret:
        raise HTTPException(401, "bad webhook secret")
    log.info("WA inbound: phone=%s msg=%r", (payload or {}).get("phone"),
             str((payload or {}).get("message"))[:120])
    # TODO: маршрутизация во входящий лид / авто-ответ ассистента.
    return {"ok": True}
