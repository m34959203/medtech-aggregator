from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ClinicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    city: str
    district: str
    address: str
    lat: float | None
    lng: float | None
    phone: str


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    canonical_name: str
    category: str
    synonyms: list = []


class PriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    clinic_id: int
    service_id: int | None
    source_type: str
    raw_name: str
    price: float
    currency: str
    match_confidence: float
    valid_from: date


# --- Агрегатор: сравнение цен ---
class PriceOffer(BaseModel):
    """Одно предложение услуги в конкретной клинике для витрины сравнения."""
    clinic_id: int
    clinic_name: str
    city: str
    district: str
    address: str
    lat: float | None
    lng: float | None
    phone: str
    price: float
    currency: str
    raw_name: str
    source_type: str
    match_confidence: float
    valid_from: date


class ServiceVariant(BaseModel):
    """Другой вариант той же базовой услуги (для перелинковки на витрине)."""
    service_id: int
    canonical_name: str
    label: str
    offers_count: int
    min_price: float


class ServiceComparison(BaseModel):
    service_id: int
    canonical_name: str
    category: str
    offers_count: int
    min_price: float
    max_price: float
    offers: list[PriceOffer]
    # Модель «база + атрибуты варианта»: теги сопоставимости + сёстры-варианты
    attributes: dict = {}
    variants: list[ServiceVariant] = []


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
    clinic_id: int
    channel: str
    format: str
    items_found: int
    matched: int
    needs_review: int
    status: str
