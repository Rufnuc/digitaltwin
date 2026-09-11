"""Phase 6: market intelligence (real-data parsers, ingestion, endpoints)."""
from __future__ import annotations

from app.services.market_intelligence import ingest
from app.services.market_intelligence.base import EconomicPoint, MarketNews
from app.services.market_intelligence.live import (
    parse_fx,
    parse_rss,
    parse_worldbank,
    score_relevance,
)

# --- Fixtures mirroring the real API shapes (so parsers are tested offline) ---
WB_PAYLOAD = [
    {"page": 1},
    [
        {"date": "2025", "value": None, "indicator": {"id": "FP.CPI.TOTL.ZG"}},
        {"date": "2024", "value": 33.24, "indicator": {"id": "FP.CPI.TOTL.ZG"}},
        {"date": "2023", "value": 24.66, "indicator": {"id": "FP.CPI.TOTL.ZG"}},
    ],
]
FX_PAYLOAD = {
    "result": "success", "time_last_update_unix": 1757635200,
    "rates": {"NGN": 1326.03, "EUR": 0.92, "GBP": 0.79, "USD": 1.0},
}
RSS_XML = """<?xml version="1.0"?><rss><channel>
  <item><title>Naira weakens as inflation climbs</title>
    <link>https://news.example/1</link>
    <description>The naira fell against the dollar amid rising import costs.</description>
    <pubDate>Fri, 11 Sep 2026 08:00:00 GMT</pubDate></item>
  <item><title>Local football results</title><link>https://news.example/2</link>
    <description>Weekend fixtures.</description>
    <pubDate>Thu, 10 Sep 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


class StubProvider:
    name = "stub"

    def fetch_indicators(self):
        return [
            EconomicPoint("inflation_cpi_yoy", "Inflation", "2024-12-31", 33.24, "%",
                          "World Bank", "https://data.worldbank.org/x"),
            EconomicPoint("fx_usd_ngn", "USD→NGN", "2026-09-11", 1326.03, "NGN/USD",
                          "open.er-api.com", "https://open.er-api.com/v6/latest/USD"),
        ]

    def fetch_news(self):
        return [MarketNews("Naira weakens as inflation climbs", "…", "Google News",
                           "https://news.example/1", "2026-09-11", 0.75)]


def test_parse_worldbank_takes_latest_non_null():
    pt = parse_worldbank("inflation_cpi_yoy", "Inflation", "%", WB_PAYLOAD)
    assert pt is not None
    assert pt.value == 33.24 and pt.period == "2024-12-31"  # skips the null 2025
    assert pt.source == "World Bank"


def test_parse_fx_computes_cross_rates():
    pts = {p.indicator: p for p in parse_fx(FX_PAYLOAD)}
    assert pts["fx_usd_ngn"].value == 1326.03
    assert pts["fx_eur_ngn"].value == round(1326.03 / 0.92, 2)
    assert pts["fx_gbp_ngn"].unit == "NGN/GBP"


def test_relevance_scoring_and_rss():
    assert score_relevance("naira inflation import fuel") >= 0.75
    assert score_relevance("football weekend fixtures") == 0.0
    news = parse_rss(RSS_XML)
    assert len(news) == 2
    assert news[0].relevance > news[1].relevance  # economics item ranks higher
    assert news[0].source_url == "https://news.example/1"


def test_ingest_stores_provenance_and_dedupes(db):
    r1 = ingest.refresh_market_data(db, StubProvider())
    assert r1["indicators_ingested"] == 2 and r1["news_ingested"] == 1
    inds = ingest.latest_indicators(db)
    infl = next(i for i in inds if i["indicator"] == "inflation_cpi_yoy")
    assert infl["value"] == 33.24
    assert infl["data_origin"] == "REAL"
    assert infl["source"] == "World Bank"
    assert infl["implication"]  # transparent labelled hint present

    # Second run: same period updates (not duplicates), same news skipped.
    r2 = ingest.refresh_market_data(db, StubProvider())
    assert r2["indicators_ingested"] == 0 and r2["indicators_updated"] == 2
    assert r2["news_ingested"] == 0


def test_market_summary_and_events(db):
    ingest.refresh_market_data(db, StubProvider())
    summ = ingest.market_summary(db)
    assert summ["has_data"] is True
    assert any(i["indicator"] == "fx_usd_ngn" for i in summ["indicators"])
    assert "ASSUMPTION" in summ["note"]


def test_refresh_endpoint_not_configured_returns_400(client, auth_headers):
    # Tests pin MARKET_DATA_PROVIDER=none -> honest "not configured", never fabricated.
    r = client.post("/api/v1/market/refresh", headers=auth_headers("ANALYST"))
    assert r.status_code == 400


def test_market_read_endpoints(client, auth_headers, db, monkeypatch):
    monkeypatch.setattr(ingest, "get_market_provider", lambda: StubProvider())
    ok = client.post("/api/v1/market/refresh", headers=auth_headers("ANALYST"))
    assert ok.status_code == 200, ok.text
    assert ok.json()["indicators_ingested"] == 2

    inds = client.get("/api/v1/market/indicators", headers=auth_headers("VIEWER"))
    assert inds.status_code == 200
    assert any(i["indicator"] == "inflation_cpi_yoy" for i in inds.json()["items"])
