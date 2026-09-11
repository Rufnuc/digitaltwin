from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DocumentStatus, ImportStatus
from app.db.base import Base, TimestampMixin


class DataSource(Base, TimestampMixin):
    """A logical origin of data (a scanning batch, an ERP export, a bank feed)."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)  # csv/excel/ocr/api/manual
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataImport(Base, TimestampMixin):
    """One ingestion run. Supports incremental, batched historical migration."""

    __tablename__ = "data_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=ImportStatus.UPLOADED.value)
    rows_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_imported: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Document(Base, TimestampMixin):
    """An archived source document (e.g. a scanned paper invoice, spec §12).

    The original artefact is always retained; OCR output is added later without
    overwriting it.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=DocumentStatus.UPLOADED.value)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_import_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
