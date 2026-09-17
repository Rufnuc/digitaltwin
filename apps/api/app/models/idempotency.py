"""Idempotency keys for money/stock-moving writes.

A client sends the same ``Idempotency-Key`` when it retries a request (a timed-out
sale, a double-tapped "Record payment"). The key is reserved on first sight; a
replay returns the stored result of the original write instead of performing a
second one. The key's uniqueness is enforced by the database, so even two
simultaneous retries cannot both succeed.
"""
from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class IdempotencyKey(Base, TimestampMixin):
    __tablename__ = "idempotency_keys"

    # The client-supplied key is the primary key — one row per logical request.
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    # The endpoint/scope the key was used for, so the same key on a different action
    # is treated as a conflict rather than silently replaying the wrong response.
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    # The stored successful response; SQL NULL means the original request is still in
    # flight (reserved but not yet completed). none_as_null makes a Python None persist
    # as SQL NULL (not JSON 'null'), so `response_json IS NULL` filters work.
    response_json: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
