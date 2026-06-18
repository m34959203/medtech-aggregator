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

    @property
    def chat_provider(self) -> str:
        """Фактический провайдер чата с учётом 'auto' и наличия ключей."""
        if self.llm_provider in ("alem", "groq"):
            return self.llm_provider
        return "alem" if self.alem_api_key else "groq"


settings = Settings()
