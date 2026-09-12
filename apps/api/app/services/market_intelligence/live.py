"""Live market-intelligence sources (spec §30).

Real, free, no-key sources for the business's market (Nigeria):
  - World Bank indicators (inflation, GDP growth, lending rate, official FX)
  - open.er-api.com live exchange rates (USD/EUR/GBP → NGN)
  - Google News RSS (business/economy headlines)

Parsing is pure and separated from HTTP so it is unit-tested without network.
Fetching is resilient: a failing source is skipped, never fabricated.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from app.services.market_intelligence.base import EconomicPoint, MarketNews

logger = logging.getLogger("digitaltwin.market")

COUNTRY = "NGA"
_TIMEOUT = 15.0
_HEADERS = {"User-Agent": "DigitalTwin/1.0"}


def _client() -> httpx.Client:
    # follow_redirects is required — Google News feeds 302 to a canonical URL.
    return httpx.Client(timeout=_TIMEOUT, follow_redirects=True, headers=_HEADERS)

# World Bank indicator catalogue (key, label, unit, WB series code).
WB_INDICATORS = [
    ("inflation_cpi_yoy", "Inflation, consumer prices (annual %)", "%", "FP.CPI.TOTL.ZG"),
    ("gdp_growth", "GDP growth (annual %)", "%", "NY.GDP.MKTP.KD.ZG"),
    ("lending_rate", "Lending interest rate (%)", "%", "FR.INR.LEND"),
    ("official_fx_usd", "Official exchange rate (NGN per USD, avg)", "NGN/USD", "PA.NUS.FCRF"),
]

FX_URL = "https://open.er-api.com/v6/latest/USD"

# Two real Google-News feeds: local Nigerian business, and China/Asia trade —
# most imported parts come from China, so Chinese economic news is material.
NEWS_URLS = [
    ("https://news.google.com/rss/search"
     "?q=Nigeria+economy+naira+inflation+fuel+import+business"
     "&hl=en-NG&gl=NG&ceid=NG:en"),
    ("https://news.google.com/rss/search"
     "?q=China+yuan+exports+manufacturing+Nigeria+trade+shipping+tariff"
     "&hl=en&gl=US&ceid=US:en"),
]

# Terms that make a headline relevant to an auto-parts import/wholesale business
# sourcing from China (and the West).
BUSINESS_KEYWORDS = [
    "naira", "inflation", "fuel", "petrol", "diesel", "import", "customs", "tariff",
    "exchange rate", "forex", "fx", "dollar", "port", "supply", "vehicle", "auto",
    "spare part", "car", "transport", "interest rate", "cbn", "manufacturing", "cost",
    "china", "chinese", "yuan", "renminbi", "rmb", "export", "shipping", "container",
    "shenzhen", "guangzhou", "factory", "supply chain",
]


def score_relevance(text: str) -> float:
    """Transparent keyword relevance in [0,1] for the business's context."""
    t = (text or "").lower()
    hits = sum(1 for kw in BUSINESS_KEYWORDS if kw in t)
    return round(min(hits / 4.0, 1.0), 3)


def _wb_url(code: str) -> str:
    return (
        f"https://api.worldbank.org/v2/country/{COUNTRY}/indicator/{code}"
        f"?format=json&per_page=60&date=2010:2026"
    )


def parse_worldbank(key: str, label: str, unit: str, payload) -> EconomicPoint | None:
    """Return the most recent non-null observation as an EconomicPoint."""
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return None
    for row in payload[1]:  # WB returns newest-first
        value = row.get("value")
        if value is None:
            continue
        year = row.get("date")
        return EconomicPoint(
            indicator=key,
            label=label,
            period=f"{year}-12-31",
            value=float(value),
            unit=unit,
            source="World Bank",
            source_url=f"https://data.worldbank.org/indicator/"
                       f"{row.get('indicator', {}).get('id', '')}?locations=NG",
            confidence=1.0,
        )
    return None


def parse_fx(payload: dict) -> list[EconomicPoint]:
    if payload.get("result") != "success":
        return []
    rates = payload.get("rates", {})
    ngn = rates.get("NGN")
    if not ngn:
        return []
    ts = payload.get("time_last_update_unix")
    period = (
        datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        if ts else datetime.now(timezone.utc).date().isoformat()
    )
    out = [EconomicPoint("fx_usd_ngn", "Exchange rate USD → NGN", period, round(float(ngn), 2),
                         "NGN/USD", "open.er-api.com", FX_URL)]
    if rates.get("EUR"):
        out.append(EconomicPoint("fx_eur_ngn", "Exchange rate EUR → NGN", period,
                                 round(float(ngn) / float(rates["EUR"]), 2), "NGN/EUR",
                                 "open.er-api.com", FX_URL))
    if rates.get("GBP"):
        out.append(EconomicPoint("fx_gbp_ngn", "Exchange rate GBP → NGN", period,
                                 round(float(ngn) / float(rates["GBP"]), 2), "NGN/GBP",
                                 "open.er-api.com", FX_URL))
    if rates.get("CNY"):
        out.append(EconomicPoint("fx_cny_ngn", "Exchange rate CNY → NGN", period,
                                 round(float(ngn) / float(rates["CNY"]), 2), "NGN/CNY",
                                 "open.er-api.com", FX_URL))
    return out


def parse_rss(xml_text: str, limit: int = 15) -> list[MarketNews]:
    out: list[MarketNews] = []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return out
    for item in root.iterfind(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = item.findtext("pubDate")
        try:
            published = parsedate_to_datetime(pub).date().isoformat() if pub else ""
        except (TypeError, ValueError):
            published = ""
        # Plain-text summary: strip HTML tags and unescape entities (RSS
        # descriptions carry HTML like &nbsp; that is not valid XML).
        summary = html.unescape(re.sub(r"<[^>]+>", " ", desc)).strip() if desc else ""
        summary = re.sub(r"\s+", " ", summary)
        out.append(MarketNews(
            title=title, summary=summary[:400], source="Google News",
            source_url=link, published=published,
            relevance=score_relevance(f"{title} {summary}"),
        ))
        if len(out) >= limit:
            break
    return out


class LiveMarketProvider:
    name = "live"

    def fetch_indicators(self) -> list[EconomicPoint]:
        points: list[EconomicPoint] = []
        with _client() as client:
            for key, label, unit, code in WB_INDICATORS:
                try:
                    r = client.get(_wb_url(code))
                    pt = parse_worldbank(key, label, unit, r.json())
                    if pt:
                        points.append(pt)
                except (httpx.HTTPError, ValueError) as e:
                    logger.warning("World Bank fetch failed for %s: %s", code, e)
            try:
                r = client.get(FX_URL)
                points.extend(parse_fx(r.json()))
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("FX fetch failed: %s", e)
        return points

    def fetch_news(self) -> list[MarketNews]:
        seen: set[str] = set()
        items: list[MarketNews] = []
        with _client() as c:
            for url in NEWS_URLS:  # local Nigerian feed + China/Asia trade feed
                try:
                    for n in parse_rss(c.get(url).text):
                        if n.title and n.title not in seen:
                            seen.add(n.title)
                            items.append(n)
                except httpx.HTTPError as e:
                    logger.warning("News fetch failed for %s: %s", url, e)
        return items
