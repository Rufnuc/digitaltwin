"""Daily inventory-policy Monte Carlo (spec v4 §5/§8, v5 §2, Phase 2).

Simulates a periodic-review order-up-to (R, S) policy day by day against stochastic
daily demand, and reports the service metrics the spec defines: probability of
stockout, fill rate, cycle service level, and expected lost/backordered units. The
daily demand comes from the weekly forecast via the §5.1 bridge; draws are Poisson
or negative-binomial (gamma-Poisson mixture — scipy-free) depending on the observed
variance-to-mean ratio.

Determinism: draws depend only on (seed, iteration, day) — never on the policy S —
so candidate policies compared under the same seed see identical demand paths
(common random numbers, spec v5 §2 / v4 step 4).

`run_once` is a pure state machine over an explicit daily-demand array, so receipt
timing and the service metrics are exactly testable without any randomness.
"""
from __future__ import annotations

import math

import numpy as np

# A stockout "cycle" is one review interval of R days; a cycle counts as a
# stockout cycle if any day in it leaves demand unmet.
_EPS = 1e-9


def daily_lambdas(weekday_means: list[float], start_weekday: int, horizon_days: int) -> np.ndarray:
    """Expected demand for each horizon day, tiling the 7 weekday means."""
    means = np.asarray(weekday_means, dtype=float)
    idx = (start_weekday + np.arange(horizon_days)) % 7
    return means[idx]


def draw_demand(
    lambdas: np.ndarray, vmr: float, rng: np.random.Generator
) -> np.ndarray:
    """One horizon-length daily demand path.

    vmr is the variance-to-mean ratio of demand. vmr <= 1 → Poisson; vmr > 1 →
    negative binomial with the same VMR (gamma-Poisson mixture, scale = vmr - 1,
    shape = lambda / (vmr - 1)), so var = mean * vmr consistently (spec §5.1).
    """
    lam = np.clip(lambdas, 0.0, None)
    if vmr <= 1.0 + _EPS:
        return rng.poisson(lam).astype(float)
    scale = vmr - 1.0
    shape = np.where(lam > 0, lam / scale, 1.0)
    mixed = rng.gamma(shape=shape, scale=scale)
    mixed = np.where(lam > 0, mixed, 0.0)
    return rng.poisson(mixed).astype(float)


