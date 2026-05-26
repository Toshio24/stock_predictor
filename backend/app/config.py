"""Centralised settings loader.

Reads from environment / `.env`. Pydantic validation runs at startup —
malformed env config crashes the process rather than running in an
unsafe half-configured state. Every secret has a default of `""` so the
code never panics on import; callers must check explicitly before use.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Infra -------------------------------------------------------------
    database_url: str = "postgresql+psycopg://signal:signal@localhost:5432/signal"
    redis_url: str = "redis://localhost:6379/0"

    # --- Secrets (default empty so missing keys don't crash imports) -------
    finnhub_api_key: str = ""
    anthropic_api_key: str = ""
    fred_api_key: str = ""

    # --- Tracked universe --------------------------------------------------
    tracked_tickers: str = ""

    # --- Model + cost ------------------------------------------------------
    claude_model: str = "claude-haiku-4-5"
    classify_max_tokens: int = 600

    # --- Worker cadence (seconds) -----------------------------------------
    finnhub_poll_seconds: int = 60
    quote_refresh_seconds: int = 300
    composite_refresh_seconds: int = 120
    macro_refresh_seconds: int = 3600        # FRED updates daily; hourly is plenty
    fundamentals_refresh_seconds: int = 86400  # once a day

    # --- Security ----------------------------------------------------------
    app_env: Literal["dev", "staging", "prod"] = "dev"
    cors_origins: str = "http://localhost:3000"
    allowed_hosts: str = "localhost,127.0.0.1"
    firebase_project_id: str = ""
    allowed_users: str = ""
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 20

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", "allowed_hosts", "tracked_tickers", "allowed_users")
    @classmethod
    def _strip(cls, v: str) -> str:
        return (v or "").strip()

    # --- Derived helpers ---------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def allowed_user_list(self) -> list[str]:
        return [u.strip().lower() for u in self.allowed_users.split(",") if u.strip()]

    @property
    def auth_enabled(self) -> bool:
        return bool(self.firebase_project_id)

    @property
    def is_prod(self) -> bool:
        return self.app_env in ("prod", "staging")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Production sanity checks — fail fast on misconfig.
    if s.is_prod:
        if not s.firebase_project_id:
            raise RuntimeError(
                "APP_ENV=prod requires FIREBASE_PROJECT_ID to be set "
                "(otherwise every API call is unauthenticated)."
            )
        if "*" in s.cors_origin_list or not s.cors_origin_list:
            raise RuntimeError("CORS_ORIGINS must be an explicit allow-list in prod.")
        if not s.allowed_host_list or "localhost" in s.allowed_host_list:
            raise RuntimeError("ALLOWED_HOSTS must be set to your prod domain(s).")
    return s
