"""Phase 2 business-intelligence analytics tests."""
from __future__ import annotations

from app.seed.demo_data import seed
from app.services.bi.customers import customer_intelligence
from app.services.bi.financials import monthly_pnl
from app.services.bi.products import product_intelligence
from app.services.bi.suppliers import supplier_intelligence


def test_customer_intelligence_structure_and_ordering(db):
    seed(db)
    intel = customer_intelligence(db)
    assert intel["summary"]["customers_with_sales"] > 0
    profits = [m["gross_profit"] for m in intel["top_by_profit"]]
    assert profits == sorted(profits, reverse=True)  # ranked desc
    # Concentration shares are fractions.
    assert 0 <= intel["summary"]["top5_revenue_share"] <= 1.0000001


def test_product_intelligence_best_sellers_ranked(db):
    seed(db)
    intel = product_intelligence(db)
    revs = [p["revenue"] for p in intel["best_sellers"]]
    assert revs == sorted(revs, reverse=True)
    for p in intel["most_profitable"]:
        assert 0 <= p["gross_margin"] <= 1


def test_supplier_intelligence(db):
    seed(db)
    intel = supplier_intelligence(db)
    assert intel["summary"]["supplier_count"] == 5
    assert all("product_count" in s for s in intel["suppliers"])


def test_monthly_pnl_series(db):
    seed(db)
    fin = monthly_pnl(db)
    assert len(fin["series"]) >= 20  # ~24 months of activity
    row = fin["series"][0]
    # Identity holds per period: gross = revenue - cogs.
    assert abs(row["gross_profit"] - (row["revenue"] - row["cogs"])) < 0.01
    # net = gross - opex
    assert abs(row["net_profit"] - (row["gross_profit"] - row["operating_expenses"])) < 0.01
