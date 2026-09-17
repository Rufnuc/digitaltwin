"""Business analytics service (spec §16).

All financial calculations live here so they are defined once and reused by the
dashboard, the API and the simulation engine — never duplicated in the frontend.
Pure functions (``pnl``, ``margin``) are separated from DB-backed aggregations so
they can be unit-tested against known deterministic values (spec §46).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import DataOrigin
from app.models.customer import Customer
from app.models.expense import Expense
from app.models.invoice import Invoice, InvoiceLine


# --------------------------------------------------------------------------- #
# Pure calculations (no I/O) — deterministic and unit-tested.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PnL:
    revenue: float
    cogs: float
    operating_expenses: float
    gross_profit: float
    gross_margin: float  # fraction 0..1
    net_profit: float
    net_margin: float


def pnl(revenue: float, cogs: float, operating_expenses: float = 0.0) -> PnL:
    """Core profit-and-loss identity. Example (spec §46):
    revenue=100, cogs=40, opex=20 -> gross_profit=60, net_profit=40."""
    revenue = float(revenue)
    cogs = float(cogs)
    operating_expenses = float(operating_expenses)
    gross_profit = revenue - cogs
    net_profit = gross_profit - operating_expenses
    gross_margin = gross_profit / revenue if revenue else 0.0
    net_margin = net_profit / revenue if revenue else 0.0
    return PnL(
        revenue=revenue,
        cogs=cogs,
        operating_expenses=operating_expenses,
        gross_profit=gross_profit,
        gross_margin=gross_margin,
        net_profit=net_profit,
        net_margin=net_margin,
    )


# --------------------------------------------------------------------------- #
# DB-backed aggregations.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BaselineEconomics:
    """Snapshot of unit economics used as the simulation baseline."""

    revenue: float
    cogs: float
    units: float
    avg_unit_price: float
    avg_unit_cost: float
    gross_profit: float
    gross_margin: float
    order_count: int
    # Total operating expenses over the same window (for net-profit projections).
    # Defaulted so existing positional/keyword constructions stay valid.
    operating_expenses: float = 0.0


def _f(value) -> float:
    return float(value) if value is not None else 0.0


def baseline_economics(db: Session) -> BaselineEconomics:
    """Aggregate unit economics from invoice lines (the simulation baseline)."""
    revenue = _f(db.scalar(select(func.coalesce(func.sum(InvoiceLine.line_total), 0))))
    units = _f(db.scalar(select(func.coalesce(func.sum(InvoiceLine.quantity), 0))))
    cogs = _f(
        db.scalar(
            select(func.coalesce(func.sum(InvoiceLine.quantity * InvoiceLine.unit_cost), 0))
        )
    )
    order_count = int(_f(db.scalar(select(func.count(func.distinct(InvoiceLine.invoice_id))))))
    opex = _f(db.scalar(select(func.coalesce(func.sum(Expense.amount), 0))))

    avg_unit_price = revenue / units if units else 0.0
    avg_unit_cost = cogs / units if units else 0.0
    gross_profit = revenue - cogs
    gross_margin = gross_profit / revenue if revenue else 0.0
    return BaselineEconomics(
        revenue=revenue,
        cogs=cogs,
        units=units,
        avg_unit_price=avg_unit_price,
        avg_unit_cost=avg_unit_cost,
        gross_profit=gross_profit,
        gross_margin=gross_margin,
        order_count=order_count,
        operating_expenses=opex,
    )


def dashboard_summary(db: Session) -> dict:
    """Headline KPIs for the dashboard. Flags whether any real (non-demo) data
    exists so the UI never presents synthetic data as real (spec §17/§41)."""
    econ = baseline_economics(db)
    opex = _f(db.scalar(select(func.coalesce(func.sum(Expense.amount), 0))))
    p = pnl(econ.revenue, econ.cogs, opex)

    active_customers = int(
        _f(db.scalar(select(func.count(Customer.id)).where(Customer.status == "ACTIVE")))
    )
    # Lot-authoritative inventory value: the lot ledger is the single source of
    # truth (a sale decrements lots, not the legacy Inventory scalar), so value it
    # from lots wherever they exist and fall back to Inventory only for products
    # that predate the ledger.
    from app.services import stock as _stock
    inventory_value = _f(_stock.stock_value(db))

    # Is the current dataset entirely demo? (drives the DEMO DATA banner)
    real_invoices = int(
        _f(
            db.scalar(
                select(func.count(Invoice.id)).where(
                    Invoice.data_origin == DataOrigin.REAL.value
                )
            )
        )
    )
    total_invoices = int(_f(db.scalar(select(func.count(Invoice.id)))))

    return {
        "kpis": {
            **asdict(p),
            "orders": econ.order_count,
            "units_sold": econ.units,
            "active_customers": active_customers,
            "inventory_value": inventory_value,
        },
        "data_status": {
            "total_invoices": total_invoices,
            "real_invoices": real_invoices,
            "is_demo_only": total_invoices > 0 and real_invoices == 0,
        },
        # Every KPI above is computed from stored transactions, not invented.
        "provenance": DataOrigin.MODEL_OUTPUT.value,
    }
