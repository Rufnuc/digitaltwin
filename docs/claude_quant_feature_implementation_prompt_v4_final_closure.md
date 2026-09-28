# Claude implementation prompt v4: final quant specification and phased delivery

You are working inside the existing DigitalTwin repository, an AI business digital twin and decision-support platform for a tractor-parts business. Fully implement the quantitative inventory and decision-support module described here. This version closes the remaining specification gaps and supersedes earlier quant prompts where they conflict.

Do not merely write documentation, interfaces, schemas, comments, or TODOs. Implement executable calculations, persistence, API endpoints, tests, assistant tools, frontend flows, migrations, and documentation. Work in the phases defined at the end of this prompt. Do not attempt a risky single-shot rewrite.

The actual repository source is authoritative for existing conventions. First inspect it and adapt to its real interfaces while preserving the behavioural contracts below.

## 1. Repository inspection and seam rules

Inspect before editing:

- Python, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, and test versions.
- Existing model modules, migrations, enums, provenance mixins, audit logs, response envelopes, exception handlers, auth/RBAC, jobs/scheduler, caching, rate limiting, and configuration.
- Existing simulation registry/protocol, runner, Monte Carlo implementation, seed handling, and persistence.
- Existing analytics and P&L identity.
- Existing assistant provider loop, tool registry, provider schemas, and frontend API client.
- Existing Next.js routes, layout, state management, table/chart components, CSS, accessibility, and test commands.

### Compatible-seam definition

A quant feature is integrated through a compatible seam only if:

1. It implements the existing interface/protocol rather than bypassing it.
2. It uses the existing database session/transaction pattern.
3. It uses the existing `DataOrigin`, `VerificationStatus`, and provenance mixin, or adds values through the existing enum migration mechanism.
4. It uses existing auth/RBAC dependencies and error handlers.
5. It uses the existing API envelope and pagination conventions.
6. It uses the existing simulation registry/runner for simulation engines.
7. It uses the existing assistant tool registration and audit path.
8. It uses the existing job/scheduler abstraction if present.
9. It preserves all existing endpoints and tests.
10. Any deviation is documented with a migration/compatibility note and test.

Do not invent a parallel auth, job, provenance, simulation, or response framework.

## 2. Scope boundary for v1

### 2.1 Single-period optimisation

Version 1 budget optimisation is **single-order-cycle, single-horizon** optimisation. It chooses quantities for one decision date over the requested forecast/protection horizon.

- It does not optimise a multi-period replenishment plan.
- It does not optimise dynamic reorder decisions over many future review periods.
- The inventory-policy Monte Carlo can simulate repeated policy behaviour, but the optimiser itself returns a single-cycle order plan.
- Return `optimisation_scope="single_cycle"`.
- Dynamic multi-period optimisation is a documented Phase 3 extension.

### 2.2 No CVaR optimisation in v1

The primary objective is expected contribution or service-level subject to budget. CVaR and stochastic-programming objectives are not implemented in v1.

- Do not call the result risk-optimal.
- Return `risk_objective="expected_contribution"`.
- Implement an optional post-optimisation risk report: p05 contribution, probability of stockout, and probability of budget breach.
- CVaR optimisation is Phase 3.

### 2.3 Cross-product correlation

v1 models cross-product dependence only through:

- Verified substitute groups.
- Verified BOM/kit relationships.
- Shared supplier capacity/budget.

Do not infer general demand correlation from arbitrary co-purchase history in v1. Cross-product correlation from time-series residuals is Phase 3.

### 2.4 External calendars

v1 does not automatically use weather, holidays, crop calendars, or promotions unless a verified event table or explicit request input exists.

- No hidden external calendar effects.
- User-supplied events are assumptions.
- Weather/holiday/crop integrations are Phase 3 providers.

## 3. Canonical data contracts

### 3.1 Verification status

Use the repository’s existing verification field and enum. During inspection, identify its actual name. In this specification, refer to it as `verification_status`.

A record is “verified” only when:

- `verification_status == VERIFIED`, or
- the repository has an equivalent terminal trusted status that is explicitly mapped in a compatibility adapter.

Never assume a row is verified merely because it exists.

### 3.2 Structured product-linked enquiries

If an enquiry table exists, use it. If not, create:

