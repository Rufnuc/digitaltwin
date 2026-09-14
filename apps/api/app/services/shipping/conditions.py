"""Lane conditions — the natural and human factors bearing on the China → Nigeria
and Turkey → Nigeria trade lanes, from REAL sources only.

Two honest signals, never invented:
  * Lane signals — observed from live AIS: how many vessels we track from each
    source lane, how many are under way vs sitting still (a congestion hint), and
    the median speed of those making way.
  * Disruption news — real headlines already ingested into the market feed,
    matched against a transparent keyword taxonomy and split into natural
    (weather) and human (logistics/geopolitics) factors, each linking to source.
"""
from __future__ import annotations

import re
from statistics import median

from sqlalchemy.orm import Session

from app.services.market_intelligence.ingest import recent_events
from app.services.shipping import collector
from app.services.shipping.collector import SOURCE_REGIONS

# Transparent keyword taxonomy — every match links back to a real headline.
# Matched on whole words (see _matches) so "ice" never fires inside "licenses".
NATURAL_KEYWORDS = (
    "typhoon", "cyclone", "hurricane", "storm", "monsoon", "flood", "fog",
    "drought", "weather", "earthquake", "tsunami", "sea ice",
)
HUMAN_KEYWORDS = (
    "strike", "congestion", "backlog", "blockade", "suez", "red sea", "houthi",
    "panama canal", "tariff", "sanction", "embargo", "port closure",
    "lockdown", "piracy", "detained", "delay", "shortage",
)


def _matches(text: str, keywords: tuple[str, ...]) -> list[str]:
    """Whole-word keyword matches (phrases allowed), case-insensitive."""
    return [kw for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", text)]

# Speed (knots) below which a vessel is not making way — anchored, berthed or waiting.
STATIONARY_KN = 0.5


def lane_signals() -> list[dict]:
    """Observed AIS signals per source lane (REAL)."""
    out = []
    for region in SOURCE_REGIONS:
        vs = [v for v in collector.store.vessels.values() if v.get("origin_region") == region]
        speeds = [v["sog"] for v in vs if isinstance(v.get("sog"), int | float)]
        moving = [s for s in speeds if s >= STATIONARY_KN]
        stationary = [s for s in speeds if s < STATIONARY_KN]
        share = round(len(stationary) / len(speeds), 3) if speeds else None
        out.append({
            "lane": region,
            "vessels_tracked": len(vs),
            "with_speed": len(speeds),
            "moving": len(moving),
            "stationary": len(stationary),
            "stationary_share": share,
            "median_speed_kn": round(median(moving), 1) if moving else None,
        })
    return out


def disruption_news(db: Session, limit: int = 40) -> dict:
    """Recent real news matched to natural / human disruption factors."""
    natural: list[dict] = []
    human: list[dict] = []
    for e in recent_events(db, limit=limit, min_relevance=0.0):
        text = f"{e['title']} {e.get('summary') or ''}".lower()
        nat = _matches(text, NATURAL_KEYWORDS)
        hum = _matches(text, HUMAN_KEYWORDS)
        base = {
            "title": e["title"], "source": e["source"], "source_url": e["source_url"],
            "published": e["published"], "relevance": e["relevance"],
        }
        if nat:
            natural.append({**base, "factors": nat})
        if hum:
            human.append({**base, "factors": hum})
    return {"natural": natural, "human": human}


def conditions(db: Session) -> dict:
    news = disruption_news(db)
    return {
        "lanes": lane_signals(),
        "disruptions": news,
        "counts": {"natural": len(news["natural"]), "human": len(news["human"])},
        "provenance": {"lane_signals": "REAL", "disruptions": "REAL"},
        "note": "Lane signals are live AIS observations; disruption items are real headlines "
                "matched to weather (natural) and logistics/geopolitical (human) factors. "
                "Presence of a factor is a signal, not a measured effect.",
    }
