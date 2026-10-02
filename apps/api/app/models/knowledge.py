"""Internal knowledgebase: versioned articles (SOPs, policies, notes). Every save
keeps an immutable snapshot with a version number, so changes are fully tracked and
any prior version can be viewed or restored."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class KbArticle(Base, TimestampMixin):
    __tablename__ = "kb_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    # Marks an article created by the content seed (and which seed version), so the
    # seed can refresh its own articles on deploy without touching human-written ones.
    seed_tag: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )

    versions: Mapped[list[KbArticleVersion]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class KbArticleVersion(Base):
    """An immutable snapshot of an article at one version."""

    __tablename__ = "kb_article_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("kb_articles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    change_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    article: Mapped[KbArticle] = relationship(back_populates="versions")
