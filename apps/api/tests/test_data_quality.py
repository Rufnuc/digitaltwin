"""Data-quality reporting tests (spec §43)."""
from __future__ import annotations

from app.core.enums import DataOrigin
from app.models.product import Product
from app.seed.demo_data import seed
from app.services.bi.data_quality import data_quality_report


def test_clean_demo_scores_well(db):
    seed(db)
    report = data_quality_report(db)
    # Demo data is internally consistent -> no arithmetic/dup issues, high score.
    categories = {i["category"] for i in report["issues"]}
    assert "invoice_line_arithmetic" not in categories
    assert "duplicate_invoice_number" not in categories
    assert report["score"] >= 90
    assert report["grade"] == "A"


def test_non_positive_margin_is_flagged(db):
    seed(db)
    # Introduce a product that sells below cost.
    bad = Product(code="BADPRICE", name="Loss maker", purchase_cost=100, selling_price=80,
                  data_origin=DataOrigin.DEMO.value)
    db.add(bad)
    db.commit()
    report = data_quality_report(db)
    categories = {i["category"] for i in report["issues"]}
    assert "non_positive_margin" in categories
    issue = next(i for i in report["issues"] if i["category"] == "non_positive_margin")
    assert bad.id in issue["sample_ids"]


def test_missing_values_flagged(db):
    seed(db)
    db.add(Product(code="NOPRICE", name="No price", purchase_cost=10, selling_price=None))
    db.commit()
    report = data_quality_report(db)
    assert any(i["category"] == "missing_product_values" for i in report["issues"])