`product_enquiries`

- id.
- product_id nullable only when unresolved.
- customer_id nullable.
- enquiry_timestamp timezone-aware.
- quantity_requested nullable.
- enquiry_type.
- status: `OPEN`, `QUOTED`, `WON`, `LOST`, `CANCELLED`.
- source.
- verification_status.
- data_origin.
- source_reference.

Only rows with a resolved product ID, valid timestamp, non-negative requested quantity where present, and trusted/verified status may be used as structured enquiry evidence. Default enquiry-equivalent quantity:

- If `quantity_requested` exists: use that quantity multiplied by 0.25.
- Otherwise: use 0.25 units per enquiry.
- `enquiry_weight=0.25` is an ASSUMPTION and is returned.

### 3.3 Verified substitutes

If an existing compatibility/substitution table exists, use it. Otherwise create:

`product_substitutions`

- primary_product_id.
- substitute_product_id.
- relationship_type.
- compatibility_status.
- effective_from.
- effective_to nullable.
- substitution_probability nullable.
- source_reference.
- verification_status.
- data_origin.

Only active rows with trusted verification and compatible dates may be used. Default substitution probability is 0.0 if no verified probability exists. Historical probability requires at least 10 eligible observations:

`substitution_probability = fulfilled_substitute_units / max(unmet_primary_units + fulfilled_substitute_units, 1)`

Clip to [0, 1] and return the numerator, denominator, sample size, and method.

### 3.4 Verified BOMs

If an existing BOM table exists, use it. Otherwise create:

`product_boms`

- parent_product_id.
- component_product_id.
- component_quantity.
- effective_from.
- effective_to nullable.
- verification_status.
- data_origin.
- source_reference.

Only `VERIFIED` BOM lines with positive component quantities are used. If no BOM exists, kit/component logic returns `BOM_UNAVAILABLE` and does not silently explode kits.

## 4. Forecast predictive distribution: canonical object

Every forecast returns a `PredictiveDistribution` object, not merely a point number:

```json
{
  "frequency": "WEEKLY",
  "horizon_periods": 12,
  "point_statistic": "MEAN",
  "point_values": [4.1, 4.0, 4.3],
  "quantiles": {
    "p05": [0.0, 0.0, 0.0],
    "p25": [1.0, 1.0, 1.0],
    "p50": [3.0, 3.0, 3.0],
    "p75": [6.0, 6.0, 7.0],
    "p95": [12.0, 13.0, 14.0]
  },
  "samples": null,
  "distribution_family": "RESIDUAL_BOOTSTRAP|EMPIRICAL|POISSON|NEGATIVE_BINOMIAL|ZERO_INFLATED|NONE",
  "parameters": {},
  "sample_count": 2000,
  "seed": 42,
  "method": "string",
  "warnings": []
}
```

- `point_statistic` is explicitly one of `MEAN`, `MEDIAN`, or `MODE`.
- Routed forecasts use `MEAN` when a predictive distribution is available.
- For Croston SBA/TSB point estimates, the point estimate is the mean expected period demand from the model: SBA’s forecast rate or TSB’s `p_t * demand_size_t`. It is not called a sample mean.
- The simulation point lambda uses the predictive-distribution expected value if available; otherwise it uses the routed point estimate. If only quantiles exist, approximate the mean using the trapezoidal integral over p05, p25, p50, p75, p95 and mark `MEAN_APPROXIMATED_FROM_QUANTILES`.
- The forecast API must return `point_statistic`, `point_values`, `quantiles`, family, parameters, method, sample count, and warnings.
- Store samples only when explicitly requested and bounded; otherwise store deterministic distribution metadata and quantiles.

### 4.1 Point-to-distribution rules

1. If model has residual bootstrap samples, use those samples.
2. If model has an empirical conditional distribution, use empirical samples.
3. For smooth demand with sufficient dispersion diagnostics, use a negative-binomial predictive distribution where overdispersion exists.
4. For smooth demand with variance approximately equal to mean, use Poisson.
5. For intermittent demand, use the Croston/TSB occurrence-size construction below.
6. For point-only forecasts without residual evidence, return `NONE` distribution family and use the point estimate only with low-evidence warning.

