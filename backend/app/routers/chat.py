"""Чат-помощник пациента — диалоговый поиск по витрине цен.

Помощник = НАДСТРОЙКА над агрегатором, а не отдельный «всезнающий» LLM:
сначала ПРИНУДИТЕЛЬНО ищем по тому же нормализованному справочнику, что и
витрина, и вкладываем результаты в контекст модели (retrieval-injection).
Поэтому бот не выдумывает цены/клиники — отвечает строго по данным.

Провайдер OpenAI-совместимый и настраивается (LLM_PROVIDER): AlemLLM (KZ, по
умолчанию при наличии ключа) или Groq. Tool-calling НЕ используется — AlemLLM
его не поддерживает, а retrieval-injection работает с любым провайдером.

Деградация: без ключа провайдера (или при ошибке сети) endpoint отвечает
детерминированным поиском-сводкой. Демо работает всегда — важно для жюри.
"""
from __future__ import annotations

import json
from datetime import date

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from rapidfuzz import fuzz
from sqlalchemy import distinct
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..ingestion.normalizer import _clean
from ..models import Clinic, ServiceCatalog
from .aggregator import _build_comparison

router = APIRouter(prefix="/api", tags=["assistant"])


# --- Контракт ---
class ChatMessage(BaseModel):
    role: str  # user / assistant
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatOffer(BaseModel):
    """Предложение для карточек в виджете (фронт рендерит ссылку/телефон)."""
    service: str
    clinic_name: str
    city: str
    district: str
    address: str
    phone: str
    price: float
    currency: str
    is_cheapest: bool


class ChatResponse(BaseModel):
    reply: str
    offers: list[ChatOffer] = []
    grounded: bool  # ответ построен на реальных данных витрины
    llm: bool       # отвечал LLM (False = детерминированный фолбэк)


# --- Поиск по справочнику (общая воронка с витриной) ---
def _rank_services(db: Session, query: str, limit: int = 3) -> list[ServiceCatalog]:
    """Фаззи-подбор услуг справочника под свободный запрос пользователя."""
    q = _clean(query)
    if not q:
        return []
    scored: list[tuple[float, ServiceCatalog]] = []
    for svc in db.query(ServiceCatalog).all():
        keys = [svc.canonical_name] + [str(s) for s in (svc.synonyms or [])]
        best = max((fuzz.token_set_ratio(q, _clean(k)) for k in keys), default=0.0)
        if any(q in _clean(k) for k in keys):  # прямое вхождение — приоритет
            best = max(best, 90.0)
        if best >= 55:
            scored.append((best, svc))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [svc for _, svc in scored[:limit]]


def _search_offers(
    db: Session,
    query: str,
    city: str | None = None,
    max_price: float | None = None,
    sort: str = "price_asc",
    limit_services: int = 3,
    per_service: int = 6,
):
    """Возвращает (offers для виджета, summaries для контекста LLM)."""
    offers: list[ChatOffer] = []
    summaries = []
    for svc in _rank_services(db, query, limit_services):
        cmp = _build_comparison(db, svc, city, max_price, sort)
        if cmp.offers_count == 0:
            continue
        summaries.append(cmp)
        cheapest = cmp.min_price
        for o in cmp.offers[:per_service]:
            offers.append(
                ChatOffer(
                    service=cmp.canonical_name,
                    clinic_name=o.clinic_name,
                    city=o.city,
                    district=o.district,
                    address=o.address,
                    phone=o.phone,
                    price=o.price,
                    currency=o.currency,
                    is_cheapest=(o.price == cheapest),
                )
            )
    return offers, summaries


def _dedupe(offers: list[ChatOffer]) -> list[ChatOffer]:
    seen, out = set(), []
    for o in offers:
        key = (o.service, o.clinic_name, o.price)
        if key not in seen:
            seen.add(key)
            out.append(o)
    return out


def _summaries_for_llm(summaries) -> dict:
    if not summaries:
        return {"result": "no_matches", "hint": "По этому запросу цен в базе нет."}
    return {
        "results": [
            {
                "service": cmp.canonical_name,
                "category": cmp.category,
                "offers_count": cmp.offers_count,
                "min_price": cmp.min_price,
                "max_price": cmp.max_price,
                "currency": cmp.offers[0].currency if cmp.offers else "KZT",
                "offers": [
                    {
                        "clinic": o.clinic_name,
                        "city": o.city,
                        "district": o.district,
                        "address": o.address,
                        "phone": o.phone,
                        "price": o.price,
                    }
                    for o in cmp.offers[:6]
                ],
            }
            for cmp in summaries
        ]
    }


