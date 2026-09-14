"""Market-intelligence ingestion & read models (spec §30, §31 foundation).

Fetches real external data via a provider and upserts it into `economic_data` /
`market_events` with full provenance (source, url, date, confidence, REAL origin).
Reads come from the database, so the UI never blocks on the network. "Implications"
are transparent, rule-based hints explicitly labelled ASSUMPTION / POSSIBLE IMPACT
— never presented as fact, and never auto-run as simulations (that is Phase 7).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import DataOrigin, VerificationStatus
from app.models.events import EconomicData, MarketEvent
from app.services.market_intelligence.base import MarketDataProvider, get_market_provider

# Transparent indicator → possible business impact (ASSUMPTION, not fact).
IMPLICATIONS = {
    "inflation_cpi_yoy": "Higher inflation raises input and operating costs — review prices and "
                         "tighten cost control.",
    "fx_usd_ngn": "A weaker naira raises the cost of USD-priced imported parts and supplier "
                  "prices — consider hedging or diversifying sourcing.",
    "fx_eur_ngn": "Euro-priced imports get more expensive as the naira weakens.",
    "fx_gbp_ngn": "Sterling-priced imports get more expensive as the naira weakens.",
    "fx_cny_ngn": "Most parts are imported from China — a weaker naira against the yuan raises "
                  "landed costs directly.",
    "official_fx_usd": "Official-rate depreciation signals broad import-cost pressure.",
    "lending_rate": "Higher lending rates raise the cost of financing inventory and expansion.",
    "gdp_growth": "Slower growth may soften customer demand.",
}


def _parse_date(s: str | None) -> date:
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return date.today()


def refresh_market_data(db: Session, provider: MarketDataProvider | None = None) -> dict:
    provider = provider or get_market_provider()

    indicators = provider.fetch_indicators()
    ind_new = ind_updated = 0
    for p in indicators:
        period = _parse_date(p.period)
        existing = db.scalar(
            select(EconomicData).where(
                EconomicData.indicator == p.indicator, EconomicData.period == period
            )
        )
        if existing:
            existing.value = p.value
            existing.confidence = p.confidence
            existing.source_reference = p.source_url
            existing.extraction_method = p.source
            ind_updated += 1
        else:
            row = EconomicData(
                indicator=p.indicator, period=period, value=p.value, unit=p.unit,
                data_origin=DataOrigin.REAL.value,
                verification_status=VerificationStatus.VERIFIED.value,
                confidence=p.confidence, extraction_method=p.source, source_reference=p.source_url,
            )
            db.add(row)
            ind_new += 1

    news = provider.fetch_news()
    news_new = 0
    for n in news:
        exists = db.scalar(select(MarketEvent.id).where(MarketEvent.title == n.title))
        if exists:
            continue
        db.add(MarketEvent(
            event_date=_parse_date(n.published), title=n.title[:255], summary=n.summary,
            source_url=n.source_url, relevance=n.relevance,
            data_origin=DataOrigin.REAL.value,
            verification_status=VerificationStatus.AI_EXTRACTED.value,
            # source_reference is short (255): store the source NAME; the full
            # (long) article URL lives in source_url (1024).
            extraction_method=n.source, source_reference=n.source[:255], confidence=n.relevance,
        ))
        news_new += 1

    db.commit()
    return {
        "provider": provider.name,
        "indicators_ingested": ind_new,
        "indicators_updated": ind_updated,
        "news_ingested": news_new,
        "sources": sorted({p.source for p in indicators} | {n.source for n in news}),
        "as_of": date.today().isoformat(),
    }


def _label_for(indicator: str) -> str:
    labels = {
        "inflation_cpi_yoy": "Inflation (CPI, annual %)",
        "gdp_growth": "GDP growth (annual %)",
        "lending_rate": "Lending interest rate (%)",
        "official_fx_usd": "Official FX (NGN/USD, World Bank annual avg)",
        "fx_usd_ngn": "USD → NGN (interbank ref; parallel rate differs)",
        "fx_eur_ngn": "EUR → NGN (interbank ref)",
        "fx_gbp_ngn": "GBP → NGN (interbank ref)",
        "fx_cny_ngn": "CNY → NGN (interbank ref)",
    }
    return labels.get(indicator, indicator)


def latest_indicators(db: Session) -> list[dict]:
    """Most recent observation per indicator, with provenance and implication."""
    # Latest period per indicator.
    sub = (
        select(EconomicData.indicator, func.max(EconomicData.period).label("mx"))
        .group_by(EconomicData.indicator)
        .subquery()
    )
    rows = db.scalars(
        select(EconomicData)
        .join(sub, (EconomicData.indicator == sub.c.indicator) & (EconomicData.period == sub.c.mx))
        .order_by(EconomicData.indicator)
    ).all()
    return [
        {
            "indicator": r.indicator,
            "label": _label_for(r.indicator),
            "value": float(r.value),
            "unit": r.unit,
            "period": r.period.isoformat(),
            "source": r.extraction_method,
            "source_url": r.source_reference,
            "data_origin": r.data_origin,
            "implication": IMPLICATIONS.get(r.indicator),
        }
        for r in rows
    ]


def recent_events(db: Session, limit: int = 20, min_relevance: float = 0.0) -> list[dict]:
    stmt = select(MarketEvent).where(MarketEvent.relevance >= min_relevance)
    rows = db.scalars(
        stmt.order_by(MarketEvent.event_date.desc(), MarketEvent.relevance.desc()).limit(limit)
    ).all()
    return [
        {
            "id": e.id,
            "title": e.title,
            "summary": e.summary,
            "source": e.extraction_method,
            "source_url": e.source_url,
            "published": e.event_date.isoformat(),
            "relevance": e.relevance,
            "data_origin": e.data_origin,
        }
        for e in rows
    ]


def market_summary(db: Session) -> dict:
    indicators = latest_indicators(db)
    events = recent_events(db, limit=6, min_relevance=0.25)
    return {
        "indicators": indicators,
        "top_news": events,
        "has_data": bool(indicators or events),
        "note": "External facts with provenance. 'Implications' are ASSUMPTIONS / POSSIBLE "
                "IMPACTS, not certainties — run a scenario to quantify them.",
        "provenance": "REAL",
    }
