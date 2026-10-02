"""Knowledgebase articles with full version history. Every create/edit/restore writes
an immutable version snapshot and an activity-log entry, so changes are tracked in
real time with a version number attached."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.knowledge import KbArticle, KbArticleVersion
from app.models.user import User
from app.services import audit


def _user_names(db: Session) -> dict[int, str]:
    return {u.id: (u.full_name or u.email)
            for u in db.query(User.id, User.full_name, User.email).all()}


def _snapshot(db: Session, art: KbArticle, *, user_id: int | None, note: str | None) -> None:
    db.add(KbArticleVersion(
        article_id=art.id, version_no=art.version_no, title=art.title, body=art.body,
        change_note=note, changed_by_user_id=user_id,
    ))


def create_article(db: Session, *, title: str, body: str, category: str | None,
                   user_id: int | None) -> KbArticle:
    art = KbArticle(title=title, body=body or "", category=category, version_no=1,
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
                   category: str | None, note: str | None, user_id: int | None) -> KbArticle | None:
    art = db.get(KbArticle, article_id)
    if art is None:
        return None
    if title is not None:
        art.title = title
    if body is not None:
        art.body = body
    if category is not None:
        art.category = category
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


def list_articles(db: Session, *, q: str | None = None, category: str | None = None,
                  include_archived: bool = False) -> list[dict]:
    stmt = select(KbArticle)
    if not include_archived:
        stmt = stmt.where(KbArticle.archived_at.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(KbArticle.title.ilike(like) | KbArticle.body.ilike(like))
    if category:
        stmt = stmt.where(KbArticle.category == category)
    rows = db.scalars(stmt.order_by(KbArticle.updated_at.desc())).all()
    names = _user_names(db)
    cats = [c for (c,) in db.execute(
        select(KbArticle.category).where(KbArticle.category.is_not(None)).distinct()
    ).all()]
    return [{
        "id": a.id, "title": a.title, "category": a.category,
        "version_no": a.version_no,
        "updated_by": names.get(a.updated_by_user_id),
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "archived": a.archived_at is not None,
    } for a in rows], sorted(cats)


def get_article(db: Session, article_id: int) -> dict | None:
    a = db.get(KbArticle, article_id)
    if a is None:
        return None
    names = _user_names(db)
    return {
        "id": a.id, "title": a.title, "category": a.category, "body": a.body,
        "version_no": a.version_no,
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
