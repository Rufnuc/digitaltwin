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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import Role
from app.core.security import role_at_least
from app.models.user import User

# Query params handled explicitly by list endpoints (never treated as filters).
_RESERVED = {"limit", "offset", "q", "sort", "sort_dir"}

# Fields that must not be changed by a casual STAFF edit (MANAGER+ only), per resource.
_SENSITIVE_FIELDS: dict[str, set[str]] = {
    "customer": {"credit_limit", "payment_terms_days"},
    "supplier": {"reliability_score"},
}


def _delete_blocker(db: Session, entity_type: str, item_id: int) -> str | None:
    """Return a description of the financial/stock records referencing this entity,
    or None if it is safe to delete. Prevents orphaning invoices, lots or payments."""
    from sqlalchemy import func, select

    from app.models.invoice import Invoice, InvoiceLine
    from app.models.payment import Payment
    from app.models.purchase import Purchase, SupplierPayment
    from app.models.warehouse import StockLot, StockMovement

    refs: dict[str, list[tuple]] = {
        "product": [("invoice lines", InvoiceLine, InvoiceLine.product_id),
                    ("stock lots", StockLot, StockLot.product_id),
                    ("stock movements", StockMovement, StockMovement.product_id)],
        "customer": [("invoices", Invoice, Invoice.customer_id),
                     ("payments", Payment, Payment.customer_id)],
        "supplier": [("stock lots", StockLot, StockLot.supplier_id),
                     ("purchases", Purchase, Purchase.supplier_id),
                     ("supplier payments", SupplierPayment, SupplierPayment.supplier_id)],
        "warehouse": [("stock lots", StockLot, StockLot.warehouse_id),
                      ("stock movements", StockMovement, StockMovement.warehouse_id)],
    }
    for label, model, col in refs.get(entity_type, []):
        n = db.scalar(select(func.count()).select_from(model).where(col == item_id))
        if n:
            return f"{n} {label}"
    return None


def _archive(obj) -> bool:
    """Soft-delete via an existing status/flag column. Returns True if archived (so
    the caller skips the hard delete), False if the model has no archive field."""
    from app.core.enums import EntityStatus

    if hasattr(obj, "status"):
        obj.status = EntityStatus.ARCHIVED.value
        return True
    if hasattr(obj, "is_active"):
        obj.is_active = False
        return True
    return False


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
    auto_code_prefix: str | None = None,
    writable: bool = True,
) -> APIRouter:
    """When ``writable`` is False only the read routes are exposed — used for stock
    Inventory, whose quantities are owned by the lot ledger and must never be edited
    directly (that would bypass the audited stock-movement trail)."""
    router = APIRouter(tags=tags)

    columns = set(model.__table__.columns.keys())

    def _next_code(db: Session) -> str:
        """Generate the next sequential code like PREFIX0001, filling gaps safely."""
        rows = db.scalars(select(model.code)).all()  # type: ignore[attr-defined]
        n = 0
        for c in rows:
            if c and c.startswith(auto_code_prefix):
                try:
                    n = max(n, int(c[len(auto_code_prefix):]))
                except ValueError:
                    continue
        return f"{auto_code_prefix}{n + 1:04d}"

    @router.get("", response_model=dict)
    def list_items(
        request: Request,
        db: Session = Depends(db_session),
        _: User = Depends(get_current_user),
        limit: int = Query(50, le=200),
        offset: int = Query(0, ge=0),
        q: str | None = None,
        sort: str | None = Query(None, description="column to sort by (default id)"),
        sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    ) -> Any:
        stmt = select(model)

        # Full-text-ish search across the configured search fields.
        if q and search_fields:
            like = f"%{q}%"
            conditions = [getattr(model, f).ilike(like) for f in search_fields if hasattr(model, f)]
            if conditions:
                stmt = stmt.where(or_(*conditions))

        # Field filters: any query param matching a model column (?status=ACTIVE).
        applied_filters: dict[str, str] = {}
        for key, value in request.query_params.items():
            if key in _RESERVED or key not in columns or value == "":
                continue
            col = getattr(model, key)
            pytype = col.type.python_type
            if pytype is str:
                # String columns filter case-insensitively.
                stmt = stmt.where(func.lower(col) == value.lower())
            elif pytype is bool:
                stmt = stmt.where(col == (value.lower() in ("true", "1", "yes")))
            else:
                try:
                    stmt = stmt.where(col == pytype(value))
                except (TypeError, ValueError):
                    continue  # ignore un-coercible filter value
            applied_filters[key] = value

        total = db.scalar(select(func.count()).select_from(stmt.subquery()))

        # Sorting: validated column name, else fall back to id.
        sort_col = getattr(model, sort) if sort in columns else model.id
        stmt = stmt.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

        rows = db.scalars(stmt.limit(limit).offset(offset)).all()
        return {
            "items": [out_schema.model_validate(r).model_dump() for r in rows],
            "total": int(total or 0),
            "limit": limit,
            "offset": offset,
            "sort": sort or "id",
            "sort_dir": sort_dir,
            "filters": applied_filters,
            "sortable_fields": sorted(columns),
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

    if writable:
        @router.post("", response_model=out_schema, status_code=status.HTTP_201_CREATED)
        def create_item(
            payload: create_schema,  # type: ignore[valid-type]
            db: Session = Depends(db_session),
            user: User = Depends(require_role(write_role)),
        ) -> Any:
            data = payload.model_dump()
            data.pop("data_origin", None)  # provenance is never client-settable
            # Auto-generate the code when the resource opts in and none was supplied.
            if auto_code_prefix and not data.get("code"):
                data["code"] = _next_code(db)
            obj = model(**data)
            db.add(obj)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(
                    status.HTTP_409_CONFLICT, f"{entity_type} conflicts with an existing record"
                ) from None
            db.refresh(obj)
            # The change is recorded automatically by the audit-trail listener.
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
            # Provenance/verification are governed by the import + verify flow, never a
            # casual edit; drop them from generic updates.
            for protected in ("data_origin", "verification_status"):
                changes.pop(protected, None)
            # Sensitive fields (credit limits, reliability scores) need MANAGER+.
            touched_sensitive = _SENSITIVE_FIELDS.get(entity_type, set()) & set(changes)
            if touched_sensitive and not role_at_least(user.role, Role.MANAGER):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    f"changing {', '.join(sorted(touched_sensitive))} requires MANAGER or higher",
                )
            for k, v in changes.items():
                setattr(obj, k, v)
            db.commit()  # before→after captured automatically by the audit-trail listener
            db.refresh(obj)
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
            # Refuse to destroy a record that financial/stock history points at — that
            # would orphan invoices, lots or payments. Archive instead where possible.
            blocker = _delete_blocker(db, entity_type, item_id)
            if blocker:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"cannot delete this {entity_type}: it is referenced by {blocker}. "
                    "Archive it instead.",
                )
            archived = _archive(obj)
            if archived:
                db.commit()  # soft-delete: recorded by the audit-trail listener
                return Response(status_code=status.HTTP_204_NO_CONTENT)
            db.delete(obj)
            db.commit()  # deletion recorded automatically by the audit-trail listener
            return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
