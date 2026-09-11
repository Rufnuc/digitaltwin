"""Market-intelligence provider abstraction (spec §30, Phase 6).

External facts must always retain provenance (source, date, url, confidence).
Phase 1 defines the seam; no external calls are made.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass
class MarketDatum:
    title: str
    summary: str
    source_url: str
    published: date
    confidence: float


class MarketDataProvider(Protocol):
    def fetch_recent(self, query: str) -> list[MarketDatum]: ...


class NullMarketDataProvider:
    def fetch_recent(self, query: str) -> list[MarketDatum]:
        raise NotImplementedError(
            "Market-data provider not configured. Market intelligence is a Phase 6 capability."
        )


def get_market_provider() -> MarketDataProvider:
    return NullMarketDataProvider()
