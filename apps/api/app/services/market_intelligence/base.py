"""Market-intelligence provider abstraction (spec §30).

External facts ALWAYS retain provenance (source, date, url, confidence) and are
never treated as unquestionable truth. Providers here fetch **real** economic
data — World Bank indicators, live FX, and Google News — for the business's
market (Nigeria). HTTP fetching is separated from parsing so parsers are unit-
tested without network access.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


@dataclass
class EconomicPoint:
    indicator: str        # machine key, e.g. "inflation_cpi_yoy"
    label: str            # human label
    period: str           # ISO date (YYYY-MM-DD)
    value: float
    unit: str
    source: str
    source_url: str
    confidence: float = 1.0


@dataclass
class MarketNews:
    title: str
    summary: str
    source: str
    source_url: str
    published: str        # ISO date
    relevance: float


class MarketDataProvider(Protocol):
    name: str

    def fetch_indicators(self) -> list[EconomicPoint]: ...
    def fetch_news(self) -> list[MarketNews]: ...


class NullMarketDataProvider:
    name = "none"

    def fetch_indicators(self) -> list[EconomicPoint]:
        raise NotImplementedError(
            "Market-data provider not configured. Set MARKET_DATA_PROVIDER=live."
        )

    def fetch_news(self) -> list[MarketNews]:
        raise NotImplementedError(
            "Market-data provider not configured. Set MARKET_DATA_PROVIDER=live."
        )


def get_market_provider() -> MarketDataProvider:
    provider = (settings.MARKET_DATA_PROVIDER or "none").lower()
    if provider in ("live", "real"):
        # Imported lazily so the app runs without network when the feature is off.
        from app.services.market_intelligence.live import LiveMarketProvider

        return LiveMarketProvider()
    return NullMarketDataProvider()
