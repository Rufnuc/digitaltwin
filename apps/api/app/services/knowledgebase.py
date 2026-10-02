"""Knowledgebase articles with full version history. Every create/edit/restore writes
an immutable version snapshot and an activity-log entry, so changes are tracked in
real time with a version number attached."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.knowledge import KbArticle, KbArticleVersion, KbFeedback
from app.models.user import User
from app.services import audit


def _user_names(db: Session) -> dict[int, str]:
    return {u.id: (u.full_name or u.email)
            for u in db.query(User.id, User.full_name, User.email).all()}


def _excerpt(body: str, n: int = 160) -> str:
    """Plain-text preview of an article body (markdown stripped)."""
    text = body or ""
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)      # headings
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)      # links → text
    text = re.sub(r"[*`>#]", "", text)                        # emphasis/code marks
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:n] + "…") if len(text) > n else text


def _snapshot(db: Session, art: KbArticle, *, user_id: int | None, note: str | None) -> None:
    db.add(KbArticleVersion(
        article_id=art.id, version_no=art.version_no, title=art.title, body=art.body,
        change_note=note, changed_by_user_id=user_id,
    ))


def _clean_tags(tags) -> list[str]:
    if not tags:
        return []
    return [t.strip() for t in tags if isinstance(t, str) and t.strip()][:12]


def create_article(db: Session, *, title: str, body: str, category: str | None,
                   user_id: int | None, tags: list[str] | None = None,
                   internal: bool = False) -> KbArticle:
    art = KbArticle(title=title, body=body or "", category=category,
                    tags=_clean_tags(tags), internal=internal, version_no=1,
                    created_by_user_id=user_id, updated_by_user_id=user_id)
    db.add(art)
    db.flush()
    _snapshot(db, art, user_id=user_id, note="created")
    audit.record(db, action="KB_EDIT", user_id=user_id, entity_type="kb_article",
                 entity_id=art.id, summary=f"Knowledgebase: created '{title}' (v1)",
                 commit=False)
    db.commit()
    db.refresh(art)
    return art


def update_article(db: Session, *, article_id: int, title: str | None, body: str | None,
                   category: str | None, note: str | None, user_id: int | None,
                   tags: list[str] | None = None,
                   internal: bool | None = None) -> KbArticle | None:
    art = db.get(KbArticle, article_id)
    if art is None:
        return None
    if title is not None:
        art.title = title
    if body is not None:
        art.body = body
    if category is not None:
        art.category = category
    if tags is not None:
        art.tags = _clean_tags(tags)
    if internal is not None:
        art.internal = internal
    art.version_no += 1
    art.updated_by_user_id = user_id
    db.flush()
    _snapshot(db, art, user_id=user_id, note=note or "edited")
    audit.record(db, action="KB_EDIT", user_id=user_id, entity_type="kb_article",
                 entity_id=art.id,
                 summary=f"Knowledgebase: edited '{art.title}' → v{art.version_no}"
                         + (f" ({note})" if note else ""),
                 commit=False)
    db.commit()
    db.refresh(art)
    return art


def restore_version(db: Session, *, article_id: int, version_no: int,
                    user_id: int | None) -> KbArticle | None:
    art = db.get(KbArticle, article_id)
    if art is None:
        return None
    snap = db.scalar(select(KbArticleVersion).where(
        KbArticleVersion.article_id == article_id, KbArticleVersion.version_no == version_no
    ))
    if snap is None:
        return None
    art.title = snap.title
    art.body = snap.body
    art.version_no += 1
    art.updated_by_user_id = user_id
    db.flush()
    _snapshot(db, art, user_id=user_id, note=f"restored v{version_no}")
    audit.record(db, action="KB_EDIT", user_id=user_id, entity_type="kb_article",
                 entity_id=art.id,
                 summary=f"Knowledgebase: restored '{art.title}' to v{version_no} "
                         f"(now v{art.version_no})",
                 commit=False)
    db.commit()
    db.refresh(art)
    return art


def archive_article(db: Session, *, article_id: int, user_id: int | None) -> bool:
    art = db.get(KbArticle, article_id)
    if art is None:
        return False
    art.archived_at = datetime.now(timezone.utc)
    art.updated_by_user_id = user_id
    audit.record(db, action="KB_EDIT", user_id=user_id, entity_type="kb_article",
                 entity_id=art.id, summary=f"Knowledgebase: archived '{art.title}'",
                 commit=False)
    db.commit()
    return True


def set_pinned(db: Session, *, article_id: int, pinned: bool, user_id: int | None) -> bool:
    art = db.get(KbArticle, article_id)
    if art is None:
        return False
    art.pinned = pinned
    audit.record(db, action="KB_EDIT", user_id=user_id, entity_type="kb_article",
                 entity_id=art.id,
                 summary=f"Knowledgebase: {'pinned' if pinned else 'unpinned'} '{art.title}'",
                 commit=False)
    db.commit()
    return True


def record_feedback(db: Session, *, article_id: int, user_id: int, helpful: bool) -> dict | None:
    art = db.get(KbArticle, article_id)
    if art is None:
        return None
    existing = db.scalar(select(KbFeedback).where(
        KbFeedback.article_id == article_id, KbFeedback.user_id == user_id
    ))
    if existing is None:
        db.add(KbFeedback(article_id=article_id, user_id=user_id, helpful=helpful))
        if helpful:
            art.helpful_yes = (art.helpful_yes or 0) + 1
        else:
            art.helpful_no = (art.helpful_no or 0) + 1
    elif existing.helpful != helpful:
        existing.helpful = helpful
        if helpful:
            art.helpful_yes = (art.helpful_yes or 0) + 1
            art.helpful_no = max(0, (art.helpful_no or 0) - 1)
        else:
            art.helpful_no = (art.helpful_no or 0) + 1
            art.helpful_yes = max(0, (art.helpful_yes or 0) - 1)
    db.commit()
    return {"helpful_yes": art.helpful_yes, "helpful_no": art.helpful_no, "my_vote": helpful}


def list_articles(db: Session, *, q: str | None = None, category: str | None = None,
                  tag: str | None = None, include_archived: bool = False,
                  is_dev: bool = False) -> tuple[list[dict], list[str], list[str]]:
    stmt = select(KbArticle)
    if not include_archived:
        stmt = stmt.where(KbArticle.archived_at.is_(None))
    if not is_dev:
        stmt = stmt.where(KbArticle.internal.is_(False))  # hide dev-only articles
    if q:
        like = f"%{q}%"
        stmt = stmt.where(KbArticle.title.ilike(like) | KbArticle.body.ilike(like))
    if category:
        stmt = stmt.where(KbArticle.category == category)
    # Pinned first, then most recently updated.
    rows = db.scalars(stmt.order_by(KbArticle.pinned.desc(), KbArticle.updated_at.desc())).all()
    if tag:
        rows = [a for a in rows if tag in (a.tags or [])]
    names = _user_names(db)
    cats = [c for (c,) in db.execute(
        select(KbArticle.category).where(KbArticle.category.is_not(None)).distinct()
    ).all()]
    all_tags = sorted({t for a in rows for t in (a.tags or [])})
    items = [{
        "id": a.id, "title": a.title, "category": a.category, "tags": a.tags or [],
        "excerpt": _excerpt(a.body), "pinned": bool(a.pinned), "internal": bool(a.internal),
        "version_no": a.version_no,
        "helpful_yes": a.helpful_yes or 0, "helpful_no": a.helpful_no or 0,
        "updated_by": names.get(a.updated_by_user_id),
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "archived": a.archived_at is not None,
    } for a in rows]
    return items, sorted(cats), all_tags


def get_article(db: Session, article_id: int, *, user_id: int | None = None,
                is_dev: bool = False) -> dict | None:
    a = db.get(KbArticle, article_id)
    if a is None:
        return None
    if a.internal and not is_dev:
        return None  # developer-only article is invisible to the owner/staff
    names = _user_names(db)
    my_vote = None
    if user_id is not None:
        fb = db.scalar(select(KbFeedback).where(
            KbFeedback.article_id == article_id, KbFeedback.user_id == user_id
        ))
        my_vote = fb.helpful if fb else None
    return {
        "id": a.id, "title": a.title, "category": a.category, "tags": a.tags or [],
        "body": a.body, "version_no": a.version_no, "pinned": bool(a.pinned),
        "internal": bool(a.internal),
        "helpful_yes": a.helpful_yes or 0, "helpful_no": a.helpful_no or 0,
        "my_vote": my_vote,
        "created_by": names.get(a.created_by_user_id),
        "updated_by": names.get(a.updated_by_user_id),
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "archived": a.archived_at is not None,
    }


def list_versions(db: Session, article_id: int) -> list[dict]:
    names = _user_names(db)
    rows = db.scalars(
        select(KbArticleVersion).where(KbArticleVersion.article_id == article_id)
        .order_by(KbArticleVersion.version_no.desc())
    ).all()
    return [{
        "version_no": v.version_no, "title": v.title, "body": v.body,
        "change_note": v.change_note,
        "changed_by": names.get(v.changed_by_user_id),
        "changed_at": v.created_at.isoformat() if v.created_at else None,
    } for v in rows]
