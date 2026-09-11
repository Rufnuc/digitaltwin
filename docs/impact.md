# News → Business Impact (Phase 7)

Turns a **real** market signal into a quantified, clearly-labelled impact
assessment (spec §31). The chain, and its provenance, is explicit end to end:

```
FACT (observed real data)          → REAL        e.g. inflation 23% (World Bank)
  → ASSUMPTION (mapping+magnitude)  → ASSUMPTION  e.g. 40% flows to unit cost → +9.2%
  → POSSIBLE IMPACT (who/what)      → —           affected suppliers/products/costs/customers
  → SIMULATION (deterministic)      → MODEL_OUTPUT the same engine used elsewhere
  → RISK  → RECOMMENDED ACTION
```

Possibility is never presented as certainty: the observed indicator is `REAL`, the
mapping to a scenario lever is an `ASSUMPTION`, and the numbers are `MODEL_OUTPUT`.

## Drivers (`services/impact/engine.py`)

- **Inflation** — FACT = latest CPI (World Bank). ASSUMPTION = `cost_passthrough`
  (default 0.4) → `unit_cost_change_percent`. Affects all costs/products/customers.
- **FX / import cost** — FACT = current USD→NGN. ASSUMPTION = `fx_shock_pct`
  (default 10) × `import_share` (default 0.6) → `unit_cost_change_percent`. Affected
  suppliers are found from real data (`location LIKE 'Import%'`) and their products.

Each assessment runs the shared projection model, reports revenue/gross/net deltas,
and is flagged **material** when net profit moves ≥ 5%. Material assessments raise a
dashboard `Alert` (category `market_impact`, `data_origin = MODEL_OUTPUT` — a
model-derived possibility, not an observed fact).

## Endpoints

```
POST /api/v1/impact/scan     (Analyst+)  assess current signals; optionally raise alerts
GET  /api/v1/impact/drivers  (Analyst+)  driver list + default assumptions
```

`POST /impact/scan` body: `{ "assumptions": {...}, "create_alerts": true }`.

## Why the numbers can be dramatic

A thin-margin business is highly sensitive to cost shocks: with net margin ~8–9%,
an inflation-driven ~9% rise in unit cost (COGS ≈ 60% of revenue) can cut net
profit by more than half. That is a real, honest consequence of the arithmetic —
surfaced, with its assumptions, so the owner can act (e.g. run a price-change
simulation to find the increase that restores margin).

## Next (Phase 8)
Simulated agents (customer/supplier/competitor/market) and multi-agent digital-twin
scenarios built on these same engines and real signals.
