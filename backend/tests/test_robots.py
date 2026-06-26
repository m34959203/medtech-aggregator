"""Соблюдение robots.txt (ТЗ §2.1: «Нужно соблюдать robots.txt целевых сайтов»).

Офлайн: правила сеются текстом через robots.seed_robots — без сети.
"""
import time

import pytest

from app.ingestion import robots, web_scraper


@pytest.fixture(autouse=True)
def _clean_robots(monkeypatch):
    monkeypatch.setattr("app.config.settings.respect_robots", True, raising=False)
    monkeypatch.setattr("app.config.settings.scrape_crawl_delay", 0.0, raising=False)
    robots.reset()
    yield
    robots.reset()


def test_disallow_blocks_path():
    robots.seed_robots("clinic.kz", "User-agent: *\nDisallow: /admin/\n")
    assert robots.can_fetch("https://clinic.kz/price/") is True
    assert robots.can_fetch("https://clinic.kz/admin/secret") is False


def test_real_doq_rule_appointments_disallowed():
    # как в реальном doq.kz/robots.txt
    robots.seed_robots("doq.kz", "User-agent: *\nDisallow: /appointments/*\n")
    assert robots.can_fetch("https://doq.kz/clinics/") is True
    assert robots.can_fetch("https://doq.kz/appointments/123") is False


def test_targeted_user_agent_rule():
    txt = ("User-agent: MedtechAggregatorBot\nDisallow: /\n\n"
           "User-agent: *\nDisallow:\n")
    robots.seed_robots("strict.kz", txt)
    # правило адресовано именно нашему боту → всё запрещено
    assert robots.can_fetch("https://strict.kz/any") is False


def test_no_robots_means_allow_all():
    # хост не засеян и сети нет в тесте → _fetch_robots вернёт None → allow
    # (эмулируем: подменяем фетч на None)
    robots._cache.clear()
    import app.ingestion.robots as r
    orig = r._fetch_robots
    r._fetch_robots = lambda host: None
    try:
        assert robots.can_fetch("https://no-robots-clinic.kz/price") is True
    finally:
        r._fetch_robots = orig


def test_respect_robots_off_bypasses(monkeypatch):
    robots.seed_robots("clinic.kz", "User-agent: *\nDisallow: /\n")
    assert robots.can_fetch("https://clinic.kz/x") is False
    monkeypatch.setattr("app.config.settings.respect_robots", False, raising=False)
    assert robots.can_fetch("https://clinic.kz/x") is True


def test_crawl_delay_from_robots(monkeypatch):
    robots.seed_robots("slow.kz", "User-agent: *\nCrawl-delay: 3\nDisallow:\n")
    assert robots.crawl_delay("https://slow.kz/a") == 3.0
    # дефолт, если в robots не задан
    robots.seed_robots("plain.kz", "User-agent: *\nDisallow:\n")
    monkeypatch.setattr("app.config.settings.scrape_crawl_delay", 1.5, raising=False)
    assert robots.crawl_delay("https://plain.kz/a") == 1.5


def test_throttle_enforces_delay(monkeypatch):
    robots.seed_robots("th.kz", "User-agent: *\nDisallow:\n")
    monkeypatch.setattr("app.config.settings.scrape_crawl_delay", 0.2, raising=False)
    robots._last_fetch.clear()
    t0 = time.monotonic()
    robots._throttle("https://th.kz/a")  # первый — без ожидания
    robots._throttle("https://th.kz/b")  # второй — ждёт ~0.2с
    assert time.monotonic() - t0 >= 0.18


def test_polite_get_raises_on_disallow():
    robots.seed_robots("blocked.kz", "User-agent: *\nDisallow: /\n")
    with pytest.raises(robots.RobotsDisallowed):
        robots.polite_get("https://blocked.kz/price")


def test_scrape_url_propagates_robots_disallowed():
    robots.seed_robots("blocked.kz", "User-agent: *\nDisallow: /\n")
    with pytest.raises(web_scraper.RobotsDisallowed):
        web_scraper.scrape_url("https://blocked.kz/price")