## 5. Forecast-to-daily simulation bridge

The simulation is daily; the default forecast frequency is weekly. This section is authoritative.

### 5.1 Smooth demand

For a weekly predictive distribution with expected value `E_week`:

- Daily mean baseline: `lambda_week = E_week / 7`.
- If at least 8 complete weeks of daily observations exist and each weekday has >=3 observations, use empirical weekday proportions normalised to sum to 1.
- Otherwise use uniform proportions 1/7.
- `lambda_day[d] = E_week * weekday_proportion[d]`.
- No weekend special rule is assumed beyond observed proportions.
- Holidays are ignored unless explicit verified events are supplied.

Variance:

- Calculate historical conditional weekly mean `mu` and variance `var` from eligible non-censored weekly observations.
- If `var <= 1.25 * mu` and at least 10 observations exist, use Poisson.
- If `var > 1.25 * mu` and at least 10 observations exist, use negative binomial with mean `mu` and dispersion:

`r = mu^2 / max(var - mu, epsilon)`

`p = r / (r + mu)`

- If fewer than 10 observations, use the forecast predictive distribution family if available; otherwise use Poisson with a low-evidence warning.
- Daily negative-binomial draws use the same weekday allocation in the mean and scale the variance consistently. Document the chosen parameterisation.
- Do not force every simulated week to equal the weekly forecast. Preserve expected aggregation, not path-wise equality.

### 5.2 Croston SBA

Croston SBA gives a forecast rate `f = (1 - alpha/2) * z_t / p_t`, where `p_t` is the estimated inter-demand interval.

For simulation:

- Weekly expected demand = `f`.
- Weekly occurrence probability is not `1/p_t` directly unless `p_t >= 1`; use:

`q_week = clamp(1 / max(p_t, 1), 0, 1)`.

- Conditional non-zero demand size mean:

`size_mean = max(z_t, 0)`.

- To preserve the expected weekly demand implied by SBA, set:

`size_mean_calibrated = f / max(q_week, epsilon)`.

- Estimate non-zero size variance from historical non-zero demand; if <3 observations, use a geometric-size fallback with variance equal to `size_mean_calibrated^2` and warning.
- Draw weekly occurrence as Bernoulli(`q_week`). If occurrence is 1, draw size from empirical non-zero sizes or a non-negative bootstrap/gamma approximation calibrated to the conditional mean and variance.
- Disaggregate an occurring weekly quantity across days using observed weekday proportions if available, otherwise uniformly across 1–7 days by a random allocation that sums to the weekly drawn quantity.
- Do not use a Poisson process for Croston SBA by default.

### 5.3 TSB

TSB provides occurrence probability `p_t` and non-zero size estimate `z_t`.

- Weekly occurrence probability = `q_week = clamp(p_t, 0, 1)` when the training frequency is weekly.
- Weekly conditional size mean = `max(z_t, 0)`.
- Expected weekly demand = `q_week * size_mean`.
- If TSB was fitted on another frequency, convert occurrence probability using the model’s period conversion and return the conversion method.
- Draw Bernoulli occurrence then conditional non-zero size from empirical non-zero sizes or a non-negative bootstrap/gamma approximation.
- Disaggregate an occurring quantity across days as above.
- Do not use both SBA `1/p_t` and TSB `p_t`; the selected model determines the construction.

### 5.4 Residual bootstrap

For a routed model with residual bootstrap:

- Bootstrap weekly forecast errors at each horizon where >=5 residuals exist.
- Add sampled residual to the model point forecast, clip final quantity to zero.
- For simulation, draw a weekly total from the resulting non-negative bootstrap sample.
- Use the same daily disaggregation bridge after drawing the weekly total.
- Do not bootstrap intermittent residuals and then feed them into a Poisson process; the weekly bootstrap sample is the total-demand distribution.

### 5.5 Autocorrelation and calendar effects

- v1 does not model arbitrary autocorrelation beyond the model’s residual bootstrap.
- If at least 12 complete periods exist, report lag-1 autocorrelation as a diagnostic.
- Do not use it to alter simulation draws in v1.
- Weekday proportions capture observed weekday/weekend effects.
- Holiday/weather/crop calendars are not automatically used; explicit event inputs are assumptions.

## 6. Priority-score component definitions

