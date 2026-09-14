"""Demand-pattern (ADI/CV²) and ABC classification (Quant Phase 1).

Demand pattern follows the Syntetos–Boylan–Croston scheme, which also drives
forecast-model routing:

    ADI  = periods / non-zero-demand periods         (inter-demand interval)
    CV²  = (std(nonzero_sizes) / mean(nonzero_sizes))²

    Smooth        ADI < 1.32 and CV² < 0.49     -> SES / moving-average / naive
    Erratic       ADI < 1.32 and CV² >= 0.49    -> SES with wide intervals
    Intermittent  ADI >= 1.32 and CV² < 0.49    -> Croston / SBA / TSB
    Lumpy         ADI >= 1.32 and CV² >= 0.49   -> Croston / SBA / TSB

ABC ranks products by annualised verified demand value and cuts at cumulative
80% (A) / 95% (B). A 30-covered-day evidence gate keeps five-day histories from
masquerading as a full year (spec v5 §7 / v6 §7): short-history products are
excluded from the ranked population and reported separately with a confidence
multiplier.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

ADI_CUTOFF = 1.32
CV2_CUTOFF = 0.49
ABC_A_CUM = 0.80
ABC_B_CUM = 0.95
ABC_MIN_COVERED_DAYS = 30


@dataclass
class PatternResult:
    pattern: str            # SMOOTH | ERRATIC | INTERMITTENT | LUMPY | NO_DEMAND
    adi: float | None
    cv_squared: float | None
    periods: int
    nonzero_periods: int
    recommended_models: list[str]


_MODELS_SMOOTH = ["ses", "moving_average", "naive"]
_MODELS_ERRATIC = ["ses", "moving_average"]
_MODELS_INTERMITTENT = ["croston", "sba", "tsb"]


def classify_pattern(series: list[float]) -> PatternResult:
    """Classify a demand series into a pattern and recommend forecast models."""
    periods = len(series)
    sizes = [v for v in series if v > 0]
    nz = len(sizes)
    if nz == 0:
        return PatternResult("NO_DEMAND", None, None, periods, 0, [])

    adi = periods / nz
    mean = sum(sizes) / nz
    if nz >= 2 and mean > 0:
        var = sum((s - mean) ** 2 for s in sizes) / (nz - 1)  # sample variance
        cv2 = var / (mean ** 2)
    else:
        cv2 = 0.0

    smooth_adi = adi < ADI_CUTOFF
    low_cv = cv2 < CV2_CUTOFF
    if smooth_adi and low_cv:
        pattern, models = "SMOOTH", _MODELS_SMOOTH
    elif smooth_adi and not low_cv:
        pattern, models = "ERRATIC", _MODELS_ERRATIC
    elif not smooth_adi and low_cv:
        pattern, models = "INTERMITTENT", _MODELS_INTERMITTENT
    else:
        pattern, models = "LUMPY", _MODELS_INTERMITTENT

    return PatternResult(pattern, round(adi, 6), round(cv2, 6), periods, nz, models)


# --------------------------------------------------------------------------- #
# ABC
# --------------------------------------------------------------------------- #
@dataclass
class AbcItem:
    product_id: int
    demand_value: float          # annualised verified demand value
    cumulative_share: float
    abc_class: str               # A | B | C


@dataclass
class AbcResult:
    ranked: list[AbcItem]
    new_products: list[dict]     # short-history products, excluded from ranking


def annualise_value(units: float, unit_cost: float | None, covered_days: int) -> float | None:
    """Annualised demand value = units/covered_days * 365 * unit_cost."""
    if unit_cost is None or covered_days <= 0:
        return None
    return (units / covered_days) * 365.0 * unit_cost


def abc_classify(rows: list[dict]) -> AbcResult:
    """`rows`: [{product_id, units, unit_cost, covered_days}]. Products with fewer
    than 30 covered days are held out of the ranked population and returned with a
    confidence-adjusted annualisation (spec v6 §7)."""
    ranked_inputs: list[tuple[int, float]] = []
    new_products: list[dict] = []
    for r in rows:
        covered = int(r.get("covered_days") or 0)
        units = float(r.get("units") or 0)
        cost = r.get("unit_cost")
        value = annualise_value(units, cost, covered)
        if covered < ABC_MIN_COVERED_DAYS:
            conf = min(1.0, covered / ABC_MIN_COVERED_DAYS) if covered else 0.0
            new_products.append({
                "product_id": r["product_id"],
                "covered_days": covered,
                "annualised_units_raw": round((units / covered) * 365.0, 4) if covered else None,
                "annualisation_confidence": round(conf, 4),
                "annualisation_confidence_adjusted_units": (
                    round((units / covered) * 365.0 * conf, 4) if covered else None),
                "status": "ABC_EVIDENCE_SHORT",
            })
            continue
        if value is not None and value > 0:
            ranked_inputs.append((r["product_id"], value))

    ranked_inputs.sort(key=lambda t: (-t[1], t[0]))
    total = sum(v for _, v in ranked_inputs)
    out: list[AbcItem] = []
    cum = 0.0
    for pid, value in ranked_inputs:
        # Classify by the band the item STARTS in (cumulative before it), so a single
        # dominant item is still class A rather than falling past the 80% line.
        share_before = cum / total if total else 0.0
        cum += value
        share_after = cum / total if total else 0.0
        klass = "A" if share_before < ABC_A_CUM else "B" if share_before < ABC_B_CUM else "C"
        out.append(AbcItem(pid, round(value, 4), round(share_after, 6), klass))
    return AbcResult(out, new_products)


def cv2_of(values: list[float]) -> float:
    """Coefficient-of-variation squared of a list (used for heterogeneity checks)."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    if mean == 0:
        return 0.0
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return var / (mean ** 2)


def isclose(a: float, b: float, tol: float = 1e-9) -> bool:  # small test helper
    return math.isclose(a, b, rel_tol=0, abs_tol=tol)
