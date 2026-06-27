"""Единый доступ к LLM (OpenAI-совместимый): Gemini / AlemLLM / Groq.

Провайдер выбирается через settings.chat_provider. Используется и чат-помощником,
и LLM-шагом нормализатора. Tool-calling не применяем (AlemLLM не держит).
Gemini — через OpenAI-совместимый эндпоинт (надёжнее на reasoning/JSON).
"""
from __future__ import annotations

import json
import re
import threading

import httpx

from .config import settings

# Провайдеры с поддержкой строгого JSON (response_format=json_object).
_JSON_PROVIDERS = {"gemini", "groq"}

# Vertex AI: SA-учётка кэшируется, токен (TTL ~1ч) обновляется при истечении.
_vertex_creds = None
_vertex_lock = threading.Lock()


def _vertex_token() -> str:
    """Свежий OAuth-токен из service-account для Vertex (ленивая загрузка + refresh)."""
    global _vertex_creds
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    with _vertex_lock:
        if _vertex_creds is None:
            _vertex_creds = service_account.Credentials.from_service_account_file(
                settings.google_application_credentials,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        if not _vertex_creds.valid:
            _vertex_creds.refresh(Request())
        return _vertex_creds.token


def _endpoint() -> tuple[str, str, str]:
    """(base_url, bearer, model) активного провайдера. Vertex минтит SA-токен."""
    p = settings.chat_provider
    if p == "gemini":
        if settings.gemini_is_vertex:
            loc, proj = settings.gcp_location, settings.gcp_project
            base = (f"https://{loc}-aiplatform.googleapis.com/v1beta1/projects/{proj}"
                    f"/locations/{loc}/endpoints/openapi")
            return base, _vertex_token(), f"google/{settings.gemini_model}"
        return settings.gemini_base_url, settings.gemini_api_key, settings.gemini_model
    if p == "alem":
        return settings.alem_base_url, settings.alem_api_key, settings.alem_model
    return "https://api.groq.com/openai/v1", settings.groq_api_key, settings.groq_model


def has_key() -> bool:
    # Для Vertex не минтим токен ради проверки — достаточно наличия SA+проекта.
    if settings.chat_provider == "gemini" and settings.gemini_is_vertex:
        return True
    return bool(_endpoint()[1])


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 700) -> str:
    """Чат-комплишн активного провайдера. Бросает при сетевой/HTTP-ошибке."""
    base, key, model = _endpoint()
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": _budget(max_tokens)}
    _apply_gemini(body)
    resp = httpx.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=body,
        timeout=90.0,
    )
    resp.raise_for_status()
    return _content(resp.json())


def _apply_gemini(body: dict) -> None:
    """Для Gemini 2.5 ОТКЛЮЧАЕМ thinking (thinking_budget=0). На задачах нормализатора
    (decide/verify) «размышление» жрёт 1000–1400 токенов ДО ответа → при обычном
    лимите ответ обрезается (finish_reason=length) и теряется. Без thinking — быстро,
    дёшево, надёжно; качество для структурной классификации достаточное."""
    if settings.chat_provider == "gemini":
        body["google"] = {"thinking_config": {"thinking_budget": 0}}


def _budget(max_tokens: int) -> int:
    """Скромный пол для Gemini (thinking отключён в _apply_gemini, но оставляем
    запас на длинный reason/JSON)."""
    if settings.chat_provider == "gemini":
        return max(max_tokens, 512)
    return max_tokens


def _content(data: dict) -> str:
    """Безопасно достать content. Vertex отдаёт ошибки списком [{...}]; усечённый
    thinking-ответ — choice без message. В обоих случаях возвращаем ''."""
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    return (choices[0].get("message") or {}).get("content") or ""


def parse_json_lenient(text: str) -> dict | None:
    """Достаёт первый JSON-объект из ответа (терпит ```-фенсы и пояснения)."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def json_completion(prompt: str, max_tokens: int = 300) -> dict | None:
    """JSON-ответ от активного провайдера. None — если нет ключа/ошибка/невалидно.

    Для Groq просим строгий json_object; AlemLLM формат не поддерживает —
    парсим лениво (он отдаёт JSON в ```-фенсах).
    """
    base, key, model = _endpoint()
    if not key:
        return None
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": _budget(max_tokens),
    }
    if settings.chat_provider in _JSON_PROVIDERS:
        body["response_format"] = {"type": "json_object"}
    _apply_gemini(body)
    try:
        resp = httpx.post(
            f"{base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=90.0,
        )
        resp.raise_for_status()
        return parse_json_lenient(_content(resp.json()))
    except Exception:
        return None
