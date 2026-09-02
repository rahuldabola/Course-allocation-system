"""Application configuration loaded from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres connection. Defaults work with the bundled docker-compose.
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/allocation"

    # Ollama (local LLM) connection for the AI assistant.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # Allow the Next.js dev server to call the API.
    cors_origins: str = "http://localhost:3000"

    # Shared secret required (via X-API-Key) on write / expensive endpoints.
    # Empty string disables auth — fine for local dev, set it for anything shared.
    api_key: str = ""


settings = Settings()
