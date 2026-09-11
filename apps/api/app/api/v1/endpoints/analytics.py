from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user
from app.models.user import User
from app.services.bi.customers import customer_intelligence
from app.services.bi.data_quality import data_quality_report
from app.services.bi.financials import monthly_pnl
from app.services.bi.products import product_intelligence
from app.services.bi.suppliers import supplier_intelligence

router = APIRouter(tags=["analytics"])


@router.get("/analytics/customers")
def customers(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    return customer_intelligence(db)


@router.get("/analytics/products")
def products(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    return product_intelligence(db)


@router.get("/analytics/suppliers")
def suppliers(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    return supplier_intelligence(db)


@router.get("/analytics/financials")
def financials(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    return monthly_pnl(db)


@router.get("/analytics/data-quality")
def data_quality(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    return data_quality_report(db)
