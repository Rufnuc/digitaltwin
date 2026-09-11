"""Generic CRUD router factory.

Produces list/get/create/update/delete for a model with consistent pagination,
RBAC and audit logging, so the many simple business entities don't each
reimplement the same handlers. Bespoke resources (invoices, simulations) have
their own modules.

NOTE: this module deliberately does NOT use ``from __future__ import annotations``.
The CRUD routes annotate their body param with a *closure variable* holding a
Pydantic model class; FastAPI must see the real class object at decoration time,
not a deferred string, to bind it as a request body.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, Role
from app.models.user import User
from app.services import audit


def build_crud_router(
    *,
    model: type,
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    out_schema: type[BaseModel],
    entity_type: str,
    tags: list[str],
    write_role: Role = Role.STAFF,
    delete_role: Role = Role.MANAGER,
    search_fields: tuple[str, ...] = ("name",),
) -> APIRouter:
    router = APIRouter(tags=tags)

    @router.get("", response_model=dict)
    def list_items(
        db: Session = Depends(db_session),
        _: User = Depends(get_current_user),
        limit: int = Query(50, le=200),
        offset: int = Query(0, ge=0),
        q: str | None = None,
    ) -> Any:
        stmt = select(model)
        if q and search_fields:
            like = f"%{q}%"
            conditions = [getattr(model, f).ilike(like) for f in search_fields if hasattr(model, f)]
            if conditions:
                from sqlalchemy import or_

                stmt = stmt.where(or_(*conditions))
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = db.scalars(stmt.order_by(model.id).limit(limit).offset(offset)).all()
        return {
            "items": [out_schema.model_validate(r).model_dump() for r in rows],
            "total": int(total or 0),
            "limit": limit,
            "offset": offset,
        }

    @router.get("/{item_id}", response_model=out_schema)
    def get_item(
        item_id: int,
        db: Session = Depends(db_session),
        _: User = Depends(get_current_user),
    ) -> Any:
        obj = db.get(model, item_id)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{entity_type} {item_id} not found")
        return obj

    @router.post("", response_model=out_schema, status_code=status.HTTP_201_CREATED)
    def create_item(
        payload: create_schema,  # type: ignore[valid-type]
        db: Session = Depends(db_session),
        user: User = Depends(require_role(write_role)),
    ) -> Any:
        obj = model(**payload.model_dump())
        db.add(obj)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"{entity_type} conflicts with an existing record"
            ) from None
        db.refresh(obj)
        audit.record(
            db,
            action=AuditAction.CREATE,
            user_id=user.id,
            entity_type=entity_type,
            entity_id=obj.id,
            new_value=payload.model_dump(mode="json"),
        )
        return obj

    @router.patch("/{item_id}", response_model=out_schema)
    def update_item(
        item_id: int,
        payload: update_schema,  # type: ignore[valid-type]
        db: Session = Depends(db_session),
        user: User = Depends(require_role(write_role)),
    ) -> Any:
        obj = db.get(model, item_id)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{entity_type} {item_id} not found")
        changes = payload.model_dump(exclude_unset=True)
        old = {k: getattr(obj, k) for k in changes}
        for k, v in changes.items():
            setattr(obj, k, v)
        db.commit()
        db.refresh(obj)
        audit.record(
            db,
            action=AuditAction.UPDATE,
            user_id=user.id,
            entity_type=entity_type,
            entity_id=obj.id,
            old_value={k: str(v) for k, v in old.items()},
            new_value={k: str(v) for k, v in changes.items()},
        )
        return obj

    @router.delete(
        "/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
    )
    def delete_item(
        item_id: int,
        db: Session = Depends(db_session),
        user: User = Depends(require_role(delete_role)),
    ) -> Response:
        obj = db.get(model, item_id)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{entity_type} {item_id} not found")
        db.delete(obj)
        db.commit()
        audit.record(
            db,
            action=AuditAction.DELETE,
            user_id=user.id,
            entity_type=entity_type,
            entity_id=item_id,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
