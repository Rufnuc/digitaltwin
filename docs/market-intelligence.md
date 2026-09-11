# Market Intelligence (Phase 6)

Real external economic data for the business's market (Nigeria), with mandatory
provenance. Nothing here is fabricated — every value keeps its source, date, URL
and confidence, and "implications" are explicitly labelled ASSUMPTION / POSSIBLE
IMPACT, never asserted as fact (spec §30).

## Sources (real, free, no key)

- **World Bank** indicators for Nigeria: inflation (CPI, annual %), GDP growth,
  lending interest rate, official FX (NGN/USD).
- **open.er-api.com** live exchange rates: USD/EUR/GBP → NGN (cross-rates
  computed from the USD base).
- **Google News RSS**: business/economy headlines, scored for relevance to the
  business (naira, fuel, import, FX, inflation, …).

## Architecture

```
POST /market/refresh  → provider.fetch_indicators() + fetch_news()  (real HTTP)
                      → upsert economic_data / market_events with provenance
GET  /market/indicators | /market/events | /market/summary  → read from DB
```

- **Provider abstraction** (`services/market_intelligence/base.py`) — real
  providers behind one seam; selected by `MARKET_DATA_PROVIDER` (`live` by
  default, `none` disables). Parsing is separated from HTTP (`live.py`) so parsers
  are unit-tested without network.
- **Ingestion** (`ingest.py`) — upserts with dedupe (indicator+period; news by
  title), tags rows `REAL` with source/url/confidence, and never fabricates on a
  network failure (a failing source is skipped, counts reported honestly).
- **Reads never block on the network** — the UI reads stored rows; refresh is an
  explicit user action (Analyst+).

## Endpoints

```
POST /api/v1/market/refresh      (Analyst+) fetch + store real data
GET  /api/v1/market/indicators   latest value per indicator (+ implication)
GET  /api/v1/market/events       news, filterable by ?min_relevance
GET  /api/v1/market/summary      indicators + top relevant news + note
```

## Storage & provenance

Reuses `economic_data` (indicator, period, value, unit + provenance mixin) and
`market_events` (event_date, title, summary, source_url, relevance + provenance).
`source_reference` holds the short source name; the full article URL lives in
`source_url` (1024).

## Next (Phase 7 — news → business impact)

This subsystem is the input to Phase 7: classify a market event → affected
suppliers/products/costs → auto-generate a scenario → run the simulation engine,
clearly separating FACT / ASSUMPTION / POSSIBLE IMPACT / SIMULATION.
