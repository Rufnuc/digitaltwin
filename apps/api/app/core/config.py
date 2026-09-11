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

    # Provider abstractions (unused in Phase 1, present for config stability)
    AI_PROVIDER: str = "none"
    OCR_PROVIDER: str = "none"
    MARKET_DATA_PROVIDER: str = "none"

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
