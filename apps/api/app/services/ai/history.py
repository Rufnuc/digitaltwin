"""Persist and read Benfieg chat history.

Conversations are per-user. Saving a turn records the user's question and the
assistant's answer (with its tool trace + provenance in `meta`) so a reopened
chat renders exactly as it did live. Reads are scoped to the owning user.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.assistant import AssistantConversation, AssistantMessage


def _title_from(question: str) -> str:
    q = " ".join((question or "").split())
    return (q[:60] + "…") if len(q) > 61 else (q or "New chat")


def save_turn(
    db: Session, *, user_id: int | None, conversation_id: int | None, response: dict,
) -> AssistantConversation:
    """Append a question/answer turn, creating the conversation if needed.

    Returns the conversation. If `conversation_id` is given but not owned by the
    user (or missing), a new conversation is started instead of leaking history.
    """
    convo: AssistantConversation | None = None
    if conversation_id is not None:
        convo = db.get(AssistantConversation, conversation_id)
        if convo is not None and convo.user_id != user_id:
            convo = None  # never write into someone else's chat
    if convo is None:
        convo = AssistantConversation(
            user_id=user_id, title=_title_from(response.get("question", "")),
        )
        db.add(convo)
        db.flush()

    db.add(AssistantMessage(
        conversation_id=convo.id, role="user", content=response.get("question", ""),
    ))
    db.add(AssistantMessage(
        conversation_id=convo.id, role="assistant", content=response.get("answer", ""),
        meta={
            "provider": response.get("provider"),
            "model": response.get("model"),
            "provenance": response.get("provenance"),
            "tool_calls": response.get("tool_calls", []),
            "actions_taken": response.get("actions_taken", []),
            "disclaimer": response.get("disclaimer"),
        },
    ))
    # Touch updated_at so the conversation sorts to the top of the list.
    convo.updated_at = func.now()
    db.commit()
    db.refresh(convo)
    return convo


def list_conversations(db: Session, user_id: int | None, limit: int = 50) -> list[dict]:
    counts = (
        select(
            AssistantMessage.conversation_id,
            func.count().label("n"),
        )
        .group_by(AssistantMessage.conversation_id)
        .subquery()
    )
    rows = db.execute(
        select(AssistantConversation, counts.c.n)
        .outerjoin(counts, counts.c.conversation_id == AssistantConversation.id)
        .where(AssistantConversation.user_id == user_id)
        .order_by(AssistantConversation.updated_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "message_count": int(n or 0),
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c, n in rows
    ]


def get_conversation(db: Session, user_id: int | None, conversation_id: int) -> dict | None:
    convo = db.get(AssistantConversation, conversation_id)
    if convo is None or convo.user_id != user_id:
        return None
    msgs = db.scalars(
        select(AssistantMessage)
        .where(AssistantMessage.conversation_id == convo.id)
        .order_by(AssistantMessage.id)
    ).all()
    return {
        "id": convo.id,
        "title": convo.title,
        "created_at": convo.created_at.isoformat(),
        "updated_at": convo.updated_at.isoformat(),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "meta": m.meta,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ],
    }


def rename_conversation(
    db: Session, user_id: int | None, conversation_id: int, title: str,
) -> bool:
    convo = db.get(AssistantConversation, conversation_id)
    if convo is None or convo.user_id != user_id:
        return False
    convo.title = (title or "").strip()[:255] or convo.title
    db.commit()
    return True


def delete_conversation(db: Session, user_id: int | None, conversation_id: int) -> bool:
    convo = db.get(AssistantConversation, conversation_id)
    if convo is None or convo.user_id != user_id:
        return False
    db.delete(convo)
    db.commit()
    return True
