"""Авторизация админ-зоны (passwordless): доступ по секретному токену через cookie.

Токен задаётся в ADMIN_TOKEN. Пусто → админ-роуты ЗАКРЫТЫ (fail-closed), а не
открыты всем. Токен принимается из httpOnly-cookie `mt_admin` или заголовка
`Authorization: Bearer <token>` (для API-логина без формы).
"""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, Response

from .config import settings

COOKIE_NAME = "mt_admin"
_MAX_AGE = 60 * 60 * 24 * 30  # 30 дней


def admin_configured() -> bool:
    return bool(settings.admin_token)


def token_from_request(request: Request) -> str | None:
    tok = request.cookies.get(COOKIE_NAME)
    if tok:
        return tok
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def check_admin(token: str | None) -> bool:
    if not settings.admin_token or not token:
        return False
    return secrets.compare_digest(token, settings.admin_token)


def require_admin(request: Request) -> bool:
    """Зависимость FastAPI: пускает только с валидным админ-токеном."""
    if not settings.admin_token:
        raise HTTPException(503, "Админ-доступ не настроен (ADMIN_TOKEN не задан).")
    if not check_admin(token_from_request(request)):
        raise HTTPException(401, "Требуется авторизация администратора.")
    return True


def set_admin_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token, max_age=_MAX_AGE, httponly=True,
        samesite="lax", secure=settings.cookie_secure, path="/",
    )


def clear_admin_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
