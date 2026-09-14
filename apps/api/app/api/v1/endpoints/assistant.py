from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user
from app.models.user import User
from app.services.ai.assistant import ask
from app.services.ai.tools import tool_catalog
from app.services.ai.transcribe import TranscriptionUnavailable, transcribe_wav

# Guard against oversized uploads (a minute of 16 kHz mono 16-bit ≈ 1.9 MB).
_MAX_AUDIO_BYTES = 15 * 1024 * 1024

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
