# Business intelligence (Phase 2)

All analytics live in `app/services/bi/` and are exposed under `/api/v1/analytics`.
Every figure is computed from stored records and tagged `MODEL_OUTPUT`; nothing is
invented, and where evidence is insufficient the system says so rather than
guessing (spec §50).

## Customer intelligence — `bi/customers.py` → `GET /analytics/customers`
Per-customer revenue, gross profit, margin, orders, AOV, recency, and the
customer's own average purchase interval. **Churn is flagged as *risk* only from
evidence**: ≥3 orders AND recency > 1.5× the customer's typical interval — with
the reason attached (e.g. "332d since last order vs ~71d typical interval").
Never asserts a customer "has churned" (spec §24). Also reports concentration
risk (top-1 / top-5 revenue share).

## Product intelligence — `bi/products.py` → `GET /analytics/products`
Revenue, units, gross profit and margin per product; best sellers, most
profitable, slow movers, and **dead stock** (on-hand quantity but zero sales in
the dataset) (spec §25).

## Supplier analytics — `bi/suppliers.py` → `GET /analytics/suppliers`
Spend (from purchases), product counts, lead time and reliability per supplier —
the base for Phase 3 supplier-risk simulation (spec §27).

## Financial analytics — `bi/financials.py` → `GET /analytics/financials`
Monthly P&L series: revenue → COGS → gross profit → operating expenses → net
profit, with gross/net margins. Reuses the single `analytics.pnl` identity so the
numbers reconcile with the dashboard and simulations.

## Data quality — `bi/data_quality.py` → `GET /analytics/data-quality`
Transparent checks, each returning category, severity, count and sample ids:
line/invoice arithmetic errors, unmatched product/customer, duplicate invoice
numbers, non-positive margin, missing product values, and `NEEDS_REVIEW` flags.
The **score** is an explicit weighted ratio — `100 × (1 − Σ(weightₛₑᵥ × count) /
records_checked)` — not a black box (spec §43, §51).

## Ingestion — `services/ingestion.py` → `/api/v1/imports`
CSV pipeline: `UPLOAD → PREVIEW → MAP → VALIDATE → DEDUPE → IMPORT → AUDIT`.
Importable entities are a registry (`ENTITY_SPECS`): customers, products,
expenses today; adding one is a single entry. Each run creates a `DataImport`
batch (row counts, status) and audit entry; imported rows are `REAL`-origin with
`extraction_method = csv_import`, so real data coexists with demo data under
clear provenance. Supports incremental, batched historical migration (spec §42).
