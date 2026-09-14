"""Persisted Benfieg chat history (spec §32 follow-up).

Each user keeps their own conversations. A conversation is an ordered list of
messages (the user's question and Benfieg's answer). Assistant messages also
store the tool trace and provenance in `meta`, so a reopened conversation renders
exactly as it did live — including the data-sources panel and Export PDF — with
the sourcing intact. Nothing here invents data; it only records what was shown.
"""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class AssistantConversation(Base, TimestampMixin):
    __tablename__ = "assistant_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="New chat")

    messages: Mapped[list[AssistantMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AssistantMessage.id",
    )


class AssistantMessage(Base, TimestampMixin):
    __tablename__ = "assistant_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, default="")
    # For assistant messages: {provider, model, provenance, tool_calls,
    # actions_taken, disclaimer}. Null for user messages.
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    conversation: Mapped[AssistantConversation] = relationship(back_populates="messages")
