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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from app.services.market_intelligence.base import EconomicPoint, MarketNews

logger = logging.getLogger("digitaltwin.market")

COUNTRY = "NGA"
# Keep per-request timeouts short and fetch sources concurrently: a refresh must
# return quickly even when a source is slow or unreachable, so the request never
# hangs long enough for the browser/host to drop it (which surfaces as a
# "NetworkError" in the UI). A failing source is skipped, never fabricated.
_TIMEOUT = 6.0
_MAX_WORKERS = 8
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DigitalTwin/1.0; +https://urbanbuilds.com.ng)"}


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

# Focused Google-News feeds for a Nigerian auto-parts import/wholesale business.
# Boolean OR narrows the results to genuinely on-topic stories.
NEWS_URLS = [
    # Nigeria import / FX / ports / auto trade.
    ("https://news.google.com/rss/search?q="
     "Nigeria+(import+OR+customs+OR+%22exchange+rate%22+OR+naira+OR+%22spare+parts%22"
     "+OR+%22auto+parts%22+OR+port+OR+Apapa)+business"
     "&hl=en-NG&gl=NG&ceid=NG:en"),
    # China → Nigeria trade / shipping / manufacturing.
    ("https://news.google.com/rss/search?q="
     "China+(export+OR+shipping+OR+yuan+OR+tariff+OR+manufacturing)+Nigeria+trade"
     "&hl=en&gl=US&ceid=US:en"),
]

# Core terms — a headline is only relevant if it contains at least one of these.
CORE_KEYWORDS = [
    "import", "customs", "tariff", "duty", "naira", "forex", "exchange rate", "dollar",
    "port", "apapa", "tin can", "auto", "spare part", "vehicle", "truck", "tractor",
    "china", "chinese", "yuan", "renminbi", "cbn", "inflation", "shipping", "freight",
    "container", "supply chain", "manufacturing", "clearing", "cargo",
]
# Supporting context terms that add relevance once a core term is present.
CONTEXT_KEYWORDS = [
    "cost", "supply", "transport", "export", "factory", "economy", "price", "fuel",
    "petrol", "diesel", "interest rate", "devaluation", "logistics", "warehouse",
]
# Kept for the shipping-conditions taxonomy import that references it.
BUSINESS_KEYWORDS = CORE_KEYWORDS + CONTEXT_KEYWORDS

MIN_NEWS_RELEVANCE = 0.15  # below this a headline is dropped as off-topic


def _has_word(kw: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(kw)}\b", text) is not None


def score_relevance(text: str) -> float:
    """Whole-word keyword relevance in [0,1]. Zero unless a CORE term is present, so
    incidental matches ('cost', 'car' inside 'career') do not inflate the score."""
    t = (text or "").lower()
    core = sum(1 for kw in CORE_KEYWORDS if _has_word(kw, t))
    if core == 0:
        return 0.0
    ctx = sum(1 for kw in CONTEXT_KEYWORDS if _has_word(kw, t))
    return round(min(1.0, (2 * core + ctx) / 6.0), 3)


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
    # open.er-api.com gives an interbank/aggregate reference rate. Nigeria has
    # several rates (official/NAFEM and parallel market) that can differ a lot, so
    # this may not match a bureau-de-change quote. The label says so honestly.
    lbl = "(interbank ref; parallel rate differs)"
    out = [EconomicPoint("fx_usd_ngn", f"USD → NGN {lbl}", period, round(float(ngn), 2),
                         "NGN/USD", "open.er-api.com", FX_URL)]
    if rates.get("EUR"):
        out.append(EconomicPoint("fx_eur_ngn", f"EUR → NGN {lbl}", period,
                                 round(float(ngn) / float(rates["EUR"]), 2), "NGN/EUR",
                                 "open.er-api.com", FX_URL))
    if rates.get("GBP"):
        out.append(EconomicPoint("fx_gbp_ngn", f"GBP → NGN {lbl}", period,
                                 round(float(ngn) / float(rates["GBP"]), 2), "NGN/GBP",
                                 "open.er-api.com", FX_URL))
    if rates.get("CNY"):
        out.append(EconomicPoint("fx_cny_ngn", f"CNY → NGN {lbl}", period,
                                 round(float(ngn) / float(rates["CNY"]), 2), "NGN/CNY",
                                 "open.er-api.com", FX_URL))
    return out


