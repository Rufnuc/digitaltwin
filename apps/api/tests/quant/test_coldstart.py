"""Quant — cold-start demand prior for products with no sales history (v5 §3)."""
from __future__ import annotations

from datetime import date, timedelta

from app.core.enums import VerificationStatus
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceLine
from app.models.product import Product
from app.services.quant import coldstart
from app.services.quant import service as qsvc


def _sell(db, product_id, customer_id, weekly, weeks):
    start = date.today() - timedelta(weeks=weeks)
    for i in range(weeks):
        inv = Invoice(invoice_number=f"CS-{product_id}-{i}",
                      invoice_date=start + timedelta(weeks=i), customer_id=customer_id,
                      currency="NGN", subtotal=0, total=0,
                      verification_status=VerificationStatus.VERIFIED.value,
                      data_origin="REAL")
        inv.lines.append(InvoiceLine(product_id=product_id, quantity=weekly,
                                     unit_price=100, line_total=weekly * 100))
        db.add(inv)
    db.commit()


def test_cold_start_prior_from_peers(db):
    cust = Customer(code="CSC", name="ColdCo")
    db.add(cust)
    # Two selling peers in category "Pistons", plus a brand-new no-sales product.
    peer1 = Product(code="P1", name="Piston A", category="Pistons",
                    purchase_cost=500.0, selling_price=900.0, lead_time_days=7)
    peer2 = Product(code="P2", name="Piston B", category="Pistons",
                    purchase_cost=500.0, selling_price=900.0, lead_time_days=7)
    fresh = Product(code="NEW", name="Piston New", category="Pistons",
                    purchase_cost=500.0, selling_price=900.0, lead_time_days=7)
    db.add_all([peer1, peer2, fresh])
    db.commit()
    _sell(db, peer1.id, cust.id, weekly=10, weeks=12)
    _sell(db, peer2.id, cust.id, weekly=6, weeks=12)

    r = coldstart.cold_start_prior(db, fresh)
    assert r["status"] == "OK"
    assert r["peer_count"] == 2
    # Prior is the median of the two peers' average weekly demand (~5.5 and ~9.2),
    # so it lands between them and is positive.
    assert 5.0 < r["expected_weekly_demand"] < 10.0
    assert r["forecast"]["provenance"] == "ESTIMATED"
    assert "COLD_START_DEMAND_PRIOR" in r["forecast"]["warnings"]


def test_forecast_uses_cold_start_for_new_product(db):
    cust = Customer(code="CSC2", name="ColdCo2")
    db.add(cust)
    peer = Product(code="PP", name="Filter A", category="Filters",
                   purchase_cost=100.0, selling_price=200.0, lead_time_days=7)
    fresh = Product(code="FNEW", name="Filter New", category="Filters",
                    purchase_cost=100.0, selling_price=200.0, lead_time_days=7)
    db.add_all([peer, fresh])
    db.commit()
    _sell(db, peer.id, cust.id, weekly=5, weeks=12)

    r = qsvc.product_forecast(db, fresh.id)
    assert r["status"] == "COLD_START"
    assert r["forecast"]["model_name"] == "cold_start_demand_prior"
    # One peer selling ~5/week -> the new product's prior is close to it.
    assert 4.0 < r["cold_start"]["expected_weekly_demand"] <= 5.0
    assert r["provenance"] == "ESTIMATED"


def test_no_peers_stays_insufficient(db):
    lonely = Product(code="LONE", name="Lonely", category="Rare",
                     purchase_cost=100.0, selling_price=200.0, lead_time_days=7)
    db.add(lonely)
    db.commit()
    r = qsvc.product_forecast(db, lonely.id)
    assert r["status"] == "INSUFFICIENT_DATA"  # no peers -> no prior
