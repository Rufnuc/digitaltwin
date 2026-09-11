"""Dashboard analytics + demo-data labelling tests (spec §17, §41, §49)."""
from __future__ import annotations

from app.seed.demo_data import seed
from app.services.analytics import dashboard_summary


def test_seed_and_dashboard_flags_demo_only(db):
    counts = seed(db)
    assert counts["invoices"] > 0
    assert counts["invoice_lines"] > 0

    summary = dashboard_summary(db)
    # Demo data must be flagged as such, never presented as real.
    assert summary["data_status"]["is_demo_only"] is True
    assert summary["data_status"]["real_invoices"] == 0
    # KPIs are computed from the seeded transactions.
    assert summary["kpis"]["revenue"] > 0
    assert summary["kpis"]["gross_profit"] > 0
    # Positive margin because demo prices are always above cost.
    assert 0 < summary["kpis"]["gross_margin"] < 1


def test_dashboard_endpoint(client, auth_headers, db):
    seed(db)
    r = client.get("/api/v1/dashboard/summary", headers=auth_headers("VIEWER"))
    assert r.status_code == 200, r.text
    assert r.json()["kpis"]["orders"] > 0


def test_meta_data_origins(client, auth_headers):
    r = client.get("/api/v1/meta/data-origins", headers=auth_headers("VIEWER"))
    assert r.status_code == 200
    assert "DEMO" in r.json()["data_origins"]
    assert "FORECAST" in r.json()["data_origins"]
