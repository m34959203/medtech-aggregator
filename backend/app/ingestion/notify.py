"""Уведомления подписчиков (§3.4) через WhatsApp-туннель (wa-gateway).

Синхронный httpx-вызов (используется из планировщика, вне async-контекста).
Грациозная деградация: туннель не настроен/недоступен → False, без исключения.
Подписчик дал согласие, оставив номер → bypassGates=true (минуем антибан-гейт
«писал первым»), но дневной лимит туннеля по-прежнему действует.
"""
from __future__ import annotations

import httpx

from ..config import settings


def wa_configured() -> bool:
    return bool(settings.wa_gateway_url and settings.wa_api_secret)


def send_whatsapp(phone: str, message: str) -> bool:
    """Отправить сообщение через туннель. True — принято туннелем, иначе False."""
    if not wa_configured() or not phone or not message:
        return False
    base = settings.wa_gateway_url.rstrip("/")
    try:
        r = httpx.post(
            f"{base}/api/send",
            headers={"X-API-Secret": settings.wa_api_secret},
            json={"phone": phone, "message": message, "bypassGates": True},
            timeout=30.0,
        )
        return r.status_code < 400
    except Exception:
        return False