Calculate and return every raw and normalised component.

### Demand value

`demand_value = annualised_verified_units * unit_cost`

Use the ABC trailing window and verified observed sales plus verified backorders. If cost is missing, null.

### Gross-margin opportunity

`gross_margin_opportunity = annualised_expected_fulfilled_units * max(0, selling_price - unit_cost)`

Use the primary forecast mean over the next 12 forecast periods annualised to 365 days. If no reliable forecast exists, null.

### Criticality

Map enum to numeric:

- Critical 1.00.
- Important 0.75.
- Standard 0.50.
- Non-critical 0.25.

### Stockout cost

`stockout_cost = expected_lost_units_over_protection_period * max(0, selling_price - unit_cost)`

Use the p50 or expected lost units from the inventory-policy simulation when available; otherwise calculate from demand p50/p95 and current inventory position with a warning. This is lost gross margin, not downtime or reputational cost.

### Lead-time risk

`lead_time_risk = clamp((p95_lead_time - p50_lead_time) / max(p50_lead_time, 1), 0, 1)`.

If empirical lead-time quantiles unavailable, use the triangular fallback and mark estimated.

### Supplier risk

`supplier_risk = 1 - risk_adjusted_supplier_score` for the selected/preferred supplier, after normalisation.

### Capital requirement

`capital_requirement = expected_order_quantity * unit_cost`.

Expected order quantity means the constrained quantity from the selected default reorder policy using the primary forecast mean and current inventory position over the protection period. If no recommendation is available, null.

### Forecast uncertainty

`forecast_uncertainty = clamp((p95_total - p05_total) / max(p50_total, 1), 0, 1)`.

Cap at 1.0 for score normalisation; retain raw ratio separately.

### Obsolescence risk

Map:

- High 1.00.
- Medium 0.50.
- Low 0.00.
- Unknown null.

The final priority score uses the missingness coverage penalty defined in v3. Return coverage and exclusion status.

## 7. Reorder policies and EOQ

Default policy: **periodic-review order-up-to** with 7-day review period.

Support explicit policy types:

- `FIXED_ORDER_QUANTITY`.
- `MIN_MAX`.
- `ORDER_UP_TO`.
- `EOQ`.

### Fixed order quantity

Use configured fixed quantity; if absent, return `POLICY_PARAMETER_MISSING`.

### Min-max

- `min_level = reorder_point`.
- `max_level = order_up_to_level`.
- Quantity = max(0, max_level - inventory_position) when inventory position <= min_level.

### Order-up-to

Use the periodic protection-period formula from v3/v4.

### EOQ

`EOQ = sqrt((2 * annual_demand_units * ordering_cost_per_order) / annual_holding_cost_per_unit)`.

Defaults:

- Ordering cost: no default; must be configured or supplied as an explicit assumption.
- Annual holding cost per unit: `unit_cost * annual_holding_rate`.
- Annual holding rate: 0.25.
- If ordering cost or unit cost is missing/invalid, return `EOQ_UNAVAILABLE` and use order-up-to only if the request permits fallback.
- EOQ is rounded up to MOQ/order multiple after calculation.
- Return raw EOQ, constrained EOQ, input values, and fallback status.

## 8. Service-level metrics

“Probability of achieving service target” means **cycle service level** by default:

`CSL = probability(no stockout occurs during a replenishment protection cycle)`.

Also return:

- Fill rate = fulfilled demand / total demand including backorders or lost sales.
- Line fill rate where order lines are available.
- Probability of meeting target CSL.
- Probability of meeting target fill rate.

Do not call fill rate “service level” without naming the metric.

## 9. Landed cost and supplier capacity

Landed cost:

`landed_cost = supplier_unit_cost_base_currency + freight_per_unit + duty_per_unit + handling_per_unit + fx_risk_surcharge_per_unit + expected_quality_cost_per_unit`

- Freight, duty, handling, and quality cost are used only when verified/configured.
- Missing components default to zero only if the field is explicitly configured as zero; otherwise remain null with warning.
- FX surcharge is the risk adjustment defined in v4.
- Return each component and total.

Supplier capacity input contract:

