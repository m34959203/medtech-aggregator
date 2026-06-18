import os
import sys

# делаем пакет app импортируемым при запуске pytest из каталога backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(autouse=True)
def _no_llm_in_tests(monkeypatch):
    """Тесты детерминированы и offline: нормализатор/чат не ходят в LLM.

    Без этого результат зависит от наличия GROQ/ALEM-ключа в окружении (локально
    ключ есть → сетевой вызов и conf=1.0 у новых услуг; в CI ключа нет → fuzzy).
    """
    monkeypatch.setattr("app.llm.json_completion", lambda *a, **k: None)
    monkeypatch.setattr("app.config.settings.groq_api_key", "", raising=False)
    monkeypatch.setattr("app.config.settings.alem_api_key", "", raising=False)
