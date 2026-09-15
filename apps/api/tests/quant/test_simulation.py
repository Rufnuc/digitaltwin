"""Quant Phase 2 — daily inventory-policy Monte Carlo."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from app.core.enums import VerificationStatus
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceLine
from app.models.product import Product
from app.services.quant import service as qsvc
from app.services.quant import simulation as sim

from .golden_utils import assert_golden


def test_receipt_timing_q014():
    # Order placed day 0 with lead 3 becomes available day 4 start (spec Q-014).
    # Start with 5 units, 5 demanded on day 0, then 1/day; the big review order
    # placed day 0 only lands on day 4, so days 1-3 stock out.
    demand = np.array([5, 1, 1, 1, 1, 1, 1, 1], dtype=float)
    r = sim.run_once(demand, lead_time_days=3, review_period_days=100,
                     order_up_to=100, initial_inventory=5, mode="lost_sales")
    assert r["stockout_days"] == 3
    assert r["lost_units"] == 3.0


def test_ample_inventory_never_stocks_out():
    demand = np.array([2] * 20, dtype=float)
    r = sim.run_once(demand, lead_time_days=5, review_period_days=7,
                     order_up_to=0, initial_inventory=1000, mode="lost_sales")
    assert r["stockout_event"] == 0 and r["fill_rate"] == 1.0
    assert r["cycle_service_level"] == 1.0


def test_backorder_vs_lost_sales():
    # Lead longer than the horizon so any replenishment never arrives — isolates
    # how unmet demand is booked (lost vs backordered).
    demand = np.array([10, 0, 0], dtype=float)
    lost = sim.run_once(demand, lead_time_days=100, review_period_days=100,
                        order_up_to=0, initial_inventory=4, mode="lost_sales")
    back = sim.run_once(demand, lead_time_days=100, review_period_days=100,
                        order_up_to=0, initial_inventory=4, mode="backorder")
    assert lost["lost_units"] == 6.0 and lost["backordered_units"] == 0.0
    assert back["backordered_units"] == 6.0 and back["lost_units"] == 0.0


def _policy(**kw):
    base = dict(weekday_means=[2.0] * 7, vmr=1.0, start_weekday=0, lead_time_days=2,
                review_period_days=7, order_up_to=50, initial_inventory=20,
                horizon_days=30, iterations=300, seed=7)
    base.update(kw)
    return sim.simulate_policy(**base)


def test_deterministic_and_common_random_numbers():
    a = _policy()
    b = _policy()
    assert a == b  # same seed -> identical
    # CRN: demand paths are policy-independent, so the demand distribution matches
    # even when the order-up-to level changes.
    low_s = _policy(order_up_to=5)
    assert a["distributions"]["demand_units"] == low_s["distributions"]["demand_units"]
    # A tighter stock level cannot reduce stockout probability.
    assert low_s["probability_of_stockout"] >= a["probability_of_stockout"]


def test_metrics_bounded():
    r = _policy(order_up_to=15)
    assert 0.0 <= r["probability_of_stockout"] <= 1.0
    assert 0.0 <= r["expected_fill_rate"] <= 1.0
    assert 0.0 <= r["expected_cycle_service_level"] <= 1.0


def test_simulation_golden():
    r = _policy(order_up_to=18, iterations=500, seed=123)
    # Keep the reproducible numeric contract; drop nothing (all deterministic).
    assert_golden("inventory_simulation_summary", r)


def _seed(db, product_id, customer_id, weekly_units, start, weeks):
    for i in range(weeks):
        inv = Invoice(invoice_number=f"S-{product_id}-{i}",
                      invoice_date=start + timedelta(weeks=i), customer_id=customer_id,
                      currency="NGN", subtotal=0, total=0,
                      verification_status=VerificationStatus.VERIFIED.value,
                      data_origin="REAL")
        inv.lines.append(InvoiceLine(product_id=product_id, quantity=weekly_units,
                                     unit_price=100, line_total=weekly_units * 100))
        db.add(inv)
    db.commit()


def _spec(pid, **kw):
    base = dict(product_id=pid, weekday_means=[2.0] * 7, vmr=1.0, start_weekday=0,
                lead_time_days=2, review_period_days=7, order_up_to=40,
                initial_inventory=30)
    base.update(kw)
    return base


def test_portfolio_deterministic_and_bounded():
    specs = [_spec(1), _spec(2, order_up_to=5, initial_inventory=2)]
    a = sim.simulate_portfolio(specs, horizon_days=30, iterations=200, seed=5)
    b = sim.simulate_portfolio(specs, horizon_days=30, iterations=200, seed=5)
    assert a == b
    assert 0.0 <= a["probability_of_any_stockout"] <= 1.0
    assert 0.0 <= a["expected_portfolio_fill_rate"] <= 1.0
    assert a["product_count"] == 2
    # The starved product (id 2) should be the highest-risk one.
    assert a["highest_risk_products"][0]["product_id"] == 2


def test_portfolio_no_stockout_when_all_well_stocked():
    specs = [_spec(1, initial_inventory=100000, order_up_to=0),
             _spec(2, initial_inventory=100000, order_up_to=0)]
    r = sim.simulate_portfolio(specs, horizon_days=20, iterations=100, seed=1)
    assert r["probability_of_any_stockout"] == 0.0
    assert r["expected_portfolio_fill_rate"] == 1.0


def test_portfolio_simulation_integration(db):
    cust = Customer(code="PS", name="PortCo")
    db.add(cust)
    p1 = Product(code="PP1", name="P1", purchase_cost=100.0, selling_price=200.0,
                 lead_time_days=7)
    p2 = Product(code="PP2", name="P2", purchase_cost=50.0, selling_price=120.0,
                 lead_time_days=7)
    db.add_all([p1, p2])
    db.commit()
    start = date.today() - timedelta(weeks=20)
    _seed(db, p1.id, cust.id, weekly_units=14, start=start, weeks=20)
    _seed(db, p2.id, cust.id, weekly_units=7, start=start, weeks=20)

    r = qsvc.portfolio_simulation(db, iterations=200, horizon_days=45)
    assert r["status"] == "OK" and r["products_simulated"] == 2
    pf = r["portfolio"]
    assert 0.0 <= pf["probability_of_any_stockout"] <= 1.0
    assert 0.0 <= pf["expected_portfolio_fill_rate"] <= 1.0


def test_product_simulation_integration(db):
    cust = Customer(code="SC", name="SimCo")
    prod = Product(code="SP", name="Sim Part", purchase_cost=100.0,
                   selling_price=250.0, lead_time_days=7)
    db.add_all([cust, prod])
    db.commit()
    start = date.today() - timedelta(weeks=20)
    _seed(db, prod.id, cust.id, weekly_units=14, start=start, weeks=20)

    r = qsvc.product_simulation(db, prod.id, iterations=300, horizon_days=60)
    assert r["status"] == "OK"
    s = r["simulation"]
    assert 0.0 <= s["probability_of_stockout"] <= 1.0
    assert s["iterations"] == 300 and s["horizon_days"] == 60
    # stockout cost = expected lost units × unit margin (150); non-negative.
    assert r["stockout_cost"] is not None and r["stockout_cost"] >= 0.0