```json
{
  "supplier_id": "uuid",
  "capacity_quantity": 100,
  "capacity_unit": "UNITS|BASE_CURRENCY",
  "period_start": "2026-09-14",
  "period_end": "2026-10-13",
  "scope": "SUPPLIER_TOTAL|PRODUCT|CATEGORY"
}
```

- Capacity is per supplier and period.
- For `UNITS`, decrement by order quantity.
- For `BASE_CURRENCY`, decrement by landed cost.
- If no period is supplied, use the optimisation horizon.
- Return capacity used, remaining, and binding status.

## 10. Substitution and optimisation

v1 optimisation is single-cycle and uses only verified substitute groups.

Algorithm:

1. Generate candidate increments for each eligible product/supplier.
2. Apply product MOQ/order multiple.
3. Apply single-supplier and supplier-capacity constraints.
4. For each candidate, use common random numbers and estimate expected contribution and service impact.
5. Greedily select the feasible increment with highest positive marginal expected contribution per base-currency unit.
6. Apply up to 500 local swap moves.
7. Stop after no improvement >=0.01 or 10,000 moves.
8. For substitute groups, jointly evaluate candidates. A candidate may satisfy primary demand with a substitute only by the verified substitution probability. Do not allocate one unit to two products.
9. Return primary and substitute expected fulfilment, stockout risk, spend, and assumptions.

## 11. API response contracts

Use existing envelope. If none exists, use:

```json
{
  "data": {},
  "meta": {
    "status": "OK|INSUFFICIENT_DATA|PARTIAL|FAILED",
    "request_id": "uuid",
    "generated_at": "ISO-8601 UTC",
    "model_name": "string|null",
    "model_version": "string|null",
    "config_version": "string|null",
    "input_data_version": "sha256:string|null",
    "page": 1,
    "page_size": 25,
    "total": 0,
    "total_known": true
  },
  "provenance": [],
  "warnings": [],
  "errors": []
}
```

For list responses:

```json
{
  "data": {
    "items": [],
    "excluded": [
      {
        "product_id": "uuid",
        "reason_code": "MISSING_LEAD_TIME",
        "missing_fields": ["lead_time_days"]
      }
    ]
  }
}
```

For a single product with insufficient data:

- HTTP 200.
- `data: null`.
- `meta.status: "INSUFFICIENT_DATA"`.
- `warnings` contains stable codes and missing fields.
- `errors: []`.

For invalid input: HTTP 422 and structured `VALIDATION_ERROR`.

### Example forecast response

```json
{
  "data": {
    "product_id": "part-001",
    "frequency": "WEEKLY",
    "selection_horizon": 1,
    "output_horizon": 12,
    "model_name": "croston_sba",
    "model_version": "croston-sba-1.0.0",
    "point_statistic": "MEAN",
    "point_values": [4.1, 4.1, 4.1],
    "quantiles": {
      "p05": [0, 0, 0],
      "p25": [1, 1, 1],
      "p50": [3, 3, 3],
      "p75": [6, 6, 6],
      "p95": [12, 12, 12]
    },
    "distribution_family": "EMPIRICAL",
    "distribution_parameters": {"occurrence_probability": 0.4},
    "sample_count": 2000,
    "seed": 42,
    "diagnostics": {
      "mae": 1.2,
      "wape": 0.31,
      "bias": -0.2,
      "mase": 0.88,
      "interval_coverage_p25_p75": 0.52,
      "interval_coverage_p05_p95": 0.91,
      "interval_nominal_p25_p75": 0.50,
      "interval_nominal_p05_p95": 0.90,
      "coverage_sample_count": 12
    },
    "warnings": []
  },
  "meta": {
    "status": "OK",
    "model_name": "croston_sba",
    "model_version": "croston-sba-1.0.0",
    "config_version": "1.0.0",
    "input_data_version": "sha256:..."
  },
  "provenance": [],
  "warnings": [],
  "errors": []
}
```

### Assistant tool JSON schemas

Implement strict schemas equivalent to these, adapted to existing tool conventions.

`get_demand_forecast`:

