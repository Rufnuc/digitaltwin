"""Data-quality reporting and score (spec §43).

Each check returns a category, a severity, a count and a small sample of offending
ids — so problems are transparent and actionable, never hidden. The score is a
transparent weighted ratio, not a black box.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import VerificationStatus
from app.models.invoice import Invoice, InvoiceLine
from app.models.product import Product

_TOL = 0.01
_SEVERITY_WEIGHT = {"low": 1, "medium": 3, "high": 5}


def _issue(category: str, severity: str, description: str, count: int, samples: list) -> dict:
    return {
        "category": category,
        "severity": severity,
        "description": description,
        "count": count,
        "sample_ids": samples[:10],
    }


def data_quality_report(db: Session) -> dict:
    issues: list[dict] = []

    # 1) Line arithmetic errors: quantity * unit_price != line_total.
    bad_lines = [
        lid
        for lid, q, up, lt in db.execute(
            select(
                InvoiceLine.id,
                InvoiceLine.quantity,
                InvoiceLine.unit_price,
                InvoiceLine.line_total,
            )
        ).all()
        if abs(float(q or 0) * float(up or 0) - float(lt or 0)) > _TOL
    ]
    if bad_lines:
        issues.append(_issue("invoice_line_arithmetic", "high",
                             "quantity × unit_price ≠ line_total", len(bad_lines), bad_lines))

    # 2) Invoice header arithmetic: subtotal + tax − discount ≠ total.
    bad_inv = [
        iid
        for iid, sub, tax, disc, tot in db.execute(
            select(Invoice.id, Invoice.subtotal, Invoice.tax, Invoice.discount, Invoice.total)
        ).all()
        if abs(float(sub or 0) + float(tax or 0) - float(disc or 0) - float(tot or 0)) > _TOL
    ]
    if bad_inv:
        issues.append(_issue("invoice_total_arithmetic", "high",
                             "subtotal + tax − discount ≠ total", len(bad_inv), bad_inv))

    # 3) Invoice lines not matched to a product (spec §12 normalisation gap).
    unmatched_lines = db.scalars(
        select(InvoiceLine.id).where(InvoiceLine.product_id.is_(None))
    ).all()
    if unmatched_lines:
        issues.append(_issue("unmatched_product", "medium",
                             "invoice line has no matched product", len(unmatched_lines),
                             list(unmatched_lines)))

    # 4) Invoices with no customer.
    no_customer = db.scalars(select(Invoice.id).where(Invoice.customer_id.is_(None))).all()
    if no_customer:
        issues.append(_issue("unmatched_customer", "medium",
                             "invoice has no customer", len(no_customer), list(no_customer)))

    # 5) Duplicate invoice numbers.
    dupes = [
        num
        for num, c in db.execute(
            select(Invoice.invoice_number, func.count(Invoice.id)).group_by(Invoice.invoice_number)
        ).all()
        if c > 1
    ]
    if dupes:
        issues.append(_issue("duplicate_invoice_number", "high",
                             "invoice number used more than once", len(dupes), dupes))

    # 6) Suspicious pricing: selling price ≤ cost (non-positive margin).
    neg_margin = db.scalars(
        select(Product.id).where(
            Product.selling_price.is_not(None),
            Product.purchase_cost.is_not(None),
            Product.selling_price <= Product.purchase_cost,
        )
    ).all()
    if neg_margin:
        issues.append(_issue("non_positive_margin", "medium",
                             "product sells at or below cost", len(neg_margin), list(neg_margin)))

    # 7) Missing values: products without cost or price.
    missing = db.scalars(
        select(Product.id).where(
            (Product.selling_price.is_(None)) | (Product.purchase_cost.is_(None))
        )
    ).all()
    if missing:
        issues.append(_issue("missing_product_values", "low",
                             "product missing cost or price", len(missing), list(missing)))

    # 8) Records needing review (from extraction/validation).
    needs_review = db.scalar(
        select(func.count(Invoice.id)).where(
            Invoice.verification_status == VerificationStatus.NEEDS_REVIEW.value
        )
    )
    if needs_review:
        issues.append(_issue("needs_review", "medium",
                             "invoice flagged NEEDS_REVIEW", int(needs_review), []))

    # --- Transparent score ---
    total_invoices = int(db.scalar(select(func.count(Invoice.id))) or 0)
    total_lines = int(db.scalar(select(func.count(InvoiceLine.id))) or 0)
    total_products = int(db.scalar(select(func.count(Product.id))) or 0)
    denom = max(total_invoices + total_lines + total_products, 1)
    penalty = sum(_SEVERITY_WEIGHT[i["severity"]] * i["count"] for i in issues)
    score = max(0.0, round(100.0 * (1 - min(penalty / denom, 1.0)), 1))

    return {
        "score": score,
        "grade": "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D",
        "totals": {
            "invoices": total_invoices,
            "invoice_lines": total_lines,
            "products": total_products,
        },
        "issues": sorted(issues, key=lambda i: _SEVERITY_WEIGHT[i["severity"]], reverse=True),
        "provenance": "MODEL_OUTPUT",
    }
