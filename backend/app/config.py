from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://signal:signal@localhost:5432/signal"
    redis_url: str = "redis://localhost:6379/0"
    finnhub_api_key: str = ""
    anthropic_api_key: str = ""
    tracked_tickers: str = ""

    # Model + cost
    claude_model: str = "claude-haiku-4-5"
    classify_max_tokens: int = 600

    # Worker cadence (seconds)
    finnhub_poll_seconds: int = 60
    quote_refresh_seconds: int = 300
    composite_refresh_seconds: int = 120

    # API
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
