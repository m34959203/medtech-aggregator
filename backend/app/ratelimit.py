"""Лёгкий in-memory rate-limiter (анти-абуз публичных POST и логина).

Скользящее окно per-IP, без внешних зависимостей. Для нескольких воркеров/реплик
точность приблизительная (состояние на процесс) — это первый слой; на масштаб
выносится в Redis. За CF/Next-прокси реальный IP берём из заголовков.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from .config import settings


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def hit(self, key: str) -> tuple[bool, int]:
        """Регистрирует обращение. → (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            dq = self._hits.setdefault(key, deque())
            cutoff = now - self.window
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= self.limit:
                return False, int(self.window - (now - dq[0])) + 1
            dq.append(now)
            # периодическая чистка пустых ключей, чтобы не течь по памяти
            self._calls += 1
            if self._calls % 500 == 0:
                for k in [k for k, d in self._hits.items() if not d or d[-1] <= cutoff]:
                    self._hits.pop(k, None)
            return True, 0


# Реестр лимитеров по имени — чтобы тесты могли настраивать/сбрасывать.
LIMITERS: dict[str, RateLimiter] = {}


def rate_limit(name: str, limit: int, window: float = 60.0):
    """Фабрика FastAPI-зависимости: не более `limit` запросов за `window` секунд на IP."""
    limiter = LIMITERS.setdefault(name, RateLimiter(limit, window))

    def _dep(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        ok, retry = limiter.hit(f"{name}:{client_ip(request)}")
        if not ok:
            raise HTTPException(
                429, "Слишком много запросов. Попробуйте позже.",
                headers={"Retry-After": str(retry)},
            )

    return _dep
