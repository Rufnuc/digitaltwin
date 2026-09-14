from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import Role
from app.models.company import CompanyProfile
from app.models.user import User

router = APIRouter(tags=["company"])


class CompanyIn(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    tax_id: str | None = None
    website: str | None = None
    footer_note: str | None = None


def _get(db: Session) -> CompanyProfile:
    row = db.get(CompanyProfile, 1)
    if row is None:
        row = CompanyProfile(id=1, name="")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _dump(c: CompanyProfile) -> dict:
    return {"name": c.name, "address": c.address, "phone": c.phone, "email": c.email,
            "tax_id": c.tax_id, "website": c.website, "footer_note": c.footer_note}


@router.get("/company")
def get_company(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    return _dump(_get(db))


@router.put("/company")
def update_company(
    payload: CompanyIn,
    db: Session = Depends(db_session),
    _: User = Depends(require_role(Role.OWNER)),
) -> dict:
    row = _get(db)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _dump(row)
