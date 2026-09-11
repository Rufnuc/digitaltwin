"""Scenario comparison (spec §34).

Runs several named strategies against the same baseline with the shared model and
returns them side by side, plus the baseline, so trade-offs are explicit.
"""
from __future__ import annotations

from app.services.analytics import BaselineEconomics
from app.services.simulation.model import REPORT_METRICS, Levers, levers_from_params, project


def compare_scenarios(baseline: BaselineEconomics, scenarios: list[dict]) -> dict:
    """`scenarios`: [{name, parameters, assumptions}]."""
    base = project(baseline, Levers())

    def _round(p, m: str) -> float:
        return round(p.metric(m), 4 if m == "gross_margin" else 2)

    baseline_row = {m: _round(base, m) for m in REPORT_METRICS}

    rows = []
    for sc in scenarios:
        levers = levers_from_params(sc.get("parameters", {}), sc.get("assumptions", {}))
        p = project(baseline, levers)
        values = {m: _round(p, m) for m in REPORT_METRICS}
        deltas = {
            m: round(p.metric(m) - base.metric(m), 4 if m == "gross_margin" else 2)
            for m in REPORT_METRICS
        }
        rows.append({"name": sc.get("name", "scenario"), "values": values, "deltas": deltas})

    # Rank strategies by net profit (a transparent default objective).
    ranked = sorted(rows, key=lambda r: r["values"]["net_profit"], reverse=True)
    return {
        "metrics": list(REPORT_METRICS),
        "baseline": baseline_row,
        "scenarios": rows,
        "best_by_net_profit": ranked[0]["name"] if ranked else None,
        "provenance": "MODEL_OUTPUT",
    }
