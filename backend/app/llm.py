"""Единый доступ к LLM (OpenAI-совместимый): AlemLLM / Groq.

Провайдер выбирается через settings.chat_provider. Используется и чат-помощником,
и LLM-шагом нормализатора. Tool-calling не применяем (AlemLLM не держит).
"""
from __future__ import annotations

import json
import re

import httpx

from .config import settings


def _endpoint() -> tuple[str, str, str]:
    """(base_url, api_key, model) активного провайдера."""
    if settings.chat_provider == "alem":
        return settings.alem_base_url, settings.alem_api_key, settings.alem_model
    return "https://api.groq.com/openai/v1", settings.groq_api_key, settings.groq_model


def has_key() -> bool:
    return bool(_endpoint()[1])


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 700) -> str:
    """Чат-комплишн активного провайдера. Бросает при сетевой/HTTP-ошибке."""
    base, key, model = _endpoint()
    resp = httpx.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or ""


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
        "max_tokens": max_tokens,
    }
    if settings.chat_provider == "groq":
        body["response_format"] = {"type": "json_object"}
    try:
        resp = httpx.post(
            f"{base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=60.0,
        )
        resp.raise_for_status()
        return parse_json_lenient(resp.json()["choices"][0]["message"]["content"])
    except Exception:
        return None
