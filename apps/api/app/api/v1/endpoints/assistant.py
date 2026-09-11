from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user
from app.models.user import User
from app.services.ai.assistant import ask
from app.services.ai.tools import tool_catalog

router = APIRouter(tags=["assistant"])


class AssistantAsk(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@router.get("/assistant/tools")
def tools(_: User = Depends(get_current_user)) -> dict:
    """The tools the assistant can call — the only source of numbers in answers."""
    return {"tools": tool_catalog()}


@router.post("/assistant/ask")
def assistant_ask(
    payload: AssistantAsk,
    db: Session = Depends(db_session),
    user: User = Depends(get_current_user),
) -> dict:
    return ask(db, payload.question, user=user)
