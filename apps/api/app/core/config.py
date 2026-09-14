"""Application settings, loaded from environment / .env (spec §48)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),  # api dir or repo root
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "DigitalTwin"
    API_V1_PREFIX: str = "/api/v1"

    # Security
    AUTH_SECRET: str = "dev-insecure-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    # Database. Defaults to a local sqlite file so the app is runnable with zero
    # infra; docker/postgres is used by setting DATABASE_URL (see .env.example).
    DATABASE_URL: str = "sqlite:///./digitaltwin.db"

    # Storage abstraction
    STORAGE_DRIVER: str = "local"
    STORAGE_LOCAL_PATH: str = "./storage"

    # AI assistant (Phase 4). Providers behind one seam:
    #   rule_based — offline deterministic router (no LLM, no key)
    #   ollama     — a local LLM via Ollama (free, no key; needs Ollama running)
    #   anthropic  — Claude via API key
    AI_PROVIDER: str = "rule_based"
    AI_API_KEY: str = ""
    AI_MODEL: str = "claude-opus-5"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    # OCR / Document-AI (Phase 5). Default "structured_json" ingests machine-
    # readable invoice docs offline; commercial providers plug in with keys.
    OCR_PROVIDER: str = "structured_json"

    # Market intelligence (Phase 6). "live" fetches REAL economic data (World Bank,
    # live FX, Google News) on refresh; reads come from the DB. "none" disables it.
    MARKET_DATA_PROVIDER: str = "live"

    # Shipping monitor (aisstream.io live AIS vessel data). Key from env/.env only,
    # never committed. When set, a background task streams vessel positions for the
    # China→Nigeria trade lanes; empty disables the feature.
    AISSTREAM_API_KEY: str = ""

    # Quant inventory & decision-support module (forecasting, reorder, risk). Off by
    # default; gates the /quant routes and quant assistant tools (spec v4 §15).
    QUANT_INVENTORY_ENABLED: bool = True
    # Config version stamped onto quant results for reproducibility / replay.
    QUANT_CONFIG_VERSION: str = "1.0.0"

    # CORS
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
