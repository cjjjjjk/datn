"""
Central configuration for HocGioi-Agent.
Reads environment variables from .env file using pydantic-settings.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    # ── Supabase ──────────────────────────────────────────────────
    SUPABASE_URL: str = "http://127.0.0.1:54321"
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""

    # ── Google Gemini (via AI Studio) ─────────────────────────────
    # Free API key: https://aistudio.google.com/apikey
    GOOGLE_API_KEY: str = ""
    # Model names, e.g. "gemini-2.0-flash" or "gemini-1.5-flash"
    MODEL_FAST: str = "gemini-2.0-flash"
    MODEL_SMART: str = "gemini-2.0-flash"

    # ── Agent behavior ────────────────────────────────────────────
    MAX_CONVERSATION_HISTORY: int = 20
    STREAMING_ENABLED: bool = True

    # ── FastAPI server ────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # ── CSV exercise data directory ───────────────────────────────
    # Relative to the repo root, e.g. ../HocGioi/public/samples
    CSV_DATA_DIR: str = "../HocGioi/public/samples"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
