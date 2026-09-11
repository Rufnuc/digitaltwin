# Market Intelligence (Phase 6 — interface only)

No external calls in Phase 1. The seam lives in
`app/services/market_intelligence/base.py`: `MarketDataProvider` returning
`MarketDatum` records that always carry `source_url`, `published`, and
`confidence`. Storage exists now: `market_events` and `economic_data` tables
(both provenance-tracked).

External information is **never** treated as unquestionable truth — source,
date, URL, extracted fact, relevance and confidence are always retained
(spec §30). Phase 7 ("news → business impact") turns a classified market event
into affected suppliers/products/costs → an auto-generated scenario → a
simulation, clearly separating FACT / ASSUMPTION / POSSIBLE IMPACT.
