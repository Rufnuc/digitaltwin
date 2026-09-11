"""Object-storage abstraction (spec §48). Phase 1 ships a local-filesystem
driver; an S3 driver implements the same protocol later without touching callers.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import settings


class StorageDriver(Protocol):
    def save(self, data: bytes, filename: str, content_type: str | None = None) -> str: ...
    def path_for(self, key: str) -> str: ...


class LocalStorage:
    """Stores files under STORAGE_LOCAL_PATH, returning an opaque storage key."""

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.STORAGE_LOCAL_PATH)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, filename: str, content_type: str | None = None) -> str:
        key = f"{uuid.uuid4().hex}_{filename}"
        (self.root / key).write_bytes(data)
        return key

    def path_for(self, key: str) -> str:
        return str(self.root / key)


def get_storage() -> StorageDriver:
    # Only the local driver is wired in Phase 1; S3 selected via STORAGE_DRIVER later.
    return LocalStorage()


__all__ = ["StorageDriver", "LocalStorage", "get_storage"]
