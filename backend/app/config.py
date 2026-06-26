from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./medtech.db"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    match_confidence_threshold: float = 0.78

    # Безопасность админ-зоны (passwordless: доступ по токену через cookie).
    # Пусто → админ-роуты ЗАКРЫТЫ (fail-closed). Задать ADMIN_TOKEN в .env/проде.
    admin_token: str = ""
    cookie_secure: bool = False  # True за HTTPS в проде (cookie только по TLS)

    # Rate-limiting публичных POST (анти-абуз). In-memory per-IP; Redis — на масштаб.
    rate_limit_enabled: bool = True

    # Этика автосбора (② pull). ТЗ требует соблюдать robots.txt целевых сайтов.
    # respect_robots=True → каждый GET парсера проверяется по robots.txt хоста
    # (RobotFileParser), запрещённые пути не качаются; crawl-delay соблюдается
    # пер-хост (не бомбим сайт). scrape_user_agent — наш токен в User-Agent и
    # в проверке robots (сайт может адресовать правила именно ему).
    respect_robots: bool = True
    scrape_user_agent: str = "MedtechAggregatorBot"
    scrape_crawl_delay: float = 1.0   # сек между запросами к одному хосту (мин.)
    scrape_timeout: float = 20.0
    robots_cache_ttl: float = 3600.0  # сколько кэшируем robots.txt хоста, сек

    # §2.2: валюта price хранится в KZT. Цены в USD конвертируются по курсу
    # (оригинал сохраняется в price_original/currency_original). Курс — настройка.
    usd_kzt_rate: float = 480.0
    # §4: цены старше N дней не считаются актуальными (is_active=False в выдаче).
    price_freshness_days: int = 30
    # §4: сырые данные (raw_content) хранятся не менее N дней для аудита.
    raw_retention_days: int = 90

    # Семантическая нормализация (эмбеддинги + pgvector). Понимает смысл, а не буквы:
    # «кровь на сахар» → «Глюкоза». На Postgres — pgvector; иначе in-process. Если
    # модель/пакет недоступны — слой тихо отключается (нормализатор остаётся на fuzzy).
    semantic_enabled: bool = True
    semantic_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    semantic_threshold: float = 0.72  # минимальная косинусная близость для принятия

    # Чат-помощник. Провайдер OpenAI-совместимый: "alem" (AlemLLM, KZ) или "groq".
    # По умолчанию авто: если задан alem_api_key — alem, иначе groq.
    llm_provider: str = "auto"  # auto / alem / groq
    alem_api_key: str = ""
    alem_base_url: str = "https://llm.alem.ai/v1"
    alem_model: str = "alemllm"

    # WhatsApp-туннель (Baileys-микросервис wa-gateway). Backend ходит к нему по
    # внутренней docker-сети с секретом; фронт/админ — только через наш прокси.
    # Пусто → WA-функции отключены (отдаём 503, не падаем).
    wa_gateway_url: str = ""              # напр. http://medtech-wa:3200
    wa_api_secret: str = ""               # = WA_API_SECRET туннеля (X-API-Secret)
    wa_inbound_webhook_secret: str = ""   # проверка X-Webhook-Secret на входящих

    @property
    def chat_provider(self) -> str:
        """Фактический провайдер чата с учётом 'auto' и наличия ключей."""
        if self.llm_provider in ("alem", "groq"):
            return self.llm_provider
        return "alem" if self.alem_api_key else "groq"


settings = Settings()