```json
{
  "type": "object",
  "required": ["product_id"],
  "properties": {
    "product_id": {"type": "string"},
    "branch_id": {"type": ["string", "null"]},
    "frequency": {"type": "string", "enum": ["DAILY", "WEEKLY", "MONTHLY"]},
    "horizon_periods": {"type": "integer", "minimum": 1, "maximum": 730},
    "include_samples": {"type": "boolean"},
    "seed": {"type": "integer", "minimum": 0, "maximum": 2147483647}
  },
  "additionalProperties": false
}
```

`get_reorder_recommendations`:

```json
{
  "type": "object",
  "properties": {
    "product_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 500},
    "branch_id": {"type": ["string", "null"]},
    "policy": {"type": "string", "enum": ["FIXED_ORDER_QUANTITY", "MIN_MAX", "ORDER_UP_TO", "EOQ"]},
    "service_level": {"type": ["number", "null"], "minimum": 0.5, "maximum": 0.999},
    "review_period_days": {"type": "integer", "minimum": 1, "maximum": 365},
    "include_demo": {"type": "boolean"},
    "page": {"type": "integer", "minimum": 1},
    "page_size": {"type": "integer", "minimum": 1, "maximum": 200}
  },
  "additionalProperties": false
}
```

`get_inventory_risk`:

```json
{
  "type": "object",
  "properties": {
    "product_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 500},
    "horizon_days": {"type": "integer", "minimum": 1, "maximum": 730},
    "iterations": {"type": "integer", "minimum": 100, "maximum": 50000},
    "seed": {"type": "integer", "minimum": 0, "maximum": 2147483647}
  },
  "additionalProperties": false
}
```

`simulate_inventory_policy`:

```json
{
  "type": "object",
  "required": ["product_ids"],
  "properties": {
    "product_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 500},
    "horizon_days": {"type": "integer", "minimum": 1, "maximum": 730},
    "iterations": {"type": "integer", "minimum": 100, "maximum": 50000},
    "seed": {"type": "integer", "minimum": 0, "maximum": 2147483647},
    "policy": {"type": "string", "enum": ["FIXED_ORDER_QUANTITY", "MIN_MAX", "ORDER_UP_TO", "EOQ"]},
    "review_period_days": {"type": "integer", "minimum": 1, "maximum": 365},
    "budget": {"type": ["number", "null"], "minimum": 0},
    "hard_budget": {"type": "boolean"},
    "burn_in_days": {"type": "integer", "minimum": 0, "maximum": 730}
  },
  "additionalProperties": false
}
```

`optimize_inventory_budget`:

```json
{
  "type": "object",
  "required": ["budget", "product_ids"],
  "properties": {
    "budget": {"type": "number", "minimum": 0},
    "product_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 500},
    "horizon_days": {"type": "integer", "minimum": 1, "maximum": 730},
    "iterations_per_candidate": {"type": "integer", "minimum": 100, "maximum": 10000},
    "seed": {"type": "integer", "minimum": 0, "maximum": 2147483647},
    "single_supplier_only": {"type": "boolean"},
    "allow_supplier_split": {"type": "boolean"},
    "allow_substitute_reallocation": {"type": "boolean"},
    "supplier_capacity": {"type": "array"}
  },
  "additionalProperties": false
}
```

`get_supplier_risk`:

```json
{
  "type": "object",
  "properties": {
    "product_id": {"type": ["string", "null"]},
    "supplier_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 200},
    "branch_id": {"type": ["string", "null"]}
  },
  "additionalProperties": false
}
```

`get_dead_stock`:

```json
{
  "type": "object",
  "properties": {
    "as_of_date": {"type": ["string", "null"], "format": "date"},
    "minimum_value": {"type": "number", "minimum": 0},
    "no_sale_days": {"type": "integer", "minimum": 1, "maximum": 3650},
    "page": {"type": "integer", "minimum": 1},
    "page_size": {"type": "integer", "minimum": 1, "maximum": 200}
  },
  "additionalProperties": false
}
```

`get_forecast_backtest`:

```json
{
  "type": "object",
  "required": ["product_id"],
  "properties": {
    "product_id": {"type": "string"},
    "frequency": {"type": "string", "enum": ["DAILY", "WEEKLY", "MONTHLY"]},
    "horizons": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 730}, "maxItems": 3},
    "max_folds": {"type": "integer", "minimum": 2, "maximum": 20}
  },
  "additionalProperties": false
}
```

