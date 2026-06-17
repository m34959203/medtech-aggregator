"""Чат-помощник пациента — диалоговый поиск по витрине цен.

Помощник = НАДСТРОЙКА над агрегатором, а не отдельный «всезнающий» LLM:
Groq получает единственный инструмент search_prices, который ходит в тот же
нормализованный справочник, что и витрина сравнения. Поэтому бот не выдумывает
цены/клиники — он отвечает строго по данным.

Деградация: без GROQ_API_KEY (или при ошибке сети) endpoint отвечает
детерминированным поиском-сводкой. Демо работает всегда — важно для жюри.
"""
from __future__ import annotations

import json
from datetime import date

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


# --- LLM-путь (Groq tool-calling) ---
_SYSTEM = (
    "Ты — МедЦена, дружелюбный помощник пациента на сайте-агрегаторе цен на "
    "медицинские услуги в Казахстане. Сегодня {today}.\n"
    "Помогаешь найти услугу дешевле, объясняешь где её делают и сравниваешь клиники.\n"
    "Доступные города: {cities}.\n"
    "ПРАВИЛА:\n"
    "- Цены, клиники, адреса и телефоны бери ТОЛЬКО из результата инструмента "
    "search_prices. Никогда ничего не выдумывай.\n"
    "- Если вопрос про цену/услугу — обязательно вызови search_prices.\n"
    "- Отвечай кратко и по-русски, явно называй самую выгодную клинику и цену в тенге.\n"
    "- Если данных нет — честно скажи об этом и предложи похожие услуги из справочника.\n"
    "- Цены справочные: в конце ответа с ценами напомни уточнять стоимость в клинике.\n"
    "- На вопросы не по теме медуслуг вежливо возвращай к теме.\n"
    "Справочник услуг (примеры): {catalog}"
)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_prices",
            "description": (
                "Поиск цен на медицинскую услугу по клиникам Казахстана в базе "
                "агрегатора. Возвращает предложения, отсортированные по цене."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "название услуги, напр. 'общий анализ крови', 'УЗИ брюшной полости'",
                    },
                    "city": {"type": "string", "description": "город для фильтра (опционально)"},
                    "max_price": {"type": "number", "description": "максимальная цена в тенге (опционально)"},
                    "sort": {
                        "type": "string",
                        "enum": ["price_asc", "price_desc"],
                        "description": "сортировка, по умолчанию price_asc",
                    },
                },
                "required": ["query"],
            },
        },
    }
]


def _run_llm(db: Session, messages: list[ChatMessage]):
    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    cities = [c[0] for c in db.query(distinct(Clinic.city)).all() if c[0]]
    catalog = [s.canonical_name for s in db.query(ServiceCatalog).all()]
    system = _SYSTEM.format(
        today=date.today().isoformat(),
        cities=", ".join(cities) or "—",
        catalog=", ".join(catalog[:40]) or "—",
    )
    convo: list[dict] = [{"role": "system", "content": system}]
    convo += [{"role": m.role, "content": m.content} for m in messages]

    collected: list[ChatOffer] = []
    last_text = ""
    for _ in range(3):  # ограничиваем число раундов tool-calling
        resp = client.chat.completions.create(
            model=settings.groq_model,
            messages=convo,
            tools=_TOOLS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=700,
        )
        msg = resp.choices[0].message
        last_text = msg.content or last_text
        if not msg.tool_calls:
            return last_text, collected

        convo.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            offers, summaries = _search_offers(
                db,
                str(args.get("query", "")),
                args.get("city"),
                args.get("max_price"),
                args.get("sort") or "price_asc",
            )
            collected.extend(offers)
            convo.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": "search_prices",
                    "content": json.dumps(_summaries_for_llm(summaries), ensure_ascii=False),
                }
            )

    return last_text or "Уточните, пожалуйста, какую услугу вы ищете.", collected


def _fallback(db: Session, messages: list[ChatMessage]) -> ChatResponse:
    """Детерминированный ответ без LLM — демо живёт даже без Groq."""
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
    if not settings.groq_api_key:
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
