from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user
from app.models.user import User
from app.services.ai import history
from app.services.ai.assistant import ask
from app.services.ai.tools import tool_catalog
from app.services.ai.transcribe import TranscriptionUnavailable, transcribe_wav

# Guard against oversized uploads (a minute of 16 kHz mono 16-bit ≈ 1.9 MB).
_MAX_AUDIO_BYTES = 15 * 1024 * 1024

router = APIRouter(tags=["assistant"])


class AssistantAsk(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # Continue an existing chat, or omit/null to start a new one.
    conversation_id: int | None = None


class RenameChat(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class AssistantConfirm(BaseModel):
    confirmation_token: str = Field(min_length=1, max_length=4096)


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
    result = ask(db, payload.question, user=user)
    # Persist the turn as chat history (per user), continuing or starting a chat.
    convo = history.save_turn(
        db,
        user_id=user.id if user else None,
        conversation_id=payload.conversation_id,
        response=result,
    )
    result["conversation_id"] = convo.id
    result["conversation_title"] = convo.title
    return result


@router.post("/assistant/confirm")
def assistant_confirm(
    payload: AssistantConfirm,
    db: Session = Depends(db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Execute a previously PROPOSED assistant write. The token fixes exactly what
    runs; the kill switch and role checks are re-applied at execution."""
    from app.services.ai import confirm as confirm_mod
    from app.services.ai.tools import execute_tool

    data = confirm_mod.verify_token(payload.confirmation_token)
    if data is None:
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation.")
    if data.get("user_id") is not None and data["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="This confirmation belongs to another user.")
    result = execute_tool(db, data["name"], data["args"], user=user, confirmed=True)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"executed": data["name"], "result": result}


@router.get("/assistant/conversations")
def list_conversations(
    db: Session = Depends(db_session),
    user: User = Depends(get_current_user),
) -> dict:
    return {"items": history.list_conversations(db, user.id if user else None)}


@router.get("/assistant/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int,
    db: Session = Depends(db_session),
    user: User = Depends(get_current_user),
) -> dict:
    convo = history.get_conversation(db, user.id if user else None, conversation_id)
    if convo is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return convo


@router.patch("/assistant/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: int,
    payload: RenameChat,
    db: Session = Depends(db_session),
    user: User = Depends(get_current_user),
) -> dict:
    if not history.rename_conversation(
        db, user.id if user else None, conversation_id, payload.title
    ):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"ok": True}


@router.delete("/assistant/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(db_session),
    user: User = Depends(get_current_user),
) -> dict:
    if not history.delete_conversation(db, user.id if user else None, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"ok": True}


@router.post("/assistant/transcribe")
async def assistant_transcribe(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
) -> dict:
    """Transcribe an uploaded 16 kHz mono WAV to text with local Whisper.

    Runs fully offline (no API key). Voice never leaves the machine.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio upload.")
    if len(data) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio too long — keep it under a minute.")
    try:
        return transcribe_wav(data)
    except TranscriptionUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
