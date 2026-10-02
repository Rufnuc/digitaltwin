"""Application settings, loaded from environment / .env (spec §48)."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # Storage abstraction. "local" = filesystem (dev; ephemeral on most hosts).
    # "r2"/"s3" = durable object storage (Cloudflare R2 or any S3-compatible bucket),
    # configured with the R2_* settings below. Recommended in production so uploaded
    # documents/receipts survive redeploys.
    STORAGE_DRIVER: str = "local"
    STORAGE_LOCAL_PATH: str = "./storage"
    # Cloudflare R2 / S3-compatible object storage (used when STORAGE_DRIVER=r2|s3).
    # Secrets come from env only, never committed. R2_ENDPOINT is
    # https://<account-id>.r2.cloudflarestorage.com (or set R2_ACCOUNT_ID to derive it).
    R2_ENDPOINT: str = ""
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = ""
    R2_REGION: str = "auto"

    # AI assistant (Phase 4). Providers behind one seam:
    #   rule_based — offline deterministic router (no LLM, no key)
    #   ollama     — a local LLM via Ollama (free, no key; needs Ollama running)
    #   anthropic  — Claude via API key
    AI_PROVIDER: str = "rule_based"
    AI_API_KEY: str = ""
    AI_MODEL: str = "claude-opus-5"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    # Assistant safety: writes are OFF by default (read-only). The assistant may only
    # perform mutating tools when this is explicitly enabled AND confirm-gating is in
    # place. Setting it back to False is the kill switch that stops all AI writes.
    ASSISTANT_ALLOW_WRITES: bool = False

    # Login brute-force protection: lock an account for LOGIN_LOCKOUT_MINUTES after
    # LOGIN_MAX_ATTEMPTS consecutive failures; a success resets the counter.
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    # Voice input (Whisper, local & offline). The mic records 16 kHz mono WAV in
    # the browser; the backend decodes it with the stdlib and transcribes with a
    # locally cached openai-whisper model — no API key, no ffmpeg. Empty disables.
    WHISPER_MODEL: str = "medium"

    # OCR / Document-AI (Phase 5). Default "structured_json" ingests machine-
    # readable invoice docs offline; commercial providers plug in with keys.
    OCR_PROVIDER: str = "structured_json"

    # Market intelligence (Phase 6). "live" fetches REAL economic data (World Bank,
    # live FX, Google News) on refresh; reads come from the DB. "none" disables it.
    MARKET_DATA_PROVIDER: str = "live"

    # GIS / user location tracking. Store a new fix when the user moves at least
    # GEO_MIN_MOVE_METERS or GEO_MIN_INTERVAL_SECONDS has passed; write an activity-log
    # entry when they move at least GEO_LOG_MOVE_METERS (a meaningful move).
    GEO_TRACKING_ENABLED: bool = True
    GEO_MIN_MOVE_METERS: float = 25.0
    GEO_LOG_MOVE_METERS: float = 100.0
    GEO_MIN_INTERVAL_SECONDS: int = 300
    # Reverse-geocode coordinates to a human address (so the map/activity log read as
    # places, not numbers). Uses OpenStreetMap Nominatim (free, no key). The browser
    # resolves the address and sends it with the ping; the server falls back to this
    # when none is supplied. Set an email per Nominatim's usage policy.
    GEO_REVERSE_GEOCODE: bool = True
    GEO_GEOCODER_URL: str = "https://nominatim.openstreetmap.org/reverse"
    GEO_GEOCODER_EMAIL: str = ""

    # POS reconciliation (card terminals). "moniepoint" enables the Moniepoint
    # webhook + push-to-terminal adapter; "none" disables auto-receiving (manual only).
    # Credentials come from env/.env, never committed.
    POS_PROVIDER: str = "none"
    MONIEPOINT_WEBHOOK_SECRET: str = ""   # HMAC secret to verify incoming webhooks
    MONIEPOINT_API_KEY: str = ""          # bearer/api key for push-to-terminal
    MONIEPOINT_PUSH_URL: str = ""         # endpoint that pops an amount on a terminal
    # How long an "expect POS payment" stays open to be matched (minutes), and the
    # +/- time window used to auto-match an incoming transaction to an expectation.
    POS_EXPECT_TTL_MINUTES: int = 30
    POS_MATCH_WINDOW_MINUTES: int = 20

    # Shipping monitor (aisstream.io live AIS vessel data). Key from env/.env only,
    # never committed. When set, a background task streams vessel positions for the
    # China→Nigeria trade lanes; empty disables the feature.
    AISSTREAM_API_KEY: str = ""

    # Tax (Nigeria defaults; an ESTIMATE, not tax advice — confirm with an accountant).
    # VAT 7.5%. Company income tax is tiered by annual turnover: small (<₦25m) exempt,
    # medium (₦25m–₦100m) 20%, large (>₦100m) 30%.
    TAX_VAT_RATE: float = 0.075
    TAX_CIT_SMALL_TURNOVER: float = 25_000_000.0
    TAX_CIT_MEDIUM_TURNOVER: float = 100_000_000.0
    TAX_CIT_SMALL_RATE: float = 0.0
    TAX_CIT_MEDIUM_RATE: float = 0.20
    TAX_CIT_LARGE_RATE: float = 0.30

    # Quant inventory & decision-support module (forecasting, reorder, risk). Off by
    # default; gates the /quant routes and quant assistant tools (spec v4 §15).
    QUANT_INVENTORY_ENABLED: bool = True
    # Config version stamped onto quant results for reproducibility / replay.
    QUANT_CONFIG_VERSION: str = "1.0.0"
    # ABC-aware cycle service levels: class-A items (most value) are protected more
    # than class-C. Used when no explicit service level is supplied. Tunable.
    QUANT_SERVICE_LEVEL_A: float = 0.98
    QUANT_SERVICE_LEVEL_B: float = 0.95
    QUANT_SERVICE_LEVEL_C: float = 0.90
    QUANT_SERVICE_LEVEL_DEFAULT: float = 0.95  # unknown / no-evidence class
    # Cold-start: give a no-sales-history product a low-confidence peer-based demand
    # prior (same category) instead of a blank (spec v5 §3). On by user request.
    QUANT_COLD_START_ENABLED: bool = True

    # Landed-cost uplifts as a % of the supplier's base cost (spec v4 §9). These are
    # PLACEHOLDERS until an import/clearing expert supplies real figures — see
    # docs/landed_cost_questions_for_expert.md. While QUANT_LANDED_COST_CONFIGURED
    # is False the estimate is shown clearly marked PLACEHOLDER and is NOT used in
    # reorder/margin decisions, so nothing is silently wrong.
    QUANT_LANDED_COST_CONFIGURED: bool = False
    QUANT_LANDED_FREIGHT_PCT: float = 8.0     # placeholder
    QUANT_LANDED_DUTY_PCT: float = 20.0       # placeholder
    QUANT_LANDED_LEVIES_PCT: float = 9.0      # placeholder (VAT/ETLS/surcharge)
    QUANT_LANDED_CLEARING_PCT: float = 5.0    # placeholder (agent/terminal/transport)
    QUANT_LANDED_FX_BUFFER_PCT: float = 5.0   # placeholder
    QUANT_LANDED_QUALITY_PCT: float = 1.0     # placeholder

    # CORS — the website origin(s) allowed to call the API. In production set this to
    # the business's Vercel domain(s). Accepts a comma-separated string (simplest for
    # a host env var, e.g. "https://fidelagric.vercel.app") or a JSON array.
    # NoDecode: stop pydantic-settings from JSON-parsing the env value before our
    # validator runs, so a plain "https://a.com,https://b.com" string is accepted
    # (not only a JSON array). The validator handles both forms.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("["):
                return json.loads(s)  # JSON array form
            return [o.strip() for o in s.split(",") if o.strip()]  # comma-separated form
        return v

    # Developer/vendor accounts (the person who builds & supplies the software). These
    # accounts — identified by email, independent of business role — can see "internal"
    # knowledgebase articles (e.g. the development changelog) that the business owner and
    # staff never see. Comma-separated emails; override via env.
    DEVELOPER_EMAILS: str = "israelegede@gmail.com"

    @property
    def developer_emails(self) -> set[str]:
        return {e.strip().lower() for e in (self.DEVELOPER_EMAILS or "").split(",") if e.strip()}

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "production"

    def production_config_errors(self) -> list[str]:
        """Misconfigurations that must block a production boot (fail fast, don't run
        insecure)."""
        errs: list[str] = []
        if self.is_production:
            if self.AUTH_SECRET == "dev-insecure-secret-change-me":
                errs.append("AUTH_SECRET must be a strong random value in production")
            if self.is_sqlite:
                errs.append("DATABASE_URL must point at Postgres in production, not sqlite")
        return errs


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
