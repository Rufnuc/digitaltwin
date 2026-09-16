"""Tax estimate — VAT and company income tax for a period (Nigeria defaults).

This is an ESTIMATE to help plan, computed transparently from recorded data — NOT
tax advice. It shows how each figure is derived so an accountant can check it.

  VAT payable   = output VAT (charged on sales) − input VAT (on purchases)
  Taxable profit= revenue − cost of goods sold − operating expenses
  Income tax    = max(0, taxable profit) × the turnover-tiered CIT rate

Expenses and supplier purchases feed straight in: purchases carry input VAT and
become COGS as goods sell; expenses reduce taxable profit.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import DataOrigin
from app.models.expense import Expense
from app.models.invoice import Invoice, InvoiceLine
from app.models.product import Product
from app.models.purchase import Purchase


def _cit_rate(annual_turnover: float) -> tuple[float, str]:
    if annual_turnover < settings.TAX_CIT_SMALL_TURNOVER:
        return settings.TAX_CIT_SMALL_RATE, "small (< ₦25m turnover, exempt)"
    if annual_turnover < settings.TAX_CIT_MEDIUM_TURNOVER:
        return settings.TAX_CIT_MEDIUM_RATE, "medium (₦25m–₦100m turnover)"
    return settings.TAX_CIT_LARGE_RATE, "large (> ₦100m turnover)"


def tax_summary(db: Session, start: date | None = None, end: date | None = None,
                include_demo: bool = False) -> dict:
    """VAT and income-tax estimate for [start, end] (default: trailing 12 months)."""
    end = end or date.today()
    start = start or (end - timedelta(days=365))
    inv_filter = [Invoice.invoice_date >= start, Invoice.invoice_date <= end]
    if not include_demo:
        inv_filter.append(Invoice.data_origin != DataOrigin.DEMO.value)

    revenue = float(db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(*inv_filter)) or 0)
    output_vat = float(db.scalar(
        select(func.coalesce(func.sum(Invoice.tax), 0)).where(*inv_filter)) or 0)

    # COGS: units sold × their purchase cost, for invoices in the window.
    cogs = float(db.scalar(
        select(func.coalesce(func.sum(InvoiceLine.quantity * Product.purchase_cost), 0))
        .select_from(InvoiceLine)
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .join(Product, Product.id == InvoiceLine.product_id)
        .where(*inv_filter)
    ) or 0)

    pur_filter = [Purchase.purchase_date >= start, Purchase.purchase_date <= end]
    input_vat = float(db.scalar(
        select(func.coalesce(func.sum(Purchase.tax), 0)).where(*pur_filter)) or 0)

    exp_filter = [Expense.expense_date >= start, Expense.expense_date <= end]
    opex = float(db.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(*exp_filter)) or 0)

    vat_payable = round(output_vat - input_vat, 2)
    taxable_profit = round(revenue - cogs - opex, 2)

    # Annualise the period's revenue to choose the CIT tier.
    days = max(1, (end - start).days)
    annual_turnover = revenue / days * 365
    cit_rate, cit_band = _cit_rate(annual_turnover)
    income_tax = round(max(0.0, taxable_profit) * cit_rate, 2)
    total_tax = round(max(0.0, vat_payable) + income_tax, 2)

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "revenue": round(revenue, 2),
        "vat": {
            "rate": settings.TAX_VAT_RATE,
            "output_vat": round(output_vat, 2),   # collected on sales
            "input_vat": round(input_vat, 2),      # paid on purchases
            "vat_payable": vat_payable,            # remit to FIRS (negative = credit)
        },
        "income_tax": {
            "cost_of_goods_sold": round(cogs, 2),
            "operating_expenses": round(opex, 2),
            "taxable_profit": taxable_profit,
            "annualised_turnover": round(annual_turnover, 2),
            "cit_rate": cit_rate,
            "cit_band": cit_band,
            "income_tax": income_tax,
        },
        "total_estimated_tax": total_tax,
        "provenance": "MODEL_OUTPUT",
        "disclaimer": "Estimate from your recorded sales, purchases and expenses using "
                      "Nigerian default rates — not tax advice. Confirm with your "
                      "accountant. Rates are configurable.",
    }
