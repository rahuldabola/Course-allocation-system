"""Application configuration loaded from environment variables."""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-insecure-jwt-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    # Postgres connection. Defaults work with the bundled docker-compose.
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/allocation"

    # Comma-separated list of browser origins allowed to call the API.
    cors_origins: str = "http://localhost:3000"

    # ---- Auth -------------------------------------------------------------
    jwt_secret: str = _DEV_JWT_SECRET
    jwt_expire_minutes: int = 12 * 60
    # Optional bootstrap admin, created (or re-activated) at startup.
    admin_email: str = ""
    admin_password: str = ""
    # Demo mode: seeds sample data into an empty DB, creates the public demo
    # accounts listed by GET /meta, and enables POST /admin/reset-demo.
    demo_mode: bool = False

    # ---- AI assistant -----------------------------------------------------
    # "auto" picks Gemini when GEMINI_API_KEY is set, otherwise no LLM (the
    # assistant then answers the built-in report questions only).
    llm_provider: Literal["auto", "gemini", "ollama", "none"] = "auto"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    # Per-call timeout, and the total time one assistant answer may spend in LLM
    # calls before falling back (built-in report / plain-text summary).
    llm_timeout_seconds: float = 15.0
    assistant_time_budget_seconds: float = 25.0

    # ---- Rate limits (requests per minute) --------------------------------
    login_rate_limit: int = 10
    assistant_rate_limit: int = 20

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Managed Postgres providers (Railway, Heroku, Neon…) hand out
        # postgres:// or postgresql:// URLs; SQLAlchemy needs the driver named.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg2://" + v[len(prefix) :]
        return v

    @model_validator(mode="after")
    def _check_production_secrets(self) -> Settings:
        if self.environment == "production":
            if self.jwt_secret == _DEV_JWT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of 32+ characters")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def effective_llm_provider(self) -> str:
        if self.llm_provider == "auto":
            return "gemini" if self.gemini_api_key else "none"
        return self.llm_provider


settings = Settings()