def run_once(
    daily_demand: np.ndarray, *, lead_time_days: int, review_period_days: int,
    order_up_to: float, initial_inventory: float, mode: str = "backorder",
) -> dict:
    """Simulate one demand path under a periodic-review order-up-to policy.

    Pure and deterministic: no randomness. An order placed at the review at the end
    of day t (integer lead L) becomes available at the START of day t + L + 1 (so
    lead 3 ordered on day 0 arrives day 4 — spec Q-014). Unmet demand is backordered
    (mode="backorder") or lost (mode="lost_sales").
    """
    horizon = len(daily_demand)
    lead = max(0, int(lead_time_days))
    review = max(1, int(review_period_days))
    on_hand = float(initial_inventory)
    on_order = 0.0
    backorders = 0.0
    arrivals: dict[int, float] = {}

    demand_total = fulfilled = lost = 0.0
    stockout_days = 0
    stockout_cycles: set[int] = set()

    for t in range(horizon):
        # 1. Receipts arrive at the start of the day, before demand; use them to
        #    clear outstanding backorders first.
        if t in arrivals:
            recv = arrivals.pop(t)
            on_hand += recv
            on_order -= recv
            if mode == "backorder" and backorders > _EPS:
                use = min(on_hand, backorders)
                on_hand -= use
                backorders -= use
                fulfilled += use

        # 2. Demand.
        d = float(daily_demand[t])
        demand_total += d
        served = min(on_hand, d)
        on_hand -= served
        fulfilled += served
        unmet = d - served
        if unmet > _EPS:
            stockout_days += 1
            stockout_cycles.add(t // review)
            if mode == "backorder":
                backorders += unmet
            else:
                lost += unmet

        # 3. Review at the start of each cycle; order up to S at end of day.
        if t % review == 0:
            position = on_hand + on_order - backorders
            order = max(0.0, order_up_to - position)
            if order > _EPS:
                on_order += order
                arrivals[t + lead + 1] = arrivals.get(t + lead + 1, 0.0) + order

    total_cycles = math.ceil(horizon / review) if horizon else 0
    cycles_without_stockout = total_cycles - len(stockout_cycles)
    return {
        "stockout_event": 1 if stockout_days > 0 else 0,
        "stockout_days": stockout_days,
        "demand_units": round(demand_total, 4),
        "fulfilled_units": round(fulfilled, 4),
        "lost_units": round(lost, 4),
        "backordered_units": round(backorders, 4),
        "ending_on_hand": round(on_hand, 4),
        "fill_rate": round(fulfilled / demand_total, 6) if demand_total > _EPS else 1.0,
        "cycle_service_level": (round(cycles_without_stockout / total_cycles, 6)
                                if total_cycles else 1.0),
        "total_cycles": total_cycles,
    }


def _pct(a: np.ndarray) -> dict:
    p = np.percentile(a, [5, 25, 50, 75, 95])
    return {"p05": round(float(p[0]), 4), "p25": round(float(p[1]), 4),
            "p50": round(float(p[2]), 4), "p75": round(float(p[3]), 4),
            "p95": round(float(p[4]), 4), "mean": round(float(a.mean()), 4),
            "min": round(float(a.min()), 4), "max": round(float(a.max()), 4)}


def simulate_policy(
    *, weekday_means: list[float], vmr: float, start_weekday: int,
    lead_time_days: int, review_period_days: int, order_up_to: float,
    initial_inventory: float, horizon_days: int = 90, iterations: int = 2000,
    seed: int = 42, mode: str = "backorder",
) -> dict:
    """Monte-Carlo the (R, S) policy and aggregate the service metrics.

    Demand is drawn per iteration from a stream seeded by (seed, iteration) only,
    so the same seed yields the same demand paths for any policy (CRN).
    """
    lambdas = daily_lambdas(weekday_means, start_weekday, horizon_days)
    keys = ["stockout_event", "stockout_days", "demand_units", "fulfilled_units",
            "lost_units", "backordered_units", "fill_rate", "cycle_service_level",
            "ending_on_hand"]
    cols: dict[str, list[float]] = {k: [] for k in keys}
    for i in range(iterations):
        rng = np.random.default_rng([seed, i])
        demand = draw_demand(lambdas, vmr, rng)
        r = run_once(demand, lead_time_days=lead_time_days,
                     review_period_days=review_period_days, order_up_to=order_up_to,
                     initial_inventory=initial_inventory, mode=mode)
        for k in keys:
            cols[k].append(r[k])

    arr = {k: np.asarray(v, dtype=float) for k, v in cols.items()}
    return {
        "iterations": iterations,
        "seed": seed,
        "horizon_days": horizon_days,
        "mode": mode,
        "policy": {"order_up_to": round(float(order_up_to), 4),
                   "review_period_days": review_period_days,
                   "lead_time_days": lead_time_days},
        # Headline service metrics.
        "probability_of_stockout": round(float(arr["stockout_event"].mean()), 6),
        "expected_fill_rate": round(float(arr["fill_rate"].mean()), 6),
        "expected_cycle_service_level": round(float(arr["cycle_service_level"].mean()), 6),
        "expected_lost_units": round(float(arr["lost_units"].mean()), 4),
        "expected_backordered_units": round(float(arr["backordered_units"].mean()), 4),
        # Distributions for the uncertainty-aware reader.
        "distributions": {
            "fill_rate": _pct(arr["fill_rate"]),
            "stockout_days": _pct(arr["stockout_days"]),
            "lost_units": _pct(arr["lost_units"]),
            "demand_units": _pct(arr["demand_units"]),
            "ending_on_hand": _pct(arr["ending_on_hand"]),
        },
        "provenance": "FORECAST",
    }
