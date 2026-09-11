"""Phase 7: news → business-impact engine."""
from __future__ import annotations

from datetime import date

from app.core.enums import DataOrigin
from app.models.events import EconomicData
from app.models.system import Alert
from app.seed.demo_data import seed
from app.services.impact import engine


def _add_indicator(db, key, value, unit):
    db.add(EconomicData(indicator=key, period=date(2025, 12, 31), value=value, unit=unit,
                        data_origin=DataOrigin.REAL.value, verification_status="VERIFIED",
                        extraction_method="World Bank", source_reference="https://x"))
    db.commit()


def test_inflation_assessment_is_labelled_and_data_driven(db):
    seed(db)
    _add_indicator(db, "inflation_cpi_yoy", 23.0, "%")
    a = engine.assess_inflation(db, engine.DEFAULT_ASSUMPTIONS)
    assert a is not None
    # FACT is the real observed value; mapping is an assumption.
    assert a["fact"]["value"] == 23.0
    assert a["provenance"]["fact"] == "REAL"
    assert a["provenance"]["mapping"] == "ASSUMPTION"
    assert a["provenance"]["numbers"] == "MODEL_OUTPUT"
    # unit cost lever derived from inflation * passthrough (0.4) = 9.2
    assert a["lever"]["value"] == round(23.0 * 0.4, 2)
    # Higher costs -> lower net profit.
    net = next(r for r in a["simulation"]["results"] if r["metric"] == "net_profit")
    assert net["change_percent"] < 0


def test_fx_assessment_lists_import_suppliers(db):
    seed(db)
    _add_indicator(db, "fx_usd_ngn", 1326.0, "NGN/USD")
    a = engine.assess_fx(db, engine.DEFAULT_ASSUMPTIONS)
    assert a is not None
    assert a["lever"]["value"] == round(10.0 * 0.6, 2)  # fx_shock * import_share
    assert "suppliers" in a["possible_impact"]


def test_scan_creates_material_alerts(db):
    seed(db)
    _add_indicator(db, "inflation_cpi_yoy", 23.0, "%")
    before = db.query(Alert).count()
    result = engine.scan(db)
    assert result["has_market_data"] is True
    assert result["alerts_created"] >= 1
    after = db.query(Alert).count()
    assert after > before
    alert = db.query(Alert).order_by(Alert.id.desc()).first()
    assert alert.category == "market_impact"
    # A model-derived possibility, not an observed fact.
    assert alert.data_origin == "MODEL_OUTPUT"


def test_scan_without_market_data_is_empty(db):
    seed(db)
    result = engine.scan(db)
    assert result["has_market_data"] is False
    assert result["assessments"] == []


def test_impact_api(client, auth_headers, db):
    seed(db)
    _add_indicator(db, "inflation_cpi_yoy", 23.0, "%")
    r = client.post("/api/v1/impact/scan", headers=auth_headers("ANALYST"),
                    json={"create_alerts": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assessments"]
    assert "ASSUMPTION" in body["note"] or "MODEL OUTPUT" in body["note"]
    # Staff cannot run impact scans.
    assert client.post("/api/v1/impact/scan", headers=auth_headers("STAFF"),
                       json={}).status_code == 403
