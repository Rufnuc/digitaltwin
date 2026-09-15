"""Quant Phase 1 — end-to-end composition (demand -> forecast -> reorder -> ABC)."""
from __future__ import annotations

from datetime import date, timedelta

from app.core.enums import VerificationStatus
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceLine
from app.models.product import Product
from app.services.quant import service as qsvc


def _seed_sales(db, product_id, customer_id, weekly_units, start, weeks):
    """Create one verified invoice per week with the given units."""
    for i in range(weeks):
        d = start + timedelta(weeks=i)
        inv = Invoice(invoice_number=f"Q-{product_id}-{i}", invoice_date=d,
                      customer_id=customer_id, currency="NGN", subtotal=0, total=0,
                      verification_status=VerificationStatus.VERIFIED.value,
                      data_origin="REAL")
        inv.lines.append(InvoiceLine(product_id=product_id, quantity=weekly_units,
                                     unit_price=100, line_total=weekly_units * 100))
        db.add(inv)
    db.commit()


def _product(db, code, cost=1000.0, price=1500.0, lead=7):
    p = Product(code=code, name=f"Part {code}", purchase_cost=cost, selling_price=price,
                lead_time_days=lead)
    db.add(p)
    db.commit()
    return p


def test_forecast_composition_smooth(db):
    cust = Customer(code="C1", name="Acme")
    db.add(cust)
    p = _product(db, "PX1")
    db.commit()
    start = date.today() - timedelta(weeks=20)
    _seed_sales(db, p.id, cust.id, weekly_units=5, start=start, weeks=20)

    r = qsvc.product_forecast(db, p.id)
    assert r["status"] == "OK"
    assert r["classification"]["pattern"] == "SMOOTH"
    assert r["forecast"]["point_values"][0] > 0
    assert r["demand"]["weeks_observed"] >= 20


def test_reorder_composition_orders_stock(db):
    cust = Customer(code="C2", name="Beta")
    db.add(cust)
    p = _product(db, "PX2", cost=500.0, lead=14)
    db.commit()
    start = date.today() - timedelta(weeks=16)
    _seed_sales(db, p.id, cust.id, weekly_units=10, start=start, weeks=16)

    r = qsvc.product_reorder(db, p.id, service_level=0.95)
    assert r["status"] == "OK"
    rec = r["recommendation"]
    assert rec["policy"] == "ORDER_UP_TO"
    # no stock on hand -> should recommend ordering
    assert rec["recommended_order_quantity"] > 0
    assert rec["protection_horizon_days"] == 7 + 14


def test_reorder_missing_inputs(db):
    p = Product(code="PX3", name="No cost", purchase_cost=None, lead_time_days=None)
    db.add(p)
    db.commit()
    r = qsvc.product_reorder(db, p.id)
    assert r["status"] == "INSUFFICIENT_DATA"
    assert "unit_cost" in r["missing_fields"]
    assert "lead_time_days" in r["missing_fields"]


def test_reorder_scan_portfolio(db):
    cust = Customer(code="CS", name="ScanCo")
    db.add(cust)
    steady = _product(db, "STEADY", cost=500.0, lead=14)
    _product(db, "QUIET", cost=800.0, lead=7)  # no sales -> not actionable
    db.commit()
    start = date.today() - timedelta(weeks=20)
    _seed_sales(db, steady.id, cust.id, weekly_units=10, start=start, weeks=20)

    scan = qsvc.reorder_scan(db)
    assert scan["status"] == "OK"
    assert set(scan["counts"]) == {"to_order_now", "needs_review", "insufficient_data"}

    codes = {i["product_code"] for i in scan["items"]}
    assert "STEADY" in codes            # steady demand, zero stock -> must order
    assert "QUIET" not in codes         # no demand -> nothing to recommend

    steady_item = next(i for i in scan["items"] if i["product_code"] == "STEADY")
    assert steady_item["recommended_order_quantity"] > 0
    assert steady_item["recommendation_status"] == "READY"
    # Items are ranked by estimated restock capital, largest first.
    costs = [i["estimated_order_cost"] or 0 for i in scan["items"]]
    assert costs == sorted(costs, reverse=True)
    # READY items feed the estimated restock cost total.
    assert scan["total_estimated_restock_cost"] > 0
    assert scan["counts"]["to_order_now"] >= 1


def test_abc_report(db):
    cust = Customer(code="C3", name="Gamma")
    db.add(cust)
    hi = _product(db, "HI", cost=1000.0)
    lo = _product(db, "LO", cost=100.0)
    db.commit()
    start = date.today() - timedelta(weeks=20)
    _seed_sales(db, hi.id, cust.id, 10, start, 20)
    _seed_sales(db, lo.id, cust.id, 1, start, 20)

    r = qsvc.abc_report(db)
    assert r["status"] == "OK"
    ranked = {i["product_id"]: i["abc_class"] for i in r["items"]}
    assert ranked[hi.id] == "A"  # high-value part is class A
