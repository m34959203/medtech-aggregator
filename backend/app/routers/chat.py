"""Чат-помощник пациента — диалоговый поиск по витрине цен.

Помощник = НАДСТРОЙКА над агрегатором, а не отдельный «всезнающий» LLM:
сначала ПРИНУДИТЕЛЬНО ищем по тому же нормализованному справочнику, что и
витрина, и вкладываем результаты в контекст модели (retrieval-injection).
Поэтому бот не выдумывает цены/клиники — отвечает строго по данным.

LLM — единая точка `llm.chat` (как у нормализатора/recheck): по умолчанию
Gemini 2.5-flash через Vertex AI, фолбэк AlemLLM/Groq (LLM_PROVIDER). Tool-calling
НЕ используется — retrieval-injection работает с любым провайдером.

Деградация: без ключа/SA провайдера (или при ошибке сети) endpoint отвечает
детерминированным поиском-сводкой. Демо работает всегда — важно для жюри.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from rapidfuzz import fuzz
from sqlalchemy import distinct
from sqlalchemy.orm import Session

from .. import llm
from ..ratelimit import rate_limit
from ..db import get_db
from ..ingestion.normalizer import _biomat_conflict, _clean
from ..models import Clinic, ServiceCatalog
from .aggregator import _build_comparison
# Переиспользуем извлечение услуг из фото/скана направления (OCR) — тот же
# пайплайн, что и страница /recipe (Кейс 2 §4.2: tesseract rus/kaz/eng).
from .basket import _extract_text_any, extract_service_names

router = APIRouter(prefix="/api", tags=["assistant"])


# --- Контракт ---
class ChatMessage(BaseModel):
    role: str  # user / assistant
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatOffer(BaseModel):
    """Предложение для карточек в виджете (фронт рендерит ссылку/телефон).

    service_id/clinic_id (uuid, §2.2) нужны фронту для конечных действий (CTA):
    чип услуги → /service/{service_id}, оффер → /service/{id}?clinic={clinic_id}."""
    service_id: str
    clinic_id: str
    service: str
    clinic_name: str
    city: str
    district: str
    address: str
    phone: str
    price: float
    currency: str
    is_cheapest: bool
    lat: float | None = None  # координаты клиники → CTA «Маршрут» (Яндекс)
    lng: float | None = None


class ChatResponse(BaseModel):
    reply: str
    offers: list[ChatOffer] = []
    grounded: bool  # ответ построен на реальных данных витрины
    llm: bool       # отвечал LLM (False = детерминированный фолбэк)
    recognized: list[str] = []  # услуги, распознанные с фото/скана (OCR-путь)


# --- Поиск по справочнику (общая воронка с витриной) ---
def _rank_services(db: Session, query: str, limit: int = 3) -> list[ServiceCatalog]:
    """Фаззи-подбор услуг справочника под свободный запрос пользователя.

    Если пользователь явно назвал услугу (название справочника целиком входит в
    запрос — «...общий анализ крови...»), отдаём ТОЛЬКО её и близкие прямые
    совпадения, не размывая выдачу похожими услугами («общий анализ мочи»,
    «глюкоза»). Это убирает ложные 🏆 и неверный «самый дешёвый» в ответе.
    """
    q = _clean(query)
    if not q:
        return []
    direct: list[ServiceCatalog] = []
    scored: list[tuple[float, ServiceCatalog]] = []
    for svc in db.query(ServiceCatalog).all():
        # биоматериал-гард (плановый дефолт): обычная «Глюкоза» не должна тянуть
        # мочевой вариант «Глюкоза в моче» — берём кровяной/прямой канон.
        if _biomat_conflict(query, svc.canonical_name):
            continue
        keys = [svc.canonical_name] + [str(s) for s in (svc.synonyms or [])]
        cleaned = [_clean(k) for k in keys]
        # Явное упоминание услуги в запросе (длиной от 4 символов — чтобы «КТ»/«ОАК»
        # не цеплялись как случайные подстроки).
        if any(k and len(k) >= 4 and k in q for k in cleaned):
            direct.append(svc)
            continue
        best = max((fuzz.token_set_ratio(q, k) for k in cleaned), default=0.0)
        if best >= 60:
            scored.append((best, svc))
    if direct:
        return direct[:limit]
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
        marked = False  # 🏆 ставим ровно одной клинике, даже при равных ценах
        for o in cmp.offers[:per_service]:
            is_cheapest = not marked and o.price == cheapest
            if is_cheapest:
                marked = True
            offers.append(
                ChatOffer(
                    service_id=str(cmp.service_id),
                    clinic_id=str(o.clinic_id),
                    service=cmp.canonical_name,
                    clinic_name=o.clinic_name,
                    city=o.city,
                    district=o.district,
                    address=o.address,
                    phone=o.phone,
                    price=o.price,
                    currency=o.currency,
                    is_cheapest=is_cheapest,
                    lat=o.lat,
                    lng=o.lng,
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
    """Находит упомянутый в запросе город — с учётом падежей.

    «в Караганде», «из Астаны», «по Шымкенту» — русские склонения меняют
    окончание, поэтому точного вхождения мало. Сначала пробуем прямое вхождение
    (именительный падеж), затем совпадение по основе слова и фаззи-похожесть.
    """
    low = _clean(text)
    if not low:
        return None
    tokens = low.split()
    best_city, best_score = None, 0.0
    for (city,) in db.query(distinct(Clinic.city)).all():
        if not city:
            continue
        cl = _clean(city)
        if not cl:
            continue
        if cl in low:  # именительный падеж / точное вхождение
            return city
        # Склонения: общая основа (Караганд|а→е, Астан|а→ы) либо высокая похожесть.
        stem = cl[: max(4, len(cl) - 2)]
        score = max((fuzz.ratio(tok, cl) for tok in tokens), default=0.0)
        if any(tok.startswith(stem) for tok in tokens):
            score = max(score, 90.0)
        if score > best_score:
            best_score, best_city = score, city
    return best_city if best_score >= 80 else None


def _chat_completion(messages: list[dict]) -> str:
    """Чат-комплишн активного LLM-провайдера (Gemini 2.5-flash через Vertex по
    умолчанию; фолбэк AlemLLM/Groq). Единая точка `llm.chat` — та же, что у
    нормализатора/recheck (Gemini thinking отключён, system-роль поддержана)."""
    return llm.chat(messages)


def _compose_reply(db: Session, messages: list[ChatMessage], summaries) -> str:
    """retrieval-injection: вкладываем найденные summaries в system и зовём LLM."""
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
    return _chat_completion(convo)


def _run_llm(db: Session, messages: list[ChatMessage]):
    user_q = next((m.content for m in reversed(messages) if m.role == "user"), "")
    city = _detect_city(db, user_q)
    offers, summaries = _search_offers(db, user_q, city=city)
    text = _compose_reply(db, messages, summaries)
    return text or "Уточните, пожалуйста, какую услугу вы ищете.", offers


def _has_chat_key() -> bool:
    return llm.has_key()  # Gemini/Vertex (SA) либо ключ alem/groq


def _offers_for_names(db: Session, names: list[str], city: str | None, per_service: int = 6):
    """Offers+summaries по СПИСКУ распознанных имён услуг (OCR-направление)."""
    offers: list[ChatOffer] = []
    summaries = []
    seen: set = set()
    for nm in names:
        for svc in _rank_services(db, nm, limit=1):
            if svc.id in seen:
                continue
            seen.add(svc.id)
            cmp = _build_comparison(db, svc, city, None, "price_asc")
            if cmp.offers_count == 0:
                continue
            summaries.append(cmp)
            cheapest, marked = cmp.min_price, False
            for o in cmp.offers[:per_service]:
                is_cheapest = not marked and o.price == cheapest
                marked = marked or is_cheapest
                offers.append(ChatOffer(
                    service_id=str(cmp.service_id), clinic_id=str(o.clinic_id),
                    service=cmp.canonical_name, clinic_name=o.clinic_name, city=o.city,
                    district=o.district, address=o.address, phone=o.phone,
                    price=o.price, currency=o.currency, is_cheapest=is_cheapest,
                    lat=o.lat, lng=o.lng,
                ))
    return offers, summaries


def _vision_reply_text(summaries, recognized: list[str]) -> str:
    """Детерминированный ответ для OCR-пути (без LLM/ключа) — демо живёт всегда."""
    head = "Распознал на направлении: " + ", ".join(recognized[:10]) + ".\n\n"
    if not summaries:
        return head + ("По этим услугам цен в базе пока нет — уточните названия "
                       "или попробуйте более чёткое фото.")
    lines = []
    for cmp in summaries:
        cheap = min(cmp.offers, key=lambda o: o.price)
        loc = f", {cheap.district}" if cheap.district else ""
        cur = getattr(cheap.currency, "value", cheap.currency)  # enum → "KZT"
        lines.append(f"• {cmp.canonical_name}: от {cheap.price:.0f} {cur} — "
                     f"{cheap.clinic_name}{loc} (предложений: {cmp.offers_count})")
    return (head + "Где сделать дешевле:\n" + "\n".join(lines)
            + "\n\nЦены справочные — уточняйте актуальную стоимость в клинике.")


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
        cur = getattr(cheap.currency, "value", cheap.currency)  # enum → "KZT"
        lines.append(
            f"• {cmp.canonical_name}: от {cheap.price:.0f} {cur} — "
            f"{cheap.clinic_name}{loc} (предложений: {cmp.offers_count})"
        )
    reply = (
        "Вот что нашлось по вашему запросу:\n"
        + "\n".join(lines)
        + "\n\nЦены справочные — уточняйте актуальную стоимость в клинике."
    )
    return ChatResponse(reply=reply, offers=_dedupe(offers), grounded=True, llm=False)


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit("chat", 20))])
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    if not req.messages:
        return ChatResponse(
            reply="Здравствуйте! Я помогу найти медуслугу дешевле. Что ищете?",
            grounded=False,
            llm=False,
        )
    if not _has_chat_key():
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


@router.post("/chat/vision", response_model=ChatResponse,
             dependencies=[Depends(rate_limit("chat_vision", 10))])
async def chat_vision(
    file: UploadFile = File(...),
    city: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """OCR в чате: фото/скан направления → распознавание услуг → ответ по витрине.

    Тот же retrieval-injection, что и текстовый чат: распознанные услуги ищем по
    нормализованному справочнику и отвечаем строго по данным (цены не выдумываем).
    Деградация: нет OCR/ключа — детерминированная сводка по распознанным услугам.
    """
    content = await file.read()
    text = _extract_text_any(file.filename or "", content)
    if not text.strip():
        return ChatResponse(
            reply=("Не удалось прочитать изображение — OCR недоступен или фото "
                   "нечёткое. Пришлите более чёткий снимок направления или напишите "
                   "услуги текстом."),
            grounded=False, llm=False, recognized=[],
        )
    names = extract_service_names(text)
    if not names:
        return ChatResponse(
            reply="На изображении не нашёл названий услуг. Попробуйте более чёткое фото.",
            grounded=False, llm=False, recognized=[],
        )
    detected_city = city or _detect_city(db, text)
    offers, summaries = _offers_for_names(db, names, detected_city)
    offers = _dedupe(offers)
    recognized = [cmp.canonical_name for cmp in summaries] or names[:10]

    if _has_chat_key() and summaries:
        try:
            synthetic = ChatMessage(
                role="user",
                content=(f"Вот услуги из моего направления: {', '.join(names[:15])}. "
                         f"Где их сделать дешевле"
                         f"{' в ' + detected_city if detected_city else ''}?"),
            )
            reply = _compose_reply(db, [synthetic], summaries)
            if reply:
                return ChatResponse(reply=reply, offers=offers, grounded=bool(offers),
                                    llm=True, recognized=recognized)
        except Exception:
            pass  # сеть/квота — деградируем в детерминированный ответ
    return ChatResponse(reply=_vision_reply_text(summaries, recognized), offers=offers,
                        grounded=bool(offers), llm=False, recognized=recognized)