# --- LLM-путь (retrieval-injection, OpenAI-совместимый: AlemLLM / Groq) ---
# AlemLLM не поддерживает tool-calling (tool_choice=auto отклоняется, named-tool
# падает 500), поэтому используем принудительный retrieval: сами ищем по базе и
# вкладываем результаты в контекст. Паттерн работает с любым провайдером.
_SYSTEM = (
    "Ты — МедЦена, дружелюбный помощник пациента на сайте-агрегаторе цен на "
    "медицинские услуги в Казахстане. Сегодня {today}.\n"
    "Помогаешь найти услугу дешевле, объясняешь где её делают и сравниваешь клиники.\n"
    "Доступные города: {cities}.\n"
    "ПРАВИЛА:\n"
    "- Цены, клиники, адреса и телефоны бери ТОЛЬКО из блока РЕЗУЛЬТАТЫ ПОИСКА ниже. "
    "Никогда ничего не выдумывай и не добавляй клиник, которых там нет.\n"
    "- Отвечай кратко и по-русски, явно называй самую выгодную клинику и цену в тенге.\n"
    "- Если в результатах пусто — честно скажи, что по запросу цен пока нет, и предложи "
    "уточнить название услуги.\n"
    "- Цены справочные: в конце ответа с ценами напомни уточнять стоимость в клинике.\n"
    "- На вопросы не по теме медуслуг вежливо возвращай к теме.\n"
    "Справочник услуг (примеры): {catalog}\n\n"
    "РЕЗУЛЬТАТЫ ПОИСКА ПО БАЗЕ (JSON):\n{results}"
)


def _detect_city(db: Session, text: str) -> str | None:
    """Находит упомянутый в запросе город из числа имеющихся в базе."""
    low = text.lower()
    for (city,) in db.query(distinct(Clinic.city)).all():
        if city and city.lower() in low:
            return city
    return None


def _chat_completion(messages: list[dict]) -> str:
    """Единый OpenAI-совместимый вызов для выбранного провайдера."""
    if settings.chat_provider == "alem":
        base, key, model = settings.alem_base_url, settings.alem_api_key, settings.alem_model
    else:
        base, key, model = "https://api.groq.com/openai/v1", settings.groq_api_key, settings.groq_model
    resp = httpx.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 700},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or ""


def _run_llm(db: Session, messages: list[ChatMessage]):
    user_q = next((m.content for m in reversed(messages) if m.role == "user"), "")
    city = _detect_city(db, user_q)
    offers, summaries = _search_offers(db, user_q, city=city)

    cities = [c[0] for c in db.query(distinct(Clinic.city)).all() if c[0]]
    catalog = [s.canonical_name for s in db.query(ServiceCatalog).all()]
    system = _SYSTEM.format(
        today=date.today().isoformat(),
        cities=", ".join(cities) or "—",
        catalog=", ".join(catalog[:40]) or "—",
        results=json.dumps(_summaries_for_llm(summaries), ensure_ascii=False),
    )
    convo: list[dict] = [{"role": "system", "content": system}]
    convo += [{"role": m.role, "content": m.content} for m in messages]
    text = _chat_completion(convo)
    return text or "Уточните, пожалуйста, какую услугу вы ищете.", offers


def _fallback(db: Session, messages: list[ChatMessage]) -> ChatResponse:
    """Детерминированный ответ без LLM — демо живёт даже без ключа провайдера."""
    user = next((m.content for m in reversed(messages) if m.role == "user"), "")
    offers, summaries = _search_offers(db, user)
    if not summaries:
        return ChatResponse(
            reply=(
                "Я пока не нашёл цен по этому запросу. Попробуйте уточнить название "
                "услуги — например «общий анализ крови» или «УЗИ брюшной полости»."
            ),
            offers=[],
            grounded=False,
            llm=False,
        )
    lines = []
    for cmp in summaries:
        cheap = min(cmp.offers, key=lambda o: o.price)
        loc = f", {cheap.district}" if cheap.district else ""
        lines.append(
            f"• {cmp.canonical_name}: от {cheap.price:.0f} {cheap.currency} — "
            f"{cheap.clinic_name}{loc} (предложений: {cmp.offers_count})"
        )
    reply = (
        "Вот что нашлось по вашему запросу:\n"
        + "\n".join(lines)
        + "\n\nЦены справочные — уточняйте актуальную стоимость в клинике."
    )
    return ChatResponse(reply=reply, offers=_dedupe(offers), grounded=True, llm=False)


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    if not req.messages:
        return ChatResponse(
            reply="Здравствуйте! Я помогу найти медуслугу дешевле. Что ищете?",
            grounded=False,
            llm=False,
        )
    has_key = settings.alem_api_key if settings.chat_provider == "alem" else settings.groq_api_key
    if not has_key:
        return _fallback(db, req.messages)
    try:
        reply, offers = _run_llm(db, req.messages)
        offers = _dedupe(offers)
        return ChatResponse(
            reply=reply or "Уточните, пожалуйста, запрос.",
            offers=offers,
            grounded=bool(offers),
            llm=True,
        )
    except Exception:
        # сеть/квота/ключ — не валим UX, отвечаем детерминированным поиском
        return _fallback(db, req.messages)
