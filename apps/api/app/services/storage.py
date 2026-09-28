"""Object-storage abstraction (spec §48).

Two drivers behind one protocol, chosen by ``STORAGE_DRIVER``:
- ``local`` (default): files on the local filesystem — fine for dev, but ephemeral on
  most PaaS (wiped on redeploy).
- ``r2`` / ``s3``: Cloudflare R2 or any S3-compatible bucket — durable, survives
  redeploys. Configured with the R2_* settings.

Callers only ever use ``save`` / ``read`` / ``delete`` + ``get_storage()``.
"""
from __future__ import annotations

import uuid
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import settings


class StorageError(Exception):
    """Raised when a stored object can't be read/written (missing, mis-configured)."""


class StorageDriver(Protocol):
    def save(self, data: bytes, filename: str, content_type: str | None = None) -> str: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def path_for(self, key: str) -> str | None: ...


def _safe_key(filename: str) -> str:
    # Opaque, collision-free key; strip any path separators from the original name.
    base = (filename or "file").replace("/", "_").replace("\\", "_")
    return f"{uuid.uuid4().hex}_{base}"


class LocalStorage:
    """Stores files under STORAGE_LOCAL_PATH. Ephemeral on most hosts."""

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.STORAGE_LOCAL_PATH)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, filename: str, content_type: str | None = None) -> str:
        key = _safe_key(filename)
        (self.root / key).write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        p = self.root / key
        if not p.is_file():
            raise StorageError(f"object not found: {key}")
        return p.read_bytes()

    def delete(self, key: str) -> None:
        p = self.root / key
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass

    def path_for(self, key: str) -> str | None:
        return str(self.root / key)


class R2Storage:
    """Cloudflare R2 / S3-compatible object storage (durable). Uses boto3."""

    def __init__(self) -> None:
        import boto3  # lazy: only needed when this driver is selected
        from botocore.config import Config

        endpoint = settings.R2_ENDPOINT or (
            f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
            if settings.R2_ACCOUNT_ID else None
        )
        if not (endpoint and settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY
                and settings.R2_BUCKET):
            raise StorageError(
                "R2 storage selected but not fully configured — set R2_ENDPOINT (or "
                "R2_ACCOUNT_ID), R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET."
            )
        self.bucket = settings.R2_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name=settings.R2_REGION or "auto",
            config=Config(signature_version="s3v4"),
        )

    def save(self, data: bytes, filename: str, content_type: str | None = None) -> str:
        key = _safe_key(filename)
        extra = {"ContentType": content_type} if content_type else {}
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)
        return key

    def read(self, key: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()
        except Exception as e:  # noqa: BLE001 — surface as a uniform storage error
            raise StorageError(f"object not found: {key}") from e

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass

    def path_for(self, key: str) -> str | None:
        return None  # remote object — no local path; callers stream via read()


@lru_cache
def get_storage() -> StorageDriver:
    driver = (settings.STORAGE_DRIVER or "local").strip().lower()
    if driver in ("r2", "s3"):
        return R2Storage()
    return LocalStorage()


__all__ = ["StorageDriver", "LocalStorage", "R2Storage", "StorageError", "get_storage"]
