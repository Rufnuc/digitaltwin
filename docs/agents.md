# Digital Twin — Multi-Agent Simulation (Phase 8)

Simulated **customer / supplier / competitor / market** agents play the business
forward month by month in a stochastic (Monte Carlo) simulation. Agents are
**calibrated from real historical data** and constrained by **explicit behavioural
assumptions**; outputs are FORECASTS with uncertainty — simulated behaviour is
never presented as real-world fact (spec §33, §34).

## Provenance of the pieces

| Piece | Origin | Source |
|---|---|---|
| Calibration inputs | `REAL` | customer metrics, unit economics, latest inflation |
| Behavioural parameters | `ASSUMPTION` | elasticity, churn, competitor index, drift |
| Agent decisions | SIMULATED BEHAVIOUR | monthly purchase/churn draws |
| Outcome distribution | `FORECAST` | percentiles over iterations |

## Agents (`services/agents/simulation.py`)

- **Customer** (one per real customer) — buys on its own historical cadence
  (`purchase_prob` from avg interval), orders its historical size, may churn
  (hazard raised for customers already flagged at risk), and responds to our price
  (elasticity) and the competitor's price.
- **Supplier** (aggregate) — unit cost drifts up with real inflation (+ optional FX
  depreciation).
- **Competitor** (1) — prices relative to our baseline; a price premium on our side
  loses demand.
- **Market** (1) — macro conditions (real inflation) dampen real demand and push
  costs up.

The simulation is **vectorised with NumPy** (customers as arrays) and seeded, so it
is fast and reproducible.

## Endpoints

```
GET  /api/v1/agents/roster                 the agents + default assumptions
POST /api/v1/agents/simulate   (Analyst+)  run one policy → forecast distribution
POST /api/v1/agents/compare    (Analyst+)  rank several strategies by expected profit
```

`simulate` body: `{ policy: {price_change_percent, monthly_opex_delta}, horizon_months,
iterations, assumptions, seed }`. Returns the cumulative net-profit distribution
(p5/p50/p95/mean), the monthly net-profit path (percentiles per month), probability
of cumulative loss, and expected active customers at the end.

## What it shows

A worked example on the demo data (real 23% inflation calibrated in): holding
prices leaves the business expected-loss-making (costs drift up, customers churn),
while raising prices ~10–15% restores a positive expected outcome — consistent with
the Phase 7 impact finding. The twin quantifies the trade-off (upside vs. probability
of loss vs. customer retention) rather than asserting a single answer.

## Boundaries
Agent behaviour is a model, not reality. Every number is a forecast conditioned on
the stated assumptions; the UI labels calibration (REAL), assumptions (ASSUMPTION)
and outcomes (FORECAST) separately, and the platform never presents simulated
behaviour as an observed fact (spec §33).
