from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./medtech.db"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    match_confidence_threshold: float = 0.78


settings = Settings()
