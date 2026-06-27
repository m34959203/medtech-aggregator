import uuid
from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# §2.2 ТЗ: clinic_id и service_id — uuid. Тип Uuid портативен (PG native uuid /
# SQLite CHAR(32)), что важно для тестов на SQLite и прода на Postgres.


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(Text, default="")
    district: Mapped[str] = mapped_column(Text, default="")
    address: Mapped[str] = mapped_column(Text, default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str] = mapped_column(Text, default="")
    # §2.2 MedPrice: режим работы, сайт клиники и рейтинг (для фильтра/сортировки).
    working_hours: Mapped[str] = mapped_column(Text, default="")
    website: Mapped[str] = mapped_column(Text, default="")          # ссылка на сайт клиники
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)  # рейтинг (0..5), фильтр §3.3
    online_booking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # есть онлайн-запись, фильтр §3.3
    # Токен доступа к self-service порталу клиники (passwordless). Выдаётся админом,
    # клиника правит/подтверждает свои цены по ссылке /clinic/<token>.
    access_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)

    prices: Mapped[list["Price"]] = relationship(back_populates="clinic")
    sources: Mapped[list["Source"]] = relationship(back_populates="clinic")


class ServiceCatalog(Base):
    __tablename__ = "service_catalog"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, default="")
    synonyms: Mapped[list] = mapped_column(JSON, default=list)
    # MedArchive: целевой справочник организаторов — код тарификатора (A02.004.000)
    # и специальность. Маппинг по коду даёт 100%-сопоставление без fuzzy.
    tarificator_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    specialty: Mapped[str] = mapped_column(Text, default="")

    prices: Mapped[list["Price"]] = relationship(back_populates="service")


class Source(Base):
    """Реестр источников данных: загрузка, веб-парсинг, API."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clinics.id"))
    type: Mapped[str] = mapped_column(String(20))  # upload / web_scrape / api
    url_or_endpoint: Mapped[str] = mapped_column(Text, default="")
    schedule: Mapped[str] = mapped_column(Text, default="")  # cron-строка
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    clinic: Mapped["Clinic"] = relationship(back_populates="sources")
    runs: Mapped[list["IngestionRun"]] = relationship(back_populates="source")


class IngestionRun(Base):
    """Журнал запусков приёма данных (push-загрузка и pull-автосбор)."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(10))  # push / pull
    format: Mapped[str] = mapped_column(String(20), default="")  # xlsx/csv/pdf/scan/html/json
    status: Mapped[str] = mapped_column(String(20), default="started")  # started/parsed/normalized/error/needs_review
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # MedArchive §3.2 «PriceDocument»: исходный документ-прайс (аудит / повторная
    # обработка). IngestionRun несёт поля сущности PriceDocument из ТЗ:
    #   doc_id=id · partner_id=clinic_id · file_name · file_format=format ·
    #   effective_date · parsed_at=created_at · parse_status=status · parse_log=message ·
    #   raw_content · file_path (путь к сохранённому оригиналу, §2.1/§5).
    file_name: Mapped[str] = mapped_column(Text, default="")
    raw_content: Mapped[str] = mapped_column(Text, default="")  # сырой извлечённый текст
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("clinics.id"), nullable=True)  # партнёр-источник документа
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # дата вступления прайса в силу
    file_path: Mapped[str] = mapped_column(Text, default="")  # путь к сохранённому оригиналу
    # позиционные метрики качества прогона (до дедупа) — для честного archive/quality:
    # auto_rate = matched/(matched+needs_review). По сохранённым строкам метрика
    # искажается (matched схлопывается по service_id, unmatched — нет).
    matched: Mapped[int] = mapped_column(Integer, default=0)
    needs_review: Mapped[int] = mapped_column(Integer, default=0)

    source: Mapped["Source"] = relationship(back_populates="runs")
    prices: Mapped[list["Price"]] = relationship(back_populates="run")


class PriceReport(Base):
    """Жалоба пользователя «цена неверная» — петля обратной связи (Кейс 1, доверие).

    Дёшево повышает качество: спорные цены попадают в очередь на ручную проверку.
    """

    __tablename__ = "price_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("clinics.id"), nullable=True)
    clinic_name: Mapped[str] = mapped_column(Text, default="")
    service: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="new")  # new / reviewed / fixed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Lead(Base):
    """Заявка на приём/услугу — лид для клиники (Спринт-2, монетизация).

    Пациент оставляет заявку с карточки → лид уходит клинике. Закрывает воронку
    и даёт бизнес-модель (оплата за лиды).
    """

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("clinics.id"), nullable=True)
    clinic_name: Mapped[str] = mapped_column(Text, default="")
    service: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    name: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="new")  # new / contacted / closed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Price(Base):
    """Цена услуги в конкретной клинике — результат нормализации."""

    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clinics.id"))
    service_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_catalog.id"), nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="upload")  # upload/web_scrape/api
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="KZT")  # валюта price (после конверсии — KZT)
    match_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    valid_from: Mapped[date] = mapped_column(Date, default=date.today)
    # §2.2 MedPrice: точное время парсинга, флаг актуальности, срок выполнения (анализы),
    # и оригинальная цена/валюта до конверсии USD→KZT (прозрачность источника).
    parsed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # nullable: additive-колонка на проде добавляется как NULL у легаси-строк;
    # читатели трактуют NULL как активную (неактивна = явный False).
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True, nullable=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_original: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency_original: Mapped[str] = mapped_column(String(8), default="")
    # MedArchive: раздельные тарифы резидент/нерезидент + код услуги из источника.
    # price (выше) = основной тариф (резидент, либо единственный) — путь MedPrice не ломается.
    price_resident: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_nonresident: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    service_code_source: Mapped[str] = mapped_column(String(48), default="")  # код как в документе
    tarificator_code: Mapped[str] = mapped_column(String(32), default="")      # нормализованный код тарификатора
    # §2.2 MedPrice: URL источника записи (откуда снята цена) — web_scrape: страница
    # прайса; api: ref коннектора; upload: имя файла. Прозрачность происхождения.
    source_url: Mapped[str] = mapped_column(Text, default="")

    clinic: Mapped["Clinic"] = relationship(back_populates="prices")
    service: Mapped["ServiceCatalog"] = relationship(back_populates="prices")
    run: Mapped["IngestionRun"] = relationship(back_populates="prices")


class PriceHistory(Base):
    """Лог изменений цены (Спринт-3): снимок при создании/изменении цены.

    Даёт тренды и историю — уникальный контент («цена выросла на 12% за месяц»)
    и SEO-магнит. Пишется только при ИЗМЕНЕНИИ цены, чтобы не раздувать таблицу.
    """

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clinics.id"), index=True)
    service_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_catalog.id"), index=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2))
    recorded_at: Mapped[date] = mapped_column(Date, default=date.today, index=True)


class PriceSubscription(Base):
    """§3.4 (опц.): подписка пользователя на снижение цены по услуге (и опц. клинике).

    Планировщик сверяет текущий минимум с `last_price`; при снижении шлёт уведомление
    в WhatsApp. `clinic_id`=NULL → следим за минимумом по услуге (опц. в рамках города)."""

    __tablename__ = "price_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_catalog.id"), index=True)
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("clinics.id"), nullable=True)
    city: Mapped[str] = mapped_column(Text, default="")        # ограничить городом (если clinic_id NULL)
    phone: Mapped[str] = mapped_column(String(32))             # WhatsApp подписчика
    last_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # последний замеченный минимум
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
