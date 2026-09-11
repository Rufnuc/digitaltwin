# Simulation engine

## Contract

The engine is the **only** producer of simulation numbers. An engine implements:

```python
class SimulationEngine(Protocol):
    scenario_type: str
    model_name: str
    model_version: str
    def run(self, request: ScenarioRequest, baseline: BaselineEconomics) -> ScenarioOutput: ...
```

Engines self-register in a registry keyed by `scenario_type`
(`services/simulation/base.py`). The runner (`runner.py`) builds the baseline
from real data (`analytics.baseline_economics`), dispatches, and persists results.

## Phase 1 engine: `price_change` (deterministic)

Closed-form, transparent, constant-elasticity:

```
demand_change%  = elasticity × price_change%          (elasticity is an ASSUMPTION)
new_units       = units × (1 + demand_change%/100)
new_price       = avg_price × (1 + price_change%/100)
new_revenue     = new_units × new_price
new_cogs        = avg_unit_cost × new_units           (unit cost held constant)
new_gross_profit= new_revenue − new_cogs
```

Outputs `revenue`, `gross_profit`, `gross_margin`, `units_sold` — each with
baseline, scenario, and delta — plus the explicit assumptions and any warnings
(e.g. insufficient baseline data). Every value is `MODEL_OUTPUT`.

### Worked example (deterministic, from the test suite)

Baseline 1000 units @ $10 (cost $6): a **+10%** price change with elasticity
**−0.8** ⇒ units −8% → 920, revenue $10,120, gross profit $5,120.

## Reproducibility (spec §35, §57, §58)

Each `SimulationRun` stores scenario parameters, assumptions, `model_name`,
`model_version`, and `input_data_version`, so a past result can be explained and
re-run.

## Phase 3 — simulation depth

All Phase 3 capabilities are built on one pure function, `model.project(baseline,
levers)` (`services/simulation/model.py`), so they reconcile with each other and
with the dashboard's `pnl` identity. Levers: `price_pct`, `demand_pct`,
`unit_cost_pct`, `fixed_opex_delta`, `elasticity`. The baseline now carries
`operating_expenses`, so net profit is projected too.

### General deterministic engines — `engines.py`
One `GeneralScenarioEngine` drives `demand_change`, `supplier_cost_change` and
`cost_change` via the shared model (registered alongside `price_change`).

### Monte Carlo — `montecarlo.py` → `POST /simulations/monte-carlo`
Samples uncertain variables from declared distributions (`fixed` / `normal` /
`uniform` / `triangular`), projects each draw, and reports **distributions** per
metric (mean, p5/p25/p50/p75/p95, min/max), **probability of loss**, probability
of hitting a target, and **input sensitivity** (correlation of each varying input
with the target). Seeded ⇒ reproducible. Results are persisted (`FORECAST`),
never presented as a single certain number (spec §20).

### Sensitivity (tornado) — `sensitivity.py` → `POST /simulations/sensitivity`
Varies each lever between low/high bounds one at a time and ranks by the swing in
the target metric — "what matters most?" (spec §22).

### Scenario comparison — `compare.py` → `POST /simulations/compare`
Runs several named strategies against the same baseline and returns them side by
side with deltas, plus the best by net profit (spec §34).

## Reserved for later phases
Headcount/branch-expansion scenario types, forecasting (time-series validation),
optimization, and news→impact auto-generated scenarios (Phase 7).
