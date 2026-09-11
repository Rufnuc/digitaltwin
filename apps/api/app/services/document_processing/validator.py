"""Arithmetic & sanity validation of an extracted invoice (spec §13).

Inconsistencies are flagged, never silently corrected. The original extracted
values are preserved; a reviewer decides.
"""
from __future__ import annotations

from app.services.document_processing.base import InvoiceExtraction

_TOL = 0.01


def validate(extraction: InvoiceExtraction) -> dict:
    issues: list[str] = []

    line_sum = 0.0
    for i, ln in enumerate(extraction.lines, start=1):
        expected = round(ln.quantity * ln.unit_price, 2)
        if abs(expected - ln.line_total) > _TOL:
            issues.append(f"Line {i}: quantity×unit_price={expected} ≠ line_total={ln.line_total}")
        if ln.quantity <= 0:
            issues.append(f"Line {i}: non-positive quantity ({ln.quantity})")
        line_sum += ln.line_total
    line_sum = round(line_sum, 2)

    subtotal = extraction.subtotal if extraction.subtotal is not None else line_sum
    if abs(subtotal - line_sum) > _TOL:
        issues.append(f"Subtotal {subtotal} ≠ sum of lines {line_sum}")

    computed_total = round(subtotal + extraction.tax - extraction.discount, 2)
    if extraction.total is not None and abs(extraction.total - computed_total) > _TOL:
        issues.append(f"Total {extraction.total} ≠ subtotal+tax−discount {computed_total}")

    if not extraction.lines:
        issues.append("No line items extracted")
    if not extraction.invoice_number:
        issues.append("Missing invoice number")
    if not extraction.invoice_date:
        issues.append("Missing invoice date")

    return {
        "arithmetic_ok": len(issues) == 0,
        "issues": issues,
        "computed_subtotal": line_sum,
        "computed_total": computed_total,
    }
