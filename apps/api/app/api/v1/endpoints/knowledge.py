from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import db_session, require_role
from app.core.enums import Role
from app.models.user import User
from app.services import knowledgebase as kb

router = APIRouter(tags=["knowledge"], prefix="/kb")

# Knowledgebase is managers-only (read and write).
_mgr = require_role(Role.MANAGER)


class ArticleIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = ""
    category: str | None = None


class ArticlePatch(BaseModel):
    title: str | None = Field(None, max_length=255)
    body: str | None = None
    category: str | None = None
    change_note: str | None = Field(None, max_length=255)


@router.get("/articles")
def list_articles(
    db: Session = Depends(db_session),
    _: User = Depends(_mgr),
    q: str | None = None,
    category: str | None = None,
    include_archived: bool = False,
) -> dict:
    items, categories = kb.list_articles(db, q=q, category=category,
                                         include_archived=include_archived)
    return {"items": items, "categories": categories}


@router.post("/articles", status_code=status.HTTP_201_CREATED)
def create_article(
    payload: ArticleIn, db: Session = Depends(db_session), user: User = Depends(_mgr)
) -> dict:
    art = kb.create_article(db, title=payload.title, body=payload.body,
                            category=payload.category, user_id=user.id)
    return kb.get_article(db, art.id)


@router.get("/articles/{article_id}")
def get_article(
    article_id: int, db: Session = Depends(db_session), _: User = Depends(_mgr)
) -> dict:
    art = kb.get_article(db, article_id)
    if art is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    return art


@router.patch("/articles/{article_id}")
def update_article(
    article_id: int, payload: ArticlePatch,
    db: Session = Depends(db_session), user: User = Depends(_mgr),
) -> dict:
    art = kb.update_article(db, article_id=article_id, title=payload.title,
                            body=payload.body, category=payload.category,
                            note=payload.change_note, user_id=user.id)
    if art is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    return kb.get_article(db, article_id)


@router.get("/articles/{article_id}/versions")
def article_versions(
    article_id: int, db: Session = Depends(db_session), _: User = Depends(_mgr)
) -> dict:
    return {"items": kb.list_versions(db, article_id)}


@router.post("/articles/{article_id}/restore/{version_no}")
def restore_version(
    article_id: int, version_no: int,
    db: Session = Depends(db_session), user: User = Depends(_mgr),
) -> dict:
    art = kb.restore_version(db, article_id=article_id, version_no=version_no, user_id=user.id)
    if art is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article or version not found")
    return kb.get_article(db, article_id)


@router.post("/articles/{article_id}/archive")
def archive_article(
    article_id: int, db: Session = Depends(db_session), user: User = Depends(_mgr)
) -> dict:
    if not kb.archive_article(db, article_id=article_id, user_id=user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "article not found")
    return {"status": "OK"}