def _norm_title(title: str) -> str:
    """Normalise a headline for dedup: drop the trailing ' - Publisher', lowercase,
    keep only words. Near-identical stories from different outlets collapse."""
    t = re.sub(r"\s+-\s+[^-]+$", "", title or "")  # strip " - Publisher" suffix
    t = re.sub(r"[^a-z0-9 ]", "", t.lower())
    return re.sub(r"\s+", " ", t).strip()


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


def diagnose_sources() -> list[dict]:
    """Connectivity check from the server to each market-data source — isolates
    'can the server reach the internet' from parsing. Returns per-source status."""
    import time

    checks = [
        ("World Bank", _wb_url(WB_INDICATORS[0][3])),
        ("FX (open.er-api.com)", FX_URL),
        ("Google News", NEWS_URLS[0]),
    ]
    out: list[dict] = []
    with _client() as c:
        for name, url in checks:
            t = time.monotonic()
            try:
                r = c.get(url)
                ms = int((time.monotonic() - t) * 1000)
                out.append({
                    "source": name, "ok": bool(r.is_success), "status": r.status_code,
                    "ms": ms, "error": None if r.is_success else f"HTTP {r.status_code}",
                })
            except Exception as e:  # noqa: BLE001 — report any failure verbatim
                ms = int((time.monotonic() - t) * 1000)
                out.append({
                    "source": name, "ok": False, "status": None, "ms": ms,
                    "error": f"{type(e).__name__}: {e}"[:200],
                })
    return out


def _run(jobs: list, fn) -> list:
    """Run fn over jobs concurrently; if threads can't start (constrained/serverless
    host), fall back to running them one after another. Never raises."""
    try:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            return list(ex.map(fn, jobs))
    except (RuntimeError, OSError) as e:  # e.g. "can't start new thread"
        logger.warning("thread pool unavailable (%s) — fetching sequentially", e)
        return [fn(j) for j in jobs]


class LiveMarketProvider:
    name = "live"

    def __init__(self) -> None:
        # Per-source failures collected during a refresh, surfaced to the UI so the
        # owner can see exactly which source is unreachable (and why) rather than a
        # blanket error.
        self.errors: list[dict] = []

    def _note_error(self, source: str, exc: Exception) -> None:
        kind = type(exc).__name__
        self.errors.append({"source": source, "error": f"{kind}: {exc}"[:300]})
        logger.warning("%s fetch failed: %s: %s", source, kind, exc)

    def fetch_indicators(self) -> list[EconomicPoint]:
        points: list[EconomicPoint] = []
        with _client() as client:
            def wb(args):
                key, label, unit, code = args
                try:
                    return ("wb", parse_worldbank(key, label, unit, client.get(_wb_url(code)).json()))
                except Exception as e:  # noqa: BLE001 — isolate a single source's failure
                    self._note_error(f"World Bank ({code})", e)
                    return ("wb", None)

            def fx(_):
                try:
                    return ("fx", parse_fx(client.get(FX_URL).json()))
                except Exception as e:  # noqa: BLE001
                    self._note_error("FX (open.er-api.com)", e)
                    return ("fx", [])

            jobs = [(wb, a) for a in WB_INDICATORS] + [(fx, None)]
            for kind, result in _run(jobs, lambda j: j[0](j[1])):
                if kind == "wb" and result is not None:
                    points.append(result)
                elif kind == "fx":
                    points.extend(result)
        return points

    def fetch_news(self) -> list[MarketNews]:
        seen: set[str] = set()
        items: list[MarketNews] = []
        with _client() as c:
            def fetch(url):
                try:
                    return parse_rss(c.get(url).text)
                except Exception as e:  # noqa: BLE001
                    self._note_error("Google News", e)
                    return []

            for batch in _run(NEWS_URLS, fetch):
                for n in batch:
                    # Drop off-topic headlines; dedup near-duplicates (same story
                    # from different publishers share a normalised title).
                    if (n.relevance or 0) < MIN_NEWS_RELEVANCE:
                        continue
                    key = _norm_title(n.title)
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    items.append(n)
        # Best (most relevant) first.
        items.sort(key=lambda n: n.relevance or 0, reverse=True)
        return items
