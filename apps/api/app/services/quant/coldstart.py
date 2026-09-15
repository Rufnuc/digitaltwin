"""Cold-start demand prior (spec v5 §3) — a first estimate for a product with no
sales history, so a brand-new part isn't a total blank.

Since the app has no enquiry/backorder feed yet, the prior is drawn from PEERS: the
recent average weekly demand of other selling products in the SAME category. It is a
low-confidence guess, tagged ESTIMATED / COLD_START_DEMAND_PRIOR, and deliberately
never yields an automatic reorder (the forecast-quality gate keeps it
REVIEW_REQUIRED) — it only stops a new product from showing nothing at all.
"""
from __future__ import annotations

import statistics
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.quant import demand as dmd

MIN_PEER_WEEKS = 4     # a peer needs at least this much history to inform the prior
# A wide interval reflects the low confidence: p05..p95 spread around the prior.
_LOW = 0.0
_HIGH_MULT = 2.5


def cold_start_prior(db: Session, product: Product, as_of: date | None = None,
                     horizon: int = 12, include_demo: bool = False) -> dict:
    """Peer-based expected weekly demand for a no-history product.

    Returns status NONE when there are no usable peers (so the caller falls back to
    INSUFFICIENT_DATA), otherwise a forecast-shaped, low-confidence prior.
    """
    peers: list[Product] = []
    if product.category:
        peers = list(db.scalars(
            select(Product).where(
                Product.is_active.is_(True),
                Product.category == product.category,
                Product.id != product.id,
            )
        ).all())

    weekly_means: list[float] = []
    for p in peers:
        s = dmd.product_weekly_demand(db, p.id, as_of, include_demo=include_demo)
        n = len(s["units"])
        if n >= MIN_PEER_WEEKS and s["total_units"] > 0:
            weekly_means.append(s["total_units"] / n)

    if not weekly_means:
        return {"status": "NONE"}

    prior = round(statistics.median(weekly_means), 4)
    p95 = round(prior * _HIGH_MULT, 4)
    quantiles = {"p05": [_LOW] * horizon, "p25": [round(prior * 0.5, 4)] * horizon,
                 "p50": [prior] * horizon, "p75": [round(prior * 1.5, 4)] * horizon,
                 "p95": [p95] * horizon}
    return {
        "status": "OK",
        "forecast": {
            "product_pattern": "NO_EVIDENCE",
            "frequency": "WEEKLY",
            "horizon_periods": horizon,
            "point_statistic": "MEAN",
            "point_values": [prior] * horizon,
            "quantiles": quantiles,
            "distribution_family": "COLD_START_PEER_PRIOR",
            "model_name": "cold_start_demand_prior",
            "model_version": "cold_start-1.0.0",
            "peer_count": len(weekly_means),
            "peer_category": product.category,
            "confidence": "LOW",
            "warnings": ["COLD_START_DEMAND_PRIOR", "LOW_EVIDENCE"],
            "provenance": "ESTIMATED",
        },
        "expected_weekly_demand": prior,
        "peer_count": len(weekly_means),
    }
