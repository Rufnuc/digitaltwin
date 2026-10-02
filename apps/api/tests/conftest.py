"""Test fixtures.

Uses a throwaway file-backed SQLite database so the exact same models/queries run
without any external infrastructure. DATABASE_URL is set before the app is
imported so the app engine and the test engine are the same database.
"""
from __future__ import annotations

import os
import tempfile

# Must be set before importing anything under app.* (settings reads env at import).
_TMP_DB = os.path.join(tempfile.gettempdir(), "digitaltwin_test.sqlite3")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["AUTH_SECRET"] = "test-secret"
# Deterministic providers for tests (don't depend on a local .env).
os.environ["OCR_PROVIDER"] = "structured_json"
os.environ["AI_PROVIDER"] = "rule_based"
os.environ["MARKET_DATA_PROVIDER"] = "none"
os.environ["GEO_REVERSE_GEOCODE"] = "false"  # no network reverse-geocoding in tests
os.environ["AISSTREAM_API_KEY"] = ""  # no live shipping socket during tests

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture(autouse=True)
def _create_schema():
    # Per-test clean schema so each test is fully isolated (seed() is not idempotent
    # by design — unique codes would collide across tests otherwise).
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


def _make_user(db, email: str, role: str) -> User:
    user = db.query(User).filter_by(email=email).first()
    if not user:
        user = User(email=email, full_name=email, hashed_password=hash_password("pw123456"),
                    role=role)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def token_factory(db):
    def _factory(role: str = "ADMIN") -> str:
        user = _make_user(db, f"{role.lower()}@test.example.com", role)
        return create_access_token(subject=str(user.id), role=role)
    return _factory


@pytest.fixture
def auth_headers(token_factory):
    def _headers(role: str = "ADMIN") -> dict:
        return {"Authorization": f"Bearer {token_factory(role)}"}
    return _headers
