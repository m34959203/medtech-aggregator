import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .ingestion.category import Category
from .ingestion.currency import Currency


class ClinicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    city: str
    district: str
    address: str
    lat: float | None
    lng: float | None
    phone: str
    working_hours: str = ""
    website: str = ""
    rating: float | None = None
    online_booking: bool | None = None


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    canonical_name: str
    category: str
    synonyms: list = []


class PriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    clinic_id: uuid.UUID
    service_id: uuid.UUID | None
    source_type: str
    raw_name: str
    price: float
    currency: Currency
    match_confidence: float
    valid_from: date


# --- §2.2 MedPrice: плоская «запись собираемых данных» (в точь по ТЗ) ---
class CollectedRecord(BaseModel):
    """Один кортеж (клиника × услуга × цена) — структура §2.2 дословно.

    Поля, имена и типы соответствуют таблице ТЗ §2.2 «Структура собираемых
    данных» один-в-один. `category`/`currency` — строгие enum; `price_kzt` —
    decimal; нормализованное имя берётся из привязки к справочнику.
    """

    clinic_id: uuid.UUID
    clinic_name: str
    city: str
    address: str
    phone: str
    working_hours: str
    source_url: str
    service_id: uuid.UUID
    service_name_raw: str
    service_name_norm: str
    category: Category
    price_kzt: Decimal
    currency: Currency
    duration_days: int | None
    parsed_at: datetime
    is_active: bool


# --- Агрегатор: сравнение цен ---
class PriceOffer(BaseModel):
    """Одно предложение услуги в конкретной клинике для витрины сравнения."""
    clinic_id: uuid.UUID
    clinic_name: str
    city: str
    district: str
    address: str
    lat: float | None
    lng: float | None
    phone: str
    price: float
    currency: Currency
    raw_name: str
    source_type: str
    match_confidence: float
    valid_from: date
    # §2.2 MedPrice: режим работы, сайт, рейтинг, онлайн-запись, ссылка на источник,
    # срок выполнения, актуальность, время парсинга, оригинальная цена/валюта.
    working_hours: str = ""
    website: str = ""
    source_url: str = ""
    # §2.2 дословные имена: норм. название услуги и цена в KZT (для записи-кортежа)
    service_name_norm: str = ""
    price_kzt: float | None = None
    rating: float | None = None
    online_booking: bool | None = None
    duration_days: int | None = None
    is_active: bool = True
    parsed_at: datetime | None = None
    price_original: float | None = None
    currency_original: str = ""


class ServiceVariant(BaseModel):
    """Другой вариант той же базовой услуги (для перелинковки на витрине)."""
    service_id: uuid.UUID
    canonical_name: str
    label: str
    offers_count: int
    min_price: float


class ServiceComparison(BaseModel):
    service_id: uuid.UUID
    canonical_name: str
    category: str
    category_enum: Category | None = None  # §2.2: лаборатория / приём врача / диагностика / процедура
    offers_count: int
    min_price: float
    max_price: float
    offers: list[PriceOffer]
    # Модель «база + атрибуты варианта»: теги сопоставимости + сёстры-варианты
    attributes: dict = {}
    variants: list[ServiceVariant] = []
    # Динамика цен из истории (если накоплено ≥2 точек): {points, change_pct, direction}
    price_trend: dict | None = None
    # Онтология: {code, group, osms} — стандартный код, группа, покрытие ОСМС
    ontology: dict | None = None


class IngestionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_id: int | None
    channel: str
    format: str
    status: str
    items_found: int
    message: str
    created_at: datetime


class IngestionResult(BaseModel):
    run_id: int
    clinic_id: uuid.UUID
    channel: str
    format: str
    items_found: int
    matched: int
    needs_review: int
    status: str
