# DigitalTwin — AI Business Digital Twin & Decision Support Platform

Build a **digital twin of a real business** and let its owner test decisions
before making them — *"what happens if I raise prices 10%?"* — with numbers that
come from a deterministic simulation engine, never from an LLM.

This repository is the **Phase 1 foundation**: a modular, tested, documented base
with clean seams for every future capability (simulation depth, AI assistant,
OCR of ~200k historical paper invoices, market intelligence, agents).

## The two rules that shape everything
1. **The LLM never invents numbers.** Intent → structured scenario → engine →
   results → (later) LLM explanation.
2. **Every value declares its status:** `REAL / DEMO / ESTIMATED / MISSING /
   ASSUMPTION / MODEL_OUTPUT / FORECAST / AI_INTERPRETATION`.

## Stack
- **Web** — Next.js 15 + TypeScript (plain black-and-white UI), `apps/web`
- **API** — FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic (python3.10), `apps/api`
- **DB** — PostgreSQL (Docker); tests run on SQLite for speed
- **Simulation** — NumPy-ready deterministic engine registry, `apps/api/app/services/simulation`

## Quick start
```bash
# 1) Postgres
docker-compose up -d db

# 2) API
cd apps/api
~/.local/bin/python3.10 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg://digitaltwin:digitaltwin@localhost:5432/digitaltwin"
alembic upgrade head
python -m app.seed.demo_data --reset
uvicorn app.main:app --reload --port 8000     # http://localhost:8000/docs

# 3) Web (new terminal)
cd apps/web && npm install && npm run dev      # http://localhost:3000
```
Set `apps/web/.env.local` → `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.

> **Docker on this machine is Colima.** If `docker-compose` errors on a
> credential helper, see `docs/development.md` for the one-line `DOCKER_CONFIG` /
> `DOCKER_HOST` workaround.

## Demo accounts (seeded, dev only)
| Role | Email | Password |
|---|---|---|
| Owner | `owner@demo.example.com` | `owner12345` |
| Admin | `admin@demo.example.com` | `admin12345` |
| Analyst | `analyst@demo.example.com` | `analyst12345` |
| Viewer | `viewer@demo.example.com` | `viewer12345` |

## Tests
```bash
cd apps/api && . .venv/bin/activate && pytest   # 19 passing (SQLite, no infra)
ruff check .
```

## Documentation
`docs/`: architecture · database · api · simulation · analytics · data-model ·
data-ingestion · ai · market-intelligence · development · deployment.

## Environment
Copy `.env.example` → `.env`. Secrets (`AUTH_SECRET`, DB, provider keys) come from
the environment; `.env` is git-ignored.

## Phase roadmap
1. **Foundation ✅** — schema, auth+RBAC, entities, dashboard, demo data,
   audit, tests, docs.
2. **Business intelligence ✅** — CSV imports, customer/product/supplier/financial
   analytics, data-quality scoring (`/analytics/*`, `/imports`, `docs/analytics.md`).
3. **Simulation depth ✅** — general scenario engines, Monte Carlo (percentiles,
   P(loss), sensitivity), tornado analysis, scenario comparison
   (`/simulations/monte-carlo|sensitivity|compare`, `docs/simulation.md`).
4. AI assistant (LLM abstraction + tool-calling, explanation only).
5. Historical documents (OCR provider, extraction, review queue).
6. Market intelligence. 7. News→impact. 8. Advanced agents.

## Known limitations
- Auth is JWT with a client-side route guard suitable for Phase 1; production
  should add refresh tokens / httpOnly cookies.
- `npm audit` reports advisories in the transitive `sharp` package (used only by
  `next/image`, which this app does not use) and cumulative Next.js dev-server
  advisories. Pin `next` to the latest patched release before production.
- Analytics aggregations (e.g. revenue timeseries) are computed in Python at
  Phase-1 data volumes; Phase 2 pushes them into SQL/materialised views for scale.
- Simulation supports deterministic scenarios (price/demand/supplier-cost/cost),
  Monte Carlo, tornado sensitivity, and comparison. Forecasting, optimization and
  headcount/branch scenarios remain for later phases.
