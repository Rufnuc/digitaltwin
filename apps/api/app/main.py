"""FastAPI application entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("digitaltwin")

app = FastAPI(
    title=f"{settings.PROJECT_NAME} API",
    version="0.1.0",
    description="AI Business Digital Twin & Decision Support Platform — Phase 1 foundation.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.on_event("startup")
def _startup() -> None:
    # Dev ergonomics: on SQLite, ensure tables exist so the app runs with zero
    # infra. Postgres (app/prod) is migrated with Alembic — the source of truth.
    if settings.is_sqlite:
        import app.models  # noqa: F401  (populate metadata)
        from app.db.base import Base
        from app.db.session import engine

        Base.metadata.create_all(bind=engine)
        logger.info("SQLite detected: ensured tables via create_all (dev mode).")

    # Start the live shipping monitor if an aisstream key is configured.
    if settings.AISSTREAM_API_KEY:
        from app.services.shipping import collector
        collector.start()
        logger.info("Shipping monitor started (aisstream).")

    # Periodic housekeeping (sweeps stranded idempotency reservations).
    from app.services import maintenance
    maintenance.start()
    logger.info("Maintenance loop started.")


@app.on_event("shutdown")
async def _shutdown() -> None:
    if settings.AISSTREAM_API_KEY:
        from app.services.shipping import collector
        await collector.stop()

    from app.services import maintenance
    await maintenance.stop()


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "environment": settings.ENVIRONMENT, "version": "0.1.0"}


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": settings.PROJECT_NAME,
        "docs": "/docs",
        "api": settings.API_V1_PREFIX,
        "phase": 1,
    }
