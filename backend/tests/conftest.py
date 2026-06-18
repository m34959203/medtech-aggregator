import os
import sys

# делаем пакет app импортируемым при запуске pytest из каталога backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "real_admin: тестировать реальную админ-авторизацию (без обхода)")


@pytest.fixture(autouse=True)
def _no_llm_in_tests(monkeypatch):
    """Тесты детерминированы и offline: нормализатор/чат не ходят в LLM.

    Без этого результат зависит от наличия GROQ/ALEM-ключа в окружении (локально
    ключ есть → сетевой вызов и conf=1.0 у новых услуг; в CI ключа нет → fuzzy).
    """
    monkeypatch.setattr("app.llm.json_completion", lambda *a, **k: None)
    monkeypatch.setattr("app.config.settings.groq_api_key", "", raising=False)
    monkeypatch.setattr("app.config.settings.alem_api_key", "", raising=False)
    # Rate-limit по умолчанию выключен в тестах (тест лимита включает явно).
    monkeypatch.setattr("app.config.settings.rate_limit_enabled", False, raising=False)


@pytest.fixture(autouse=True)
def _admin_auth(request, monkeypatch):
    """Задаёт тестовый ADMIN_TOKEN и по умолчанию ОБХОДИТ admin-гард (чтобы прежние
    тесты не переписывать). Тесты с маркером real_admin получают реальную проверку.
    """
    monkeypatch.setattr("app.config.settings.admin_token", "test-token", raising=False)
    bypass = request.node.get_closest_marker("real_admin") is None
    if bypass:
        from app.auth import require_admin
        from app.main import app
        app.dependency_overrides[require_admin] = lambda: True
    yield
    if bypass:
        from app.auth import require_admin
        from app.main import app
        app.dependency_overrides.pop(require_admin, None)
