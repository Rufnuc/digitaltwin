# Architecture

DigitalTwin is a modular platform for building a **digital twin of a real
business** and running decision-support simulations against it. This document
describes the Phase 1 foundation and the seams reserved for later phases.

## Guiding principles

1. **The LLM is not the simulation engine.** User intent is parsed into a
   *structured* scenario; a deterministic engine computes numbers; the LLM (a
   later phase) only explains them. No numerical result is ever invented.
2. **Every value declares its epistemic status.** `DataOrigin` —
   `REAL / DEMO / ESTIMATED / MISSING / ASSUMPTION / MODEL_OUTPUT / FORECAST /
   AI_INTERPRETATION` — is attached to business records and surfaced in the UI.
3. **Separation of concerns.** Frontend, API, analytics, and simulation are
   decoupled; AI / OCR / market-data are provider abstractions with no Phase-1
   implementation.
4. **Progressive data.** The system is useful with demo data and stays useful as
   real and historical (paper-invoice) data is ingested in batches.

## High-level shape

```
apps/web (Next.js)  ──HTTP──▶  apps/api (FastAPI)
                                  │
                                  ├─ services/analytics      financial calcs (single source)
                                  ├─ services/simulation     engine registry + deterministic engines
                                  ├─ services/audit          audit trail
                                  ├─ services/storage        object-storage abstraction (local driver)
                                  ├─ services/ai             provider seam (Phase 4, no impl)
                                  ├─ services/document_processing  OCR seam (Phase 5, no impl)
                                  └─ services/market_intelligence  market seam (Phase 6, no impl)
                                  │
                                  ▼
                             PostgreSQL (Alembic-migrated)
```

## Request flow: a simulation

```
User → scenario builder (web)
     → POST /simulations         (store SimulationRun, status PENDING)
     → POST /simulations/{id}/run
          → analytics.baseline_economics(db)     (facts from invoices)
          → engine.run(request, baseline)        (deterministic math)
          → persist SimulationResult rows        (MODEL_OUTPUT)
     → results table + assumptions + warnings (web)
```

The engine is chosen from a **registry** keyed by `scenario_type`, so new
scenario kinds (demand, supplier-cost, Monte Carlo…) are added in Phase 3 without
touching the API or the UI contract.

## Portability decision

Models use portable SQLAlchemy types (`JSON` not `JSONB`, string-backed enums) so
the identical models run on **Postgres** (app/prod, Alembic-migrated) and
**SQLite** (fast unit tests, zero-infra dev). Enum values are validated at the
Pydantic layer.

## What is intentionally NOT built in Phase 1

OCR/handwriting, AI assistant, Monte Carlo, forecasting, market ingestion,
agents. Each has a documented interface (`services/*/base.py`) and a place in the
schema, but no implementation — see `docs/*` and the phase plan in the README.
