"""Соблюдение robots.txt и вежливость автосбора (② pull).

ТЗ: «Нужно соблюдать robots.txt целевых сайтов». Этот модуль — ЕДИНЫЙ шлюз, через
который обязаны идти все сетевые GET парсера. Он:

  • качает и кэширует `robots.txt` хоста (RobotFileParser, TTL из настроек);
  • до запроса проверяет `can_fetch(url)` — запрещённый путь не скачивается
    (поднимается `RobotsDisallowed`, позиция не теряется — обрабатывается выше);
  • соблюдает `Crawl-delay` (или дефолт) пер-хост — не бомбим сайт параллельно.

Политика по доступности robots.txt (как принято у краулеров):
  • 2xx — применяем правила; 4xx/нет файла — считаем «всё разрешено»
    (у большинства клиник РК robots.txt нет — блокировать их некорректно);
  • 5xx/сетевая ошибка при настройке `robots_strict_on_error` — лучше не качать.

Тестируемость: `seed_robots(host, text)` сеет правила без сети; `reset()` чистит кэш.
"""
from __future__ import annotations

import threading
import time
from urllib.parse import urlparse, urlunparse

import httpx

from ..config import settings

# Protego (Scrapy) реализует ВЕСЬ Google-спек robots: `*` и `$` в путях,
# crawl-delay, адресные User-agent. Стандартный urllib.robotparser молча
# НЕ обрабатывает wildcard'ы (`/appointments/*`, `/*results/`) — а именно их
# используют kdlolymp.kz/doq.kz, поэтому он бы недоблокировал. Fallback на
# stdlib, если пакет недоступен (graceful, как у семантики).
try:
    from protego import Protego  # type: ignore
    _HAS_PROTEGO = True
except Exception:  # pragma: no cover
    from urllib import robotparser as _robotparser
    _HAS_PROTEGO = False


class _Rules:
    """Единый интерфейс поверх Protego или stdlib RobotFileParser."""

    def __init__(self, impl):
        self._impl = impl

    @classmethod
    def parse(cls, text: str, base_url: str) -> "_Rules":
        if _HAS_PROTEGO:
            return cls(Protego.parse(text))
        rp = _robotparser.RobotFileParser()
        rp.set_url(_robots_url(base_url))
        rp.parse(text.splitlines())
        return cls(rp)

    def can_fetch(self, ua: str, url: str) -> bool:
        if _HAS_PROTEGO:
            return self._impl.can_fetch(url, ua)
        return self._impl.can_fetch(ua, url)

    def crawl_delay(self, ua: str):
        try:
            return self._impl.crawl_delay(ua)
        except Exception:
            return None


class RobotsDisallowed(Exception):
    """robots.txt целевого сайта запрещает скачивание этого пути."""

    def __init__(self, url: str):
        self.url = url
        super().__init__(f"robots.txt запрещает доступ: {url}")


# host -> (_Rules | None, fetched_monotonic). None = robots недоступен → allow-all.
_cache: dict[str, tuple["_Rules | None", float]] = {}
# host -> монотонное время последнего запроса (для crawl-delay)
_last_fetch: dict[str, float] = {}
_lock = threading.Lock()


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _robots_url(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme or "https", p.netloc, "/robots.txt", "", "", ""))


def seed_robots(host: str, text: str) -> None:
    """Засеять правила robots.txt для хоста без сети (для тестов/демо)."""
    host = host.lower().removeprefix("www.")
    rp = _Rules.parse(text, f"https://{host}/")
    with _lock:
        _cache[host] = (rp, time.monotonic())


def reset() -> None:
    with _lock:
        _cache.clear()
        _last_fetch.clear()


def _fetch_robots(host: str) -> "_Rules | None":
    """Скачать robots.txt хоста. None → файла нет/4xx → разрешено всё."""
    url = f"https://{host}/robots.txt"
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": settings.scrape_user_agent},
            timeout=min(settings.scrape_timeout, 10.0),
            follow_redirects=True,
            verify=False,
        )
    except Exception:
        # Сетевая ошибка/таймаут — не знаем правил. По умолчанию не блокируем
        # (иначе временный сбой robots останавливает весь автосбор).
        return None
    if resp.status_code >= 500:
        return None
    if 400 <= resp.status_code < 500:
        return None  # robots.txt нет → краулерам разрешено всё
    return _Rules.parse(resp.text, url)


def _parser_for(url: str) -> "_Rules | None":
    host = _host(url)
    now = time.monotonic()
    with _lock:
        cached = _cache.get(host)
        if cached and (now - cached[1]) < settings.robots_cache_ttl:
            return cached[0]
    rp = _fetch_robots(host)  # сеть вне локов
    with _lock:
        _cache[host] = (rp, time.monotonic())
    return rp


def can_fetch(url: str, user_agent: str | None = None) -> bool:
    """Разрешает ли robots.txt хоста скачивать этот URL нашему агенту."""
    if not settings.respect_robots:
        return True
    rp = _parser_for(url)
    if rp is None:
        return True
    return rp.can_fetch(user_agent or settings.scrape_user_agent, url)


def crawl_delay(url: str, user_agent: str | None = None) -> float:
    """Crawl-delay из robots.txt (или дефолт settings.scrape_crawl_delay)."""
    default = settings.scrape_crawl_delay
    if not settings.respect_robots:
        return default
    rp = _parser_for(url)
    if rp is None:
        return default
    try:
        d = rp.crawl_delay(user_agent or settings.scrape_user_agent)
    except Exception:
        d = None
    return max(float(d), default) if d is not None else default


def _throttle(url: str) -> None:
    """Подождать crawl-delay с прошлого запроса к этому хосту."""
    host = _host(url)
    delay = crawl_delay(url)
    with _lock:
        last = _last_fetch.get(host)
        now = time.monotonic()
        wait = 0.0 if last is None else max(0.0, delay - (now - last))
        # резервируем слот заранее, чтобы параллельные потоки не обошли delay
        _last_fetch[host] = now + wait
    if wait > 0:
        time.sleep(wait)


def polite_get(url: str, *, timeout: float | None = None,
               headers: dict | None = None, client: httpx.Client | None = None,
               **kwargs) -> httpx.Response:
    """Единственный разрешённый способ GET в парсере: проверяет robots.txt,
    соблюдает crawl-delay, ставит наш User-Agent. Бросает RobotsDisallowed,
    если путь запрещён. `client` — переиспользовать сессию (cookies)."""
    if not can_fetch(url):
        raise RobotsDisallowed(url)
    _throttle(url)
    hdrs = {"User-Agent": settings.scrape_user_agent, **(headers or {})}
    timeout = timeout or settings.scrape_timeout
    if client is not None:
        return client.get(url, headers=hdrs, timeout=timeout, **kwargs)
    with httpx.Client(headers=hdrs, timeout=timeout, follow_redirects=True,
                      verify=False) as c:
        return c.get(url, **kwargs)