All tool schemas must be validated server-side. Numerical claims in assistant prose must cite the returned tool result path. If insufficient data, use the contract in this prompt and do not substitute numbers.

## 12. Forecast and backtest horizon contract

The default served forecast horizon is:

- Daily: 30 periods.
- Weekly: 12 periods.
- Monthly: 12 periods.

Model selection uses horizon 1 by default, but `/forecast` diagnostics must include coverage and metrics for every served horizon that has enough backtest folds. If 12-week output is served but only horizon-1 validation is available, return:

- `validation_status="PARTIAL"`.
- `validated_horizons=[1]`.
- `unvalidated_horizons=[2..12]`.
- Warning `OUTPUT_HORIZON_NOT_FULLY_VALIDATED`.

When enough data exists, run horizon-specific rolling-origin backtests for all requested output horizons. Do not present a long-horizon forecast as fully validated from a one-step test.

## 13. Alert freshness and scheduler behaviour

“Stale evidence” means the newest underlying source record used for the alert is older than the configured freshness window, not merely that an evaluation run is late.

- Default freshness window: 30 days for inventory/sales evidence; 90 days for supplier lead-time metrics.
- If evaluation runs but input evidence is stale, set alert state to EXPIRED with reason `STALE_INPUT_DATA`.
- If the scheduled evaluation fails, do not count it as a false run and do not resolve/suppress alerts based on absence of evidence. Record `EVALUATION_FAILED`.
- Severity increase while suppressed reopens the alert as OPEN at the new severity and records the prior state.

Scheduler:

- Use the existing scheduler if present.
- If absent, create a scheduler interface and a development CLI/cron-compatible command `quant evaluate-alerts`.
- Do not claim production scheduling unless a durable scheduler is configured.
- The scheduled task is intended for a daily 02:00 business-time execution.

## 14. Job result and frontend polling

`GET /quant/jobs/{id}/result` is idempotent and repeatable. It never consumes or deletes a result. It returns the same persisted result for the job ID.

Frontend async behaviour:

- Poll status after 1 second.
- Then poll at 2, 4, 8, 15, and 30 seconds, capped at 30 seconds.
- Stop after 10 minutes and show a retry/support state.
- Cancel requests set UI state to `CANCELLING`; stop polling only after server state is CANCELLED, SUCCEEDED, or FAILED.
- Use AbortController for component unmount and manual cancellation.
- Preserve job ID so page refresh can resume polling.
- Display progress only when server provides measured progress; otherwise display indeterminate progress.

## 15. Phase plan and deliverables

Do not implement the entire module in one uncontrolled pass.

### Phase 1: classification, demand observations, forecasts, reorder

Implement:

- New derived tables and migrations.
- Idempotent backfill from invoices, purchases, inventory, receipts, returns, backorders, and enquiries.
- ABC and demand-frequency classification.
- Naive, moving average, SES, Croston, SBA, TSB, seasonal-naive eligibility.
- PredictiveDistribution object.
- Weekly-to-daily bridge.
- Lead-time statistics.
- Safety stock, reorder point, periodic-review order-up-to, MOQ/order multiples, and EOQ.
- Forecast/backtest API and reorder API.
- Unit/integration/API/golden tests.
- Basic frontend recommendations and forecast detail.

Definition of done:

- Seeded tractor-parts data returns executable forecasts and reorder quantities.
- Missing inputs return the defined insufficient-data response.
- Golden calculations match expected values within Decimal-normalised tolerance.
- Existing tests/build/lint pass.

### Phase 2: simulation, risk, supplier selection, optimisation

Implement:

- Inventory-policy Monte Carlo with smooth, overdispersed, Croston, and TSB demand processes.
- Backorder/lost-sales state machine.
- Supplier fill/cancel and lead-time sampling.
- Common random numbers.
- Stockout/service metrics.
- Supplier scoring and landed-cost decomposition.
- Single-cycle budget optimisation with supplier capacities, MOQ, substitutes, and BOMs where verified.
- Jobs, cancellation, limits, caching, observability.
- Simulation/optimisation API and frontend.

Definition of done:

- Same request/seed/config/input hash produces semantically identical results.
- Candidate policies use identical random draws.
- Budget, supplier, MOQ, and branch constraints are enforced.
- Simulation metrics reconcile on deterministic fixtures.
- Performance is measured on the reference environment below.

