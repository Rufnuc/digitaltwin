"""Engine / session factory and the FastAPI DB dependency."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# SQLite needs check_same_thread=False for the threaded test/dev server.
_connect_args = {"check_same_thread": False} if settings.is_sqlite else {}

# pool_pre_ping revives connections a managed/cloud database has dropped; a
# 30-minute recycle proactively replaces idle ones (cloud Postgres often closes
# idle connections). Both are harmless for local Postgres and SQLite.
_engine_kwargs: dict = {"pool_pre_ping": True, "future": True}
if not settings.is_sqlite:
    _engine_kwargs["pool_recycle"] = 1800

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    **_engine_kwargs,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Attach the automatic audit trail to every Session (app, scripts, tests). Imported
# here (not at app startup) so direct SessionLocal use is audited too. Done after
# SessionLocal so a circular import can't skip it.
from app.services.audit_listener import register_audit_listeners  # noqa: E402

register_audit_listeners()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
