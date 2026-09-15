"""Reorder policies, safety stock and EOQ (spec v4 §7–§8, v5 §6, v6 §3).

Protection horizon:
  periodic review  = review_period_days + ceil(mean_lead_time_days)
  continuous       = ceil(mean_lead_time_days)

Safety stock = z(service_level) * sigma over the protection horizon.
Reorder point = mean demand over protection horizon + safety stock.
Order-up-to (periodic) = mean over (review+lead) + safety stock.
EOQ = sqrt(2 * annual_demand * ordering_cost / (unit_cost * holding_rate)),
rounded up to the order multiple/MOQ, with an explicit fallback status.

`norm_ppf` is a rational approximation of the inverse normal CDF (scipy is not a
dependency; spec v5 §9 style). Every result returns its inputs and assumptions.
"""
from __future__ import annotations

import math

HOLDING_RATE = 0.25          # annual holding cost as a fraction of unit cost (spec v4 §7)
DEFAULT_SERVICE_LEVEL = 0.95
UNCERTAINTY_SUPPRESS = 2.0   # (p95-p05)/p50 above this suppresses (spec v5 §6)
WAPE_SUPPRESS = 0.80         # backtest WAPE above this suppresses (spec v5 §6)


def norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation)."""
    p = min(max(p, 1e-9), 1 - 1e-9)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def protection_horizon_days(mean_lead_time_days: float, review_period_days: int,
                            continuous: bool = False) -> int:
    lead = math.ceil(max(mean_lead_time_days, 0))
    return lead if continuous else int(review_period_days + lead)


def safety_stock(sigma_period: float, service_level: float = DEFAULT_SERVICE_LEVEL) -> float:
    """z * sigma over the protection horizon."""
    z = norm_ppf(service_level)
    return max(0.0, z * sigma_period)


def eoq(annual_demand_units: float, ordering_cost: float | None, unit_cost: float | None,
        holding_rate: float = HOLDING_RATE, moq: float = 1.0,
        order_multiple: float = 1.0) -> dict:
    """Economic order quantity with an explicit unavailable-fallback (spec v4 §7)."""
    if not ordering_cost or not unit_cost or unit_cost <= 0 or annual_demand_units <= 0:
        return {"status": "EOQ_UNAVAILABLE", "eoq_raw": None, "eoq_constrained": None,
                "reason": "ordering_cost/unit_cost/annual_demand required and positive"}
    holding = unit_cost * holding_rate
    raw = math.sqrt((2 * annual_demand_units * ordering_cost) / holding)
    constrained = max(raw, moq)
    if order_multiple > 1:
        constrained = math.ceil(constrained / order_multiple) * order_multiple
    return {"status": "OK", "eoq_raw": round(raw, 4), "eoq_constrained": round(constrained, 4),
            "annual_holding_cost_per_unit": round(holding, 4), "holding_rate": holding_rate,
            "moq": moq, "order_multiple": order_multiple}


def reorder_recommendation(
    *, weekly_mean: float, weekly_std: float, inventory_position: float,
    mean_lead_time_days: float, review_period_days: int = 7,
    service_level: float = DEFAULT_SERVICE_LEVEL, unit_cost: float | None = None,
    uncertainty_ratio: float | None = None, wape: float | None = None,
    validation_status: str | None = None, moq: float = 1.0, order_multiple: float = 1.0,
    std_lead_time_days: float = 0.0,
) -> dict:
    """Periodic-review order-up-to recommendation with a forecast-quality gate.

    Safety stock covers both demand and lead-time variability over the protection
    horizon (spec v4 §7):
        sigma_over = sqrt(H * sigma_d^2 + d_bar^2 * sigma_LT^2)
    where H is the protection horizon in days, sigma_d/d_bar are the daily demand
    std/mean, and sigma_LT is the lead-time std in days. With std_lead_time_days=0
    this reduces to the demand-only term.
    """
    horizon = protection_horizon_days(mean_lead_time_days, review_period_days)
    daily_mean = weekly_mean / 7.0
    daily_std = weekly_std / math.sqrt(7.0)
    demand_over = daily_mean * horizon
    sigma_demand = daily_std * math.sqrt(horizon)
    sigma_leadtime = daily_mean * max(std_lead_time_days, 0.0)
    sigma_over = math.sqrt(sigma_demand ** 2 + sigma_leadtime ** 2)

    ss = safety_stock(sigma_over, service_level)
    order_up_to = demand_over + ss
    raw_qty = max(0.0, order_up_to - inventory_position)
    qty = raw_qty
    if qty > 0:
        qty = max(qty, moq)
        if order_multiple > 1:
            qty = math.ceil(qty / order_multiple) * order_multiple

    # Forecast-quality gate (spec v5 §6 / v6 §3): unreliable/uncertain/unvalidated
    # forecasts never yield an ordinary READY recommendation.
    status = "READY"
    warnings: list[str] = []
    if validation_status == "INSUFFICIENT_DATA" or wape is None:
        status = "REVIEW_REQUIRED"
        warnings.append("QUALITY_EVIDENCE_MISSING")
    elif wape > WAPE_SUPPRESS:
        status = "REVIEW_REQUIRED"
        warnings.append("FORECAST_UNRELIABLE")
    if uncertainty_ratio is not None and uncertainty_ratio > UNCERTAINTY_SUPPRESS:
        status = "REVIEW_REQUIRED"
        if "FORECAST_UNRELIABLE" not in warnings:
            warnings.append("FORECAST_UNRELIABLE")
    if weekly_mean <= 0:
        status = "REVIEW_REQUIRED"
        warnings.append("NO_DEMAND_SIGNAL")

    return {
        "policy": "ORDER_UP_TO",
        "protection_horizon_days": horizon,
        "service_level": service_level,
        "z": round(norm_ppf(service_level), 4),
        "expected_demand_over_horizon": round(demand_over, 4),
        "sigma_over_horizon": round(sigma_over, 4),
        "sigma_demand_component": round(sigma_demand, 4),
        "sigma_lead_time_component": round(sigma_leadtime, 4),
        "std_lead_time_days": round(std_lead_time_days, 4),
        "safety_stock": round(ss, 4),
        "order_up_to_level": round(order_up_to, 4),
        "inventory_position": inventory_position,
        "recommended_order_quantity": round(qty, 4),
        "recommended_order_quantity_raw": round(raw_qty, 4),
        "estimated_order_cost": round(qty * unit_cost, 2) if unit_cost else None,
        "recommendation_status": status,
        "warnings": warnings,
        "provenance": {"inputs": "REAL", "safety_stock": "MODEL_OUTPUT",
                       "service_level": "ASSUMPTION"},
    }
