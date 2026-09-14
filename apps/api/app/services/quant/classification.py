"""Demand-pattern (ADI/CV²) and ABC classification (spec v4 §6, v5 §7, v6 §7).

Demand pattern uses the Syntetos–Boylan–Croston scheme:
  ADI  = periods / non-zero periods           (average inter-demand interval)
  CV²  = (std / mean)² of non-zero demand sizes
  cutoffs: ADI 1.32, CV² 0.49
    SMOOTH        ADI < 1.32 and CV² < 0.49
    ERRATIC       ADI < 1.32 and CV² >= 0.49
    INTERMITTENT  ADI >= 1.32 and CV² < 0.49
    LUMPY         ADI >= 1.32 and CV² >= 0.49
It also drives model eligibility (SES/MA for smooth; Croston/SBA/TSB for
intermittent/lumpy).

ABC ranks products by annualised verified demand value with an evidence gate:
products with < 30 covered days are held out of the ranked population and shown
with a confidence-adjusted figure (spec v5 §7 / v6 §7).
"""
from __future__ import annotations

ADI_CUTOFF = 1.32
CV2_CUTOFF = 0.49

# Models eligible to forecast each pattern (spec v4 §4.1 / Phase 1).
PATTERN_MODELS = {
    "SMOOTH": ["naive", "moving_average", "ses"],
    "ERRATIC": ["moving_average", "ses"],
    "INTERMITTENT": ["croston", "sba", "tsb"],
    "LUMPY": ["croston", "sba", "tsb"],
    "NO_EVIDENCE": [],
}


def classify_pattern(units: list[float]) -> dict:
    """Classify a weekly demand series. `units` includes zero-demand weeks."""
    n = len(units)
    nz = [u for u in units if u > 0]
    if n == 0 or not nz:
        return {"pattern": "NO_EVIDENCE", "adi": None, "cv_squared": None,
                "periods": n, "nonzero_periods": len(nz),
                "eligible_models": PATTERN_MODELS["NO_EVIDENCE"],
                "warnings": ["NO_SALES_HISTORY"]}

    adi = n / len(nz)
    mean = sum(nz) / len(nz)
    if len(nz) > 1:
        var = sum((x - mean) ** 2 for x in nz) / len(nz)
        cv2 = (var / (mean * mean)) if mean else 0.0
    else:
        cv2 = 0.0

    if adi < ADI_CUTOFF:
        pattern = "SMOOTH" if cv2 < CV2_CUTOFF else "ERRATIC"
    else:
        pattern = "INTERMITTENT" if cv2 < CV2_CUTOFF else "LUMPY"

    warnings = []
    if len(nz) < 10:
        warnings.append("LOW_EVIDENCE")
    return {
        "pattern": pattern,
        "adi": round(adi, 6),
        "cv_squared": round(cv2, 6),
        "periods": n,
        "nonzero_periods": len(nz),
        "eligible_models": PATTERN_MODELS[pattern],
        "cutoffs": {"adi": ADI_CUTOFF, "cv_squared": CV2_CUTOFF},
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# ABC classification
# --------------------------------------------------------------------------- #
ABC_MIN_COVERED_DAYS = 30
ABC_A_CUM = 0.80
ABC_B_CUM = 0.95


def classify_abc(products: list[dict]) -> dict:
    """Rank products by annualised demand value into A/B/C classes.

    Each input: {product_id, annual_demand_value, covered_days}. Products with
    fewer than 30 covered days are excluded from the ranked population and returned
    in `new_products` with a confidence-adjusted value (spec v5 §7 / v6 §7).
    """
    ranked_input, new_products = [], []
    for p in products:
        covered = int(p.get("covered_days") or 0)
        value = p.get("annual_demand_value")
        if value is None:
            new_products.append({**p, "reason": "MISSING_DEMAND_VALUE"})
            continue
        if covered < ABC_MIN_COVERED_DAYS:
            conf = min(1.0, covered / ABC_MIN_COVERED_DAYS)
            new_products.append({
                "product_id": p["product_id"],
                "annualised_units_value_raw": round(float(value), 4),
                "annualisation_confidence": round(conf, 4),
                "annualisation_confidence_adjusted_value": round(float(value) * conf, 4),
                "covered_days": covered,
                "status": "ABC_EVIDENCE_SHORT",
            })
            continue
        ranked_input.append({"product_id": p["product_id"], "value": float(value),
                             "covered_days": covered})

    ranked_input.sort(key=lambda x: (-x["value"], x["product_id"]))
    total = sum(x["value"] for x in ranked_input)
    items, cum = [], 0.0
    for x in ranked_input:
        share = (x["value"] / total) if total else 0.0
        # Classify by cumulative BEFORE this item, so the item that crosses the 80%
        # line is still A (standard ABC; the top item is always A).
        cum_before = cum
        cum += share
        cls = "A" if cum_before < ABC_A_CUM else ("B" if cum_before < ABC_B_CUM else "C")
        items.append({
            "product_id": x["product_id"],
            "annual_demand_value": round(x["value"], 4),
            "value_share": round(share, 6),
            "cumulative_share": round(cum, 6),
            "abc_class": cls,
            "covered_days": x["covered_days"],
        })
    return {
        "items": items,
        "new_products": new_products,
        "total_value": round(total, 4),
        "cutoffs": {"a_cumulative": ABC_A_CUM, "b_cumulative": ABC_B_CUM,
                    "min_covered_days": ABC_MIN_COVERED_DAYS},
        "counts": {"ranked": len(items), "new_products": len(new_products)},
    }