### Phase 3: alerts, assistant, hardening, and UI polish

Implement:

- Alert scheduler interface and lifecycle.
- Assistant tools with strict schemas.
- Provenance/source claims.
- Feature flag rollout.
- Accessibility, demo banner, loading/error/empty states.
- Rate limits, PII checks, retention, migration rollback tests, CI, chaos tests, and performance tests.
- Complete documentation.

Definition of done:

- Assistant calls tools for numerical answers and refuses unsupported calculations.
- Alerts deduplicate, acknowledge, approve, suppress, reopen, resolve, and expire correctly.
- Feature flag disables quant routes/tools without breaking existing application.
- CI runs all required checks.

## 16. Reference environment and performance

Record actual environment in the final report. CI reference target:

- Ubuntu 22.04 runner.
- 4 vCPU.
- 8 GB RAM.
- Python 3.10.x.
- PostgreSQL 15.x.
- Node 20.x.
- npm lockfile versions.

Development fixture targets:

- 10,000-product classification <=5 seconds.
- 1,000 products x 52 weekly observations forecast run <=30 seconds when synchronous.
- 5,000-iteration 90-day one-product simulation <=5 seconds.
- API read p95 <=500 ms on seeded data excluding queued jobs.

Use a benchmark script with fixed seed and fixture generator. If the target is missed, report actual median/p95 and the limiting stage; do not fake compliance.

## 17. Golden files, CI, and acceptance matrix

Golden format:

- JSON files under `apps/api/tests/golden/quant/`.
- Stable object keys sorted.
- Decimal values serialised as strings with fixed precision.
- Floats rounded to 8 decimal places only for comparison.
- Arrays ordered by documented product/date/order key.
- Remove request IDs, timestamps, job IDs, database IDs that are generated randomly, and environment-specific paths.
- Keep model/config/schema versions in the golden file.
- Golden test failure prints a unified diff and requires deliberate fixture update.

Required golden files:

- `abc_classification.json`.
- `croston_sba_forecast.json`.
- `tsb_forecast.json`.
- `reorder_periodic_review.json`.
- `eoq_fallback.json`.
- `weekly_daily_bridge.json`.
- `inventory_simulation_summary.json`.
- `budget_optimisation_constraints.json`.
- `supplier_score.json`.
- `forecast_api_envelope.json`.

Acceptance matrix must contain, for each test:

- Test ID.
- Fixture name.
- Input values.
- Expected output fields.
- Numeric tolerance.
- Expected warnings/status.
- Required provenance.
- Test command.
- Pass/fail result.

Example:

| ID | Fixture | Expected | Tolerance | Warnings |
|---|---|---|---|---|
| Q-012 | weekly_daily_bridge | sum expected daily means = weekly mean; uniform shares 1/7 | 1e-8 | none |
| Q-014 | receipt_timing | order placed day 0 with lead 3 receives day 4 start | exact | none |
| Q-018 | hard_budget | spend <= budget; blocked increment returned | exact Decimal | BUDGET_CONSTRAINT |
| Q-024 | idempotency | second request returns same persisted result ID | exact | none |
| Q-026 | API determinism | normalised result JSON equal | exact | none |

## 18. Chaos and failure acceptance

Test:

- Database failure before computation.
- Database failure during result persistence; transaction rolls back and no recommendation becomes approved.
- Worker cancellation during simulation; result is CANCELLED with no publishable partial recommendation.
- Cache failure; calculation still executes.
- Scheduler failure; active alerts are not falsely resolved.
- Missing FX rate, supplier capacity, BOM, enquiry, inventory, or lead time.
- Malformed data and invalid parameters.
- Feature disabled.

## 19. Final implementation instruction

Begin by inspecting the repository. Implement Phase 1 first and run its tests before proceeding to Phase 2. Continue through Phase 3 only after prior phases pass. Do not leave equations as prose. Do not invent data. Do not claim optimality, accuracy, production scheduling, or performance without executable evidence. At the end, report changed files, migrations, endpoints, seams used, model/config/schema versions, formulas implemented, acceptance matrix results, golden files, test counts, benchmark measurements, deviations, and remaining limitations.