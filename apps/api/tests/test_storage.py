"""Storage drivers: local filesystem and the Cloudflare R2 / S3 driver (mocked)."""
from __future__ import annotations

import io

import pytest

from app.core.config import settings
from app.services import storage
from app.services.storage import LocalStorage, R2Storage, StorageError, get_storage


def test_local_roundtrip(tmp_path):
    st = LocalStorage(root=str(tmp_path))
    key = st.save(b"hello world", "note.txt", "text/plain")
    assert key.endswith("_note.txt")
    assert st.read(key) == b"hello world"
    assert st.path_for(key).endswith(key)
    st.delete(key)
    with pytest.raises(StorageError):
        st.read(key)


def test_get_storage_defaults_to_local(monkeypatch):
    get_storage.cache_clear()
    monkeypatch.setattr(settings, "STORAGE_DRIVER", "local", raising=False)
    assert isinstance(get_storage(), LocalStorage)
    get_storage.cache_clear()


class _FakeS3:
    """Minimal in-memory stand-in for a boto3 S3 client."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket, Key, Body, **kw):  # noqa: N803 (boto3 kwarg names)
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        if (Bucket, Key) not in self.objects:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objects.pop((Bucket, Key), None)


def test_r2_driver_roundtrip(monkeypatch):
    fake = _FakeS3()
    monkeypatch.setattr(settings, "R2_ENDPOINT", "https://acct.r2.cloudflarestorage.com", raising=False)
    monkeypatch.setattr(settings, "R2_ACCESS_KEY_ID", "k", raising=False)
    monkeypatch.setattr(settings, "R2_SECRET_ACCESS_KEY", "s", raising=False)
    monkeypatch.setattr(settings, "R2_BUCKET", "docs", raising=False)

    import boto3
    monkeypatch.setattr(boto3, "client", lambda *a, **k: fake)

    st = R2Storage()
    key = st.save(b"%PDF fake", "waybill.pdf", "application/pdf")
    assert ("docs", key) in fake.objects
    assert st.read(key) == b"%PDF fake"
    assert st.path_for(key) is None  # remote — no local path
    st.delete(key)
    with pytest.raises(StorageError):
        st.read(key)


def test_r2_driver_requires_config(monkeypatch):
    monkeypatch.setattr(settings, "R2_ENDPOINT", "", raising=False)
    monkeypatch.setattr(settings, "R2_ACCOUNT_ID", "", raising=False)
    with pytest.raises(StorageError):
        R2Storage()
