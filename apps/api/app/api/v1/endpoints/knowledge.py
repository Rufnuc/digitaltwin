from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.config import settings
from app.core.enums import Role
from app.models.user import User
from app.services import knowledgebase as kb
from app.services.storage import StorageError, get_storage

router = APIRouter(tags=["knowledge"], prefix="/kb")

# Knowledgebase is managers-only (read and write).
_mgr = require_role(Role.MANAGER)


def _is_dev(user: User) -> bool:
    """A vendor/developer account — can see 'internal' (dev-only) articles."""
    return bool(user.email and user.email.lower() in settings.developer_emails)


class ArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = ""
    category: str | None = None
    tags: list[str] | None = None
    internal: bool = False


class ArticlePatch(BaseModel):
    title: str | None = Field(None, max_length=255)
    body: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    internal: bool | None = None
    change_note: str | None = Field(None, max_length=255)


class PinIn(BaseModel):
    pinned: bool = True


class FeedbackIn(BaseModel):
    helpful: bool


@router.get("/articles")
def list_articles(
    db: Session = Depends(db_session),
    user: User = Depends(_mgr),
    q: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    include_archived: bool = False,
) -> dict:
    is_dev = _is_dev(user)
    items, categories, tags = kb.list_articles(
        db, q=q, category=category, tag=tag, include_archived=include_archived, is_dev=is_dev)
    return {"items": items, "categories": categories, "tags": tags, "is_developer": is_dev}


@router.post("/articles", status_code=status.HTTP_201_CREATED)
def create_article(
    payload: ArticleIn, db: Session = Depends(db_session), user: User = Depends(_mgr)
) -> dict:
    is_dev = _is_dev(user)
    art = kb.create_article(db, title=payload.title, body=payload.body,
                            category=payload.category, tags=payload.tags,
                            internal=payload.internal and is_dev,  # only devs mark internal
                            user_id=user.id)
    return kb.get_article(db, art.id, user_id=user.id, is_dev=is_dev)


@router.get("/articles/{article_id}")
def get_article(
    article_id: int, db: Session = Depends(db_session), user: User = Depends(_mgr)
) -> dict:
    art = kb.get_article(db, article_id, user_id=user.id, is_dev=_is_dev(user))
    if art is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    return art


@router.patch("/articles/{article_id}")
def update_article(
    article_id: int, payload: ArticlePatch,
    db: Session = Depends(db_session), user: User = Depends(_mgr),
) -> dict:
    is_dev = _is_dev(user)
    # Only a developer may change the internal flag; others leave it untouched.
    internal = payload.internal if is_dev else None
    art = kb.update_article(db, article_id=article_id, title=payload.title,
                            body=payload.body, category=payload.category, tags=payload.tags,
                            internal=internal, note=payload.change_note, user_id=user.id)
    if art is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    return kb.get_article(db, article_id, user_id=user.id, is_dev=is_dev)


@router.get("/articles/{article_id}/versions")
def article_versions(
    article_id: int, db: Session = Depends(db_session), user: User = Depends(_mgr)
) -> dict:
    if kb.get_article(db, article_id, is_dev=_is_dev(user)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    return {"items": kb.list_versions(db, article_id)}


@router.post("/articles/{article_id}/archive")
def archive_article(
    article_id: int, db: Session = Depends(db_session), user: User = Depends(_mgr)
) -> dict:
    if not kb.archive_article(db, article_id=article_id, user_id=user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    return {"status": "OK"}


@router.post("/articles/{article_id}/pin")
def pin_article(
    article_id: int, payload: PinIn,
    db: Session = Depends(db_session), user: User = Depends(_mgr),
) -> dict:
    if not kb.set_pinned(db, article_id=article_id, pinned=payload.pinned, user_id=user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    return {"status": "OK", "pinned": payload.pinned}


@router.post("/articles/{article_id}/feedback")
def article_feedback(
    article_id: int, payload: FeedbackIn,
    db: Session = Depends(db_session), user: User = Depends(_mgr),
) -> dict:
    if kb.get_article(db, article_id, is_dev=_is_dev(user)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    res = kb.record_feedback(db, article_id=article_id, user_id=user.id, helpful=payload.helpful)
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    return res


# --------------------------------------------------------------------------- #
# Article images: upload (managers) returns a URL; serving is public by opaque key
# so <img src> in an article loads without an auth header (keys are unguessable).
# --------------------------------------------------------------------------- #
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024


@router.post("/images", status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    _: User = Depends(_mgr),
) -> dict:
    data = await file.read()
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "image too large (max 5MB)")
    ctype = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if ctype not in _IMAGE_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "only image files are allowed")
    key = get_storage().save(data, file.filename or "image", ctype)
    return {"key": key, "url": f"/api/v1/kb/images/{key}"}


_ASSETS_DIR = Path(__file__).resolve().parents[3] / "kb_assets"


@router.get("/assets/{name}")
def get_asset(name: str) -> Response:
    """Serve a bundled guide illustration (public, read-only). Whitelisted by filename."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad asset name")
    path = _ASSETS_DIR / name
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "asset not found")
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return Response(content=path.read_bytes(), media_type=ctype,
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/images/{key}")
def get_image(key: str) -> Response:
    # Public by design: embedded <img> can't send an auth header. Keys are opaque.
    try:
        data = get_storage().read(key)
    except StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "image not found") from None
    ctype = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(content=data, media_type=ctype,
                    headers={"Cache-Control": "public, max-age=86400"})
