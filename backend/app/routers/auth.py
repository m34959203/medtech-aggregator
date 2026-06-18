"""Логин/логаут админ-зоны (passwordless токен → httpOnly cookie)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..auth import (
    admin_configured,
    check_admin,
    clear_admin_cookie,
    set_admin_cookie,
    token_from_request,
)
from ..config import settings
from ..ratelimit import rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    token: str


@router.post("/login", dependencies=[Depends(rate_limit("login", 10))])
def login(body: LoginIn, response: Response):
    if not settings.admin_token:
        raise HTTPException(503, "Админ-доступ не настроен.")
    if not check_admin(body.token):
        raise HTTPException(401, "Неверный токен доступа.")
    set_admin_cookie(response, body.token)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    clear_admin_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    return {
        "authenticated": check_admin(token_from_request(request)),
        "configured": admin_configured(),
    }
