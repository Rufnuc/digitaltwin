"""Quant Phase 2 — supplier scoring and landed cost."""
from __future__ import annotations

from app.models.supplier import Supplier
from app.services.quant import service as qsvc
from app.services.quant import supplier as sup


def test_landed_cost_missing_components_warns():
    r = sup.landed_cost(1000.0)
    assert r["status"] == "OK"
    assert r["total_landed_cost"] == 1000.0            # base only
    assert "LANDED_COST_COMPONENTS_MISSING" in r["warnings"]
    assert "freight_per_unit" in r["missing_components"]


def test_landed_cost_full_decomposition():
    r = sup.landed_cost(1000.0, freight=50.0, duty=120.0, handling=10.0,
                        fx_surcharge=30.0, quality=5.0)
    assert r["status"] == "OK"
    assert r["total_landed_cost"] == 1215.0
    assert r["warnings"] == [] and r["provenance"] == "REAL"


def test_landed_cost_needs_base():
    r = sup.landed_cost(None, freight=50.0)
    assert r["status"] == "INSUFFICIENT_DATA"
    assert r["total_landed_cost"] is None


def test_estimate_landed_cost_placeholder():
    r = sup.estimate_landed_cost(1000.0)
    assert r["status"] == "OK"
    # Placeholder until configured -> flagged, not for decisions.
    assert r["configured"] is False and r["provenance"] == "PLACEHOLDER"
    assert "LANDED_COST_PLACEHOLDER_NOT_CONFIGURED" in r["warnings"]
    # Components sum to the total, and total = base × (1 + total uplift).
    assert round(sum(r["components"].values()), 4) == r["total_landed_cost"]
    assert r["total_landed_cost"] == round(1000.0 * (1 + r["total_uplift_pct"] / 100), 4)


def test_estimate_landed_cost_needs_base():
    assert sup.estimate_landed_cost(None)["status"] == "INSUFFICIENT_DATA"


def test_estimate_landed_cost_configured(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "QUANT_LANDED_COST_CONFIGURED", True)
    r = sup.estimate_landed_cost(500.0)
    assert r["configured"] is True and r["provenance"] == "MODEL_OUTPUT"
    assert r["warnings"] == [] and r["note"] is None


def test_on_time_rate():
    # promised 10 days; 3 of 4 receipts on time.
    assert sup._on_time_rate([8, 9, 10, 15], 10) == 0.75
    assert sup._on_time_rate([], 10) is None
    assert sup._on_time_rate([8], None) is None


def test_score_supplier_uses_reliability(db):
    s = Supplier(code="SS1", name="Reliable", lead_time_days=14, reliability_score=0.95)
    db.add(s)
    db.commit()
    r = sup.score_supplier(db, s)
    assert r["status"] == "OK"
    assert 0.0 <= r["score"] <= 1.0
    assert r["components"]["reliability"] == 0.95
    assert r["components"]["reliability_source"] == "CONFIGURED"
    assert r["supplier_risk"] == round(1.0 - r["score"], 4)


def test_supplier_scores_ranked(db):
    good = Supplier(code="GOOD", name="Good", lead_time_days=10, reliability_score=0.95)
    poor = Supplier(code="POOR", name="Poor", lead_time_days=60, reliability_score=0.60)
    db.add_all([good, poor])
    db.commit()

    r = qsvc.supplier_scores(db)
    assert r["counts"]["scored"] == 2
    codes = [s["supplier_code"] for s in r["suppliers"]]
    # More reliable + shorter lead ranks first.
    assert codes.index("GOOD") < codes.index("POOR")
    assert r["suppliers"][0]["score"] >= r["suppliers"][1]["score"]


def test_supplier_without_evidence_is_insufficient(db):
    s = Supplier(code="BLANK", name="Blank", lead_time_days=None, reliability_score=None)
    db.add(s)
    db.commit()
    r = sup.score_supplier(db, s)
    assert r["status"] == "INSUFFICIENT_DATA" and r["score"] is None
