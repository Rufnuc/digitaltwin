"""Database-management endpoints (spec §42, §43).

Lets an owner inspect what's in the database and clear out the DEMO data before
loading real records — the demo/real boundary is exactly the DataOrigin tag, so a
purge is precise and never touches real data.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user, require_role
from app.core.enums import AuditAction, DataOrigin, Role
from app.models.customer import Customer
from app.models.events import EconomicData, MarketEvent
from app.models.expense import Expense
from app.models.inventory import Inventory
from app.models.invoice import Invoice, InvoiceLine
from app.models.payment import Payment
from app.models.product import Product, ProductPriceHistory
from app.models.purchase import Purchase, PurchaseLine, SupplierPayment
from app.models.supplier import Supplier
from app.models.system import Alert
from app.models.user import User
from app.models.warehouse import StockLot, StockMovement
from app.models.waybill import Waybill
from app.services import audit

router = APIRouter(tags=["admin"])

# Provenance-tagged tables (have a DataOrigin) reported with demo/real split.
_TAGGED = [
    ("customers", Customer), ("products", Product), ("suppliers", Supplier),
    ("invoices", Invoice), ("invoice_lines", InvoiceLine), ("inventory", Inventory),
    ("expenses", Expense), ("market_events", MarketEvent), ("economic_data", EconomicData),
    ("alerts", Alert),
]


def _count(db: Session, model, cond=None) -> int:
    stmt = select(func.count()).select_from(model)
    if cond is not None:
        stmt = stmt.where(cond)
    return int(db.scalar(stmt) or 0)


@router.get("/admin/data-stats")
def data_stats(db: Session = Depends(db_session), _: User = Depends(get_current_user)) -> dict:
    """Row counts per table with a demo-vs-real split where provenance is tracked."""
    demo = DataOrigin.DEMO.value
    tables = []
    total_demo = 0
    for name, model in _TAGGED:
        total = _count(db, model)
        d = _count(db, model, model.data_origin == demo)
        total_demo += d
        tables.append({"table": name, "total": total, "demo": d, "real": total - d})
    return {"tables": tables, "total_demo_rows": total_demo,
            "users": _count(db, User)}


@router.post("/admin/purge-demo")
def purge_demo(
    db: Session = Depends(db_session),
    user: User = Depends(require_role(Role.OWNER)),
) -> dict:
    """Delete all DEMO-origin data so real data can be entered on a clean slate.

    Deletes in FK-safe order. Real (imported/verified) data is untouched. Branches,
    employees and users are not provenance-tagged — manage those from their pages.
    """
    demo = DataOrigin.DEMO.value
    deleted: dict[str, int] = {}

    def purge(model, cond) -> None:
        res = db.execute(delete(model).where(cond))
        deleted[model.__tablename__] = deleted.get(model.__tablename__, 0) + (res.rowcount or 0)

    # Demo parent id sets, used to remove rows that only *reference* demo data (and so
    # carry no provenance tag of their own) — otherwise deleting the parents would
    # orphan them or violate foreign keys.
    demo_products = select(Product.id).where(Product.data_origin == demo)
    demo_invoices = select(Invoice.id).where(Invoice.data_origin == demo)
    demo_customers = select(Customer.id).where(Customer.data_origin == demo)
    demo_suppliers = select(Supplier.id).where(Supplier.data_origin == demo)
    demo_purchases = select(Purchase.id).where(Purchase.data_origin == demo)

    # Everything runs in one transaction (a single commit below) so the purge is
    # atomic — all demo data goes or none does.
    # Stock ledger first (movements reference lots).
    purge(StockMovement,
          StockMovement.product_id.in_(demo_products)
          | StockMovement.invoice_id.in_(demo_invoices)
          | StockMovement.customer_id.in_(demo_customers))
    purge(StockLot,
          (StockLot.data_origin == demo)
          | StockLot.product_id.in_(demo_products)
          | StockLot.supplier_id.in_(demo_suppliers))
    # Dispatch records tied to demo invoices.
    purge(Waybill, Waybill.invoice_id.in_(demo_invoices))
    # Money rows that point at demo invoices/customers/suppliers/purchases.
    purge(Payment,
          (Payment.data_origin == demo)
          | Payment.invoice_id.in_(demo_invoices)
          | Payment.customer_id.in_(demo_customers))
    purge(SupplierPayment,
          (SupplierPayment.data_origin == demo)
          | SupplierPayment.supplier_id.in_(demo_suppliers)
          | SupplierPayment.purchase_id.in_(demo_purchases))
    # Children before parents.
    purge(InvoiceLine, InvoiceLine.data_origin == demo)
    purge(Invoice, Invoice.data_origin == demo)
    purge(PurchaseLine, PurchaseLine.data_origin == demo)
    purge(Purchase, Purchase.data_origin == demo)
    purge(Inventory, Inventory.data_origin == demo)
    # price history has no provenance tag — remove rows for demo products.
    db.execute(delete(ProductPriceHistory).where(
        ProductPriceHistory.product_id.in_(demo_products)
    ))
    purge(Expense, Expense.data_origin == demo)
    purge(Customer, Customer.data_origin == demo)
    purge(Product, Product.data_origin == demo)
    purge(Supplier, Supplier.data_origin == demo)
    purge(MarketEvent, MarketEvent.data_origin == demo)
    purge(EconomicData, EconomicData.data_origin == demo)
    purge(Alert, Alert.data_origin == demo)
    # NOTE: SimulationRun has no product/invoice foreign key and no provenance tag, so
    # no simulation row is ever orphaned by this purge; deleting runs would destroy the
    # operator's real analysis history, so they are intentionally left untouched.
    db.commit()

    total = sum(deleted.values())
    audit.record(db, action=AuditAction.DELETE, user_id=user.id,
                 entity_type="admin:purge_demo", summary=f"purged {total} demo rows")
    return {"deleted": deleted, "total_deleted": total,
            "message": "Demo data removed. You can now enter real business data."}
