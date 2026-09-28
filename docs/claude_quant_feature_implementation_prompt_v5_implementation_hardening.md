# Claude implementation prompt v5: implementation hardening and final ambiguity closure

This prompt is an addendum and supersedes conflicting sections of earlier quant prompts. It closes implementation-level ambiguities that would otherwise produce unstable, unsafe, or non-reproducible behaviour.

You are working in the existing DigitalTwin repository for a tractor-parts business. Inspect the repository first and integrate with its real models, migrations, simulation registry, API conventions, RBAC, provenance, assistant tools, jobs, audit logs, and frontend conventions. Do not create parallel frameworks.

Do not merely document these decisions. Implement them, test them, and update the quant documentation.

## 1. Croston SBA rare-demand calibration

Do not use an uncapped `size_mean_calibrated = f / q_week` as the sole conditional-size estimator. It can create unstable conditional quantities for rare products.

For Croston SBA:

- `f_sba = (1 - alpha / 2) * z_t / max(p_t, 1)`.
- `q_week = clamp(1 / max(p_t, 1), 0, 1)`.
- Primary conditional non-zero size mean: `size_mean = max(z_t, 0)`.
- Do not force exact equality between `q_week * size_mean` and `f_sba`.
- Report the resulting expected weekly demand as `q_week * size_mean` and the SBA point rate as a separate diagnostic.
- If the absolute relative difference between the two exceeds 25%, return warning `CROSTON_CALIBRATION_GAP`.
- Use a conservative conditional-size cap:

`size_cap = max(p95_historical_nonzero_size, 2 * median_historical_nonzero_size, 1)`

when at least 5 non-zero observations exist.

- If fewer than 5 non-zero observations exist, use:

`size_cap = max(3 * median_nonzero_size, 1)`

- `size_mean = min(max(z_t, 0), size_cap)`.
- If no historical non-zero sizes exist, return `NO_CONDITIONAL_SIZE_EVIDENCE` and no simulated demand distribution.
- Use empirical non-zero-size bootstrap where at least 3 sizes exist. Otherwise use a geometric distribution calibrated to `size_mean`, truncated at `ceil(size_cap)`.
- The cap and fallback distribution are assumptions and must be returned.

For TSB, use `q_week = clamp(p_t, 0, 1)` and `size_mean = min(max(z_t, 0), size_cap)`. TSB’s expected weekly demand is `q_week * size_mean`.

## 2. Multi-product simulation aggregation

Every multi-product simulation must return product-level results plus explicitly defined portfolio metrics.

### 2.1 Product-level metrics

For each product:

- `stockout_event`: 1 if at least one stockout day occurs during the horizon, else 0.
- `stockout_days`.
- `demand_units`.
- `fulfilled_units`.
- `lost_units`.
- `backordered_units`.
- `fill_rate = fulfilled_units / max(demand_units, 1)` with an explicit zero-demand rule.
- `cycle_service_level = cycles_without_stockout / max(total_replenishment_cycles, 1)`.

### 2.2 Portfolio metrics

For each iteration:

- `portfolio_any_product_stockout = max(product.stockout_event)`.
- `portfolio_stockout_product_fraction = count(products with stockout_event=1) / product_count`.
- `portfolio_stockout_product_days = sum(stockout_days) / product_count`.
- `portfolio_fill_rate = sum(fulfilled_units) / max(sum(demand_units), 1)`.
- `portfolio_cycle_service_level = sum(cycles_without_stockout) / max(sum(total_cycles), 1)`.
- `portfolio_revenue = sum(product revenue)`.
- `portfolio_gross_margin = sum(product gross margin)`.
- `portfolio_holding_cost = sum(product holding cost)`.
- `portfolio_net_contribution = sum(product net contribution)`.
- `portfolio_inventory_value = sum(product inventory value)`.

The main `probability_of_stockout` for a portfolio means `P(any product stockout during horizon)`. Also return the other two stockout metrics so the user cannot confuse event probability with product-days exposure.

For all portfolio distributions, return p05/p25/p50/p75/p95, mean, min, max, and sample count.

### 2.3 Hard-budget allocation

When budget binds, use a deterministic priority order:

1. Criticality descending.
2. Risk-adjusted marginal expected contribution per base-currency unit descending.
3. Stockout probability descending.
4. Product priority score descending.
5. Product ID ascending as final tie-break.

At every candidate increment, re-evaluate feasibility and remaining budget. No random or round-robin allocation is allowed. Return allocation order and rejected increments.

### 2.4 Shared supplier correlation

v1 assumes **independent supplier fill/cancellation outcomes per PO line**. This is a deliberate simplification and must be returned as `SUPPLIER_FAILURE_INDEPENDENCE_ASSUMPTION`.

Do not imply that a supplier-wide strike or common shock is modelled. Add an optional future-ready interface:

- `supplier_common_shock_probability` default 0.0 and disabled.
- If explicitly enabled in a future extension, sample one supplier-period shock shared by all lines.
- v1 must reject non-zero common-shock input with `COMMON_SHOCK_NOT_SUPPORTED` rather than silently pretending to model it.

## 3. Enquiry-only cold-start routing

Resolve the contradiction as follows:

- Enquiries and backorders do not create fake sales periods.
- A product with zero non-zero sales periods remains `NO_SALES_HISTORY` for ordinary statistical forecasting.
- If structured enquiry or verified backorder evidence exists, invoke a separate `COLD_START_DEMAND_PRIOR` model, not Croston/TSB.
- The cold-start model returns a low-confidence predictive distribution tagged `ESTIMATED`/`FORECAST` with:
  - expected demand = weighted enquiry-equivalent quantity plus verified backorders;
  - horizon scaling based on available evidence duration, capped at the requested horizon;
  - no seasonality;
  - no automatic reorder recommendation unless inventory, cost, price, lead time, and a critical/manual override gate are satisfied.
- Demand-frequency router output remains `NO_EVIDENCE` for sales history, while forecast router output may be `COLD_START_DEMAND_PRIOR`.
- Return both statuses separately so `NO_EVIDENCE` does not mean “the system ignored enquiries.”

## 4. List endpoint status semantics

For list endpoints:

- `OK`: all requested eligible items returned; no item was excluded for insufficient data.
- `PARTIAL`: at least one item returned and at least one requested item excluded or degraded due to insufficient data.
- `INSUFFICIENT_DATA`: zero eligible items returned and at least one requested item was excluded for insufficient data.
- `FAILED`: calculation failed for the whole request; do not return partial numerical data unless explicitly persisted and marked incomplete.

List shape:

```json
{
  "data": {
    "items": [],
    "excluded": [],
    "degraded": []
  },
  "meta": {
    "status": "OK|PARTIAL|INSUFFICIENT_DATA|FAILED",
    "total_requested": 0,
    "total_returned": 0,
    "total_excluded": 0,
    "total_degraded": 0,
    "total_known": true
  },
  "provenance": [],
  "warnings": [],
  "errors": []
}
```

- `excluded` contains items that cannot produce the requested result.
- `degraded` contains items with a result but a fallback/low-confidence warning.
- All-insufficient lists return `items: []`, `excluded: [...]`, and `meta.status="INSUFFICIENT_DATA"`.
- Mixed lists return `meta.status="PARTIAL"` even if the returned item count is large.
- Frontend must implement distinct empty states for `OK` with zero legitimate items, `PARTIAL`, and `INSUFFICIENT_DATA`.

## 5. Idempotency race and retention

For a persisted POST with an idempotency key:

1. Begin a transaction.
2. Insert a unique `(actor_id, method, route, idempotency_key)` record with state `IN_PROGRESS`.
3. If insertion succeeds, the caller owns execution.
4. If a unique conflict occurs and the existing record is `IN_PROGRESS`, return HTTP 409 `IDEMPOTENCY_REQUEST_IN_PROGRESS` with retry guidance; do not execute a second calculation.
5. If the existing record is `SUCCEEDED`, replay the stored status, response body, and resource IDs.
6. If the existing record is `FAILED`, replay the stored failure only when the original request body hash matches; otherwise return 409.
7. A different body hash with the same key always returns 409 `IDEMPOTENCY_KEY_REUSE`.

Retention:

- Retain successful and failed idempotency records for 7 days.
- Retain `IN_PROGRESS` records for 24 hours; a cleanup job marks abandoned records `EXPIRED` after 24 hours.
- A replay after seven days may execute again and must return metadata stating `idempotency_replayed=false`.
- Cleanup is bounded and indexed.

## 6. Reorder forecast-quality gate

A reorder recommendation must be quality-gated.

Default suppression rules:

- Suppress if `validation_status == INSUFFICIENT_DATA`.
- Suppress if WAPE is available and `WAPE > 0.80`.
- Suppress if forecast uncertainty raw ratio `(p95 - p05) / max(p50, 1) > 2.0`.
- Suppress if interval coverage p05–p95 is outside [0.75, 0.99] with at least 5 coverage observations.
- Suppress if required input data is missing: valid product, inventory position, cost, and lead time.
- Suppress if the product is phase-out unless critical/manual override.

If WAPE or coverage is unavailable because evidence is insufficient, return `recommendation_status="REVIEW_REQUIRED"` rather than automatically suppressing or approving.

Critical/manual override:

- A MANAGER or higher may request a recommendation despite quality suppression.
- The result remains `REVIEW_REQUIRED`, carries the override actor and reason, and cannot become an automatic approval.

A low-quality forecast must never silently produce an ordinary `READY` reorder recommendation.

## 7. ABC new-product gate

ABC annualisation requires at least 30 complete covered days by default.

- If covered days <30, return `ABC_EVIDENCE_SHORT`.
- Do not include the product in the ranked ABC population by default.
- Include it in an optional `new_products` section with observed units and unannualised usage value.
- If an authorised request explicitly includes short-history products, annualise but attach a confidence multiplier:

`annualisation_confidence = min(1, covered_days / 30)`

and multiply the ABC contribution only for ranking, not for displayed raw annualised units.
- Never allow a five-day history to appear equivalent to a full-year observation without the confidence field.

## 8. Weekday-proportion evidence

“Weekday observations” means **calendar-day demand exposure observations**, not only non-zero sales days.

A day qualifies when it has a verified inventory snapshot or verified sales/inventory movement record proving the business had observable exposure on that date.

Eligibility:

- At least 8 complete weeks in total.
- At least 3 exposure-qualified observations for every weekday.
- Calculate weekday share from demand units by weekday, with Laplace smoothing of 1 unit per weekday before normalisation.
- If a weekday has insufficient exposure evidence, use uniform 1/7 and return `WEEKDAY_PATTERN_INSUFFICIENT`.
- Do not use only non-zero sale days because that would bias patterns toward active days.

## 9. Negative-binomial parameterisation

Use SciPy’s convention if SciPy is already a project dependency; otherwise implement the equivalent tested sampler.

SciPy convention:

`scipy.stats.nbinom(n=r, p=p)` counts failures before r successes, with:

- mean `r * (1-p) / p`.
- variance `r * (1-p) / p^2`.

Given target mean `mu` and variance `var > mu`:

`r = mu^2 / (var - mu)`

`p = r / (r + mu)`

Use `scipy.stats.nbinom.rvs(n=r, p=p, random_state=rng)`.

If SciPy is unavailable, use NumPy’s gamma-Poisson mixture:

- `scale = (var - mu) / mu`.
- Draw `lambda ~ Gamma(shape=r, scale=scale)`.
- Draw `demand ~ Poisson(lambda)`.

Unit tests must verify empirical mean and variance within tolerance on a fixed large sample. Never mix parameterisations.

## 10. Quantile-to-mean approximation

Do not silently treat the five quantiles as a full distribution.

If only p05, p25, p50, p75, and p95 are available:

- Use a piecewise-linear quantile function over cumulative probabilities [0.05, 0.25, 0.50, 0.75, 0.95].
- Extend below p05 as constant p05 and above p95 as constant p95 for the approximation.
- The resulting mean is a central 90%-mass approximation with tail truncation/constant-tail assumption.
- Return `MEAN_APPROXIMATED_FROM_QUANTILES` and `tail_assumption="constant_at_p05_p95"`.
- Prefer the predictive-distribution sample mean whenever samples exist.

## 11. GET forecast versus POST forecast run

### GET `/quant/products/{id}/forecast`

- Read-only.
- First checks the cache by request parameters, input hash, config version, and model version.
- If a persisted compatible forecast run exists, return it.
- If none exists, compute synchronously only within safe limits and do not persist unless `persist=true` is explicitly authorised; otherwise return a non-persisted result with `persisted=false`.
- GET never requires an idempotency key.

### POST `/quant/forecasts/run`

- Explicit computation/run request.
- Persists the forecast run and values.
- Requires idempotency key.
- Uses the same underlying forecast service and cache key.
- If an identical persisted run exists, replay it under idempotency semantics.

Cache entries are shared between GET and POST but are invalidated by input-data, config, model, or manual refresh changes. GET must never return a result with a different input hash than the current requested scope unless the response clearly identifies it as historical/persisted and the caller requested historical output.

## 12. Assistant authorization and rate limits

Assistant tools execute as the authenticated calling user, never as an unrestricted service account.

- Enforce RBAC inside every tool execution, not only in the frontend.
- Tool calls count against the calling user’s assistant and quant rate limits.
- Preserve actor ID, role, tool name, parameters hash, route, and result request ID in the audit log.
- Service credentials may be used only for internal infrastructure access and must not bypass business-authorisation checks.
- Tool errors are returned as structured errors; do not leak database or secret details.

## 13. Job partial persistence

A cancelled or failed job may persist execution metadata but cannot publish partial recommendations or partial approval candidates.

`GET /quant/jobs/{id}/result`:

- `SUCCEEDED`: returns complete result.
- `RUNNING`/`QUEUED`: HTTP 409 `JOB_NOT_READY`, with status metadata.
- `CANCELLED`: HTTP 200 with `data=null`, `meta.status="CANCELLED"`, `warnings=[{"code":"JOB_CANCELLED"}]`.
- `FAILED`: HTTP 200 with `data=null`, `meta.status="FAILED"`, structured error summary safe for users.
- No partial numerical recommendations are returned from incomplete jobs.

## 14. Approval audit contract

Use the existing audit-log schema. If fields exist, populate:

- actor/user ID.
- action: `QUANT_RECOMMENDATION_APPROVAL`.
- resource type and recommendation ID.
- decision: `APPROVE` or `REJECT`.
- reason code.
- free-text note, subject to existing limits.
- request ID.
- timestamp.
- prior recommendation status.
- resulting recommendation status.
- input-data hash.
- model/config/schema versions.
- IP address and user agent only if the existing audit system already captures them and privacy policy permits.

Do not create a second incompatible audit schema. Approval does not directly create a purchase order unless the existing purchase workflow explicitly requires that action and RBAC/confirmation are satisfied.

## 15. Priority-score collinearity

Add documentation and response metadata acknowledging that demand value, gross-margin opportunity, and capital requirement may be correlated because they share forecast, cost, and price inputs.

Return:

- `component_correlation_warning=true` when pairwise historical correlations exceed 0.80 in the eligible population.
- A component-correlation matrix where enough products exist.
- No automatic weight correction in v1.
- State that weights are policy preferences, not independent causal contributions.

## 16. Optimiser quality and optimality gap

The default greedy/local-search optimiser remains `HEURISTIC`.

Add an optional linear-relaxation upper bound when constraints can be represented linearly:

- Relax integer order quantities to continuous quantities.
- Preserve budget, capacity, MOQ lower-bound activation approximation, and supplier constraints where representable.
- Solve with an available local solver or a deterministic simplex/greedy upper-bound calculation if no solver dependency exists.
- Return:

`relaxation_upper_bound`, `heuristic_objective`, `optimality_gap = max(0, upper_bound - heuristic_objective) / max(abs(upper_bound), 1)`.

- If no valid bound is available, return null and `OPTIMALITY_GAP_UNAVAILABLE`.
- Never call the heuristic optimal.
- Report whether the bound is exact, relaxed, or unavailable.

## 17. Full acceptance matrix requirement

Do not provide only illustrative rows. Create and maintain an actual machine-readable acceptance matrix, for example:

`docs/quant-acceptance-matrix.yaml`

Each entry must include:

```yaml
id: Q-001
phase: 1
fixture: abc_short_history
command: pytest -q apps/api/tests/quant/test_abc.py::test_short_history_gate
inputs:
  covered_days: 5
expected:
  status: ABC_EVIDENCE_SHORT
  included_in_ranked_population: false
tolerance: exact
warnings:
  - ABC_EVIDENCE_SHORT
provenance: MODEL_OUTPUT
```

Include at least 40 enumerated entries covering:

- ABC window, scope, short history, demand basis.
- ADI/CV² boundaries.
- Priority weights, missingness, ties, collinearity.
- Model eligibility, Croston rare items, TSB, cold start.
- Predictive distribution and weekly/daily bridge.
- Overdispersion and negative-binomial moments.
- Quantile mean tail assumption.
- Backtest horizons and interval coverage.
- Lead time, reorder, EOQ, MOQ, periodic review.
- Multi-product aggregation and deterministic budget allocation.
- Supplier independence assumption and capacity.
- Substitutes and BOMs.
- Quality gates.
- List statuses.
- Idempotency race/TTL.
- GET/POST forecast semantics.
- Assistant authorisation/rate limits.
- Jobs/cancellation.
- Alert lifecycle.
- Audit approval.
- Cache invalidation.
- Feature flag.
- PII and retention.
- Migration rollback.
- Performance and API determinism.

CI must run every matrix command. The final report must include pass/fail status for each ID.

## 18. Specific chaos-test parameterisation

Implement explicit failure injection or fixtures for:

1. DB connection drop before forecast query.
2. DB connection drop after simulation computation but before result commit.
3. Unique-constraint violation during idempotency insert.
4. Deadlock/serialization failure during result persistence, with bounded retry and eventual structured failure.
5. Cache backend timeout; computation proceeds without cache.
6. Worker cancellation between simulation product batches.
7. Scheduler/evaluation failure before alert persistence.
8. Partial supplier data with malformed lead time/cost.
9. Missing FX rate at foreign-currency landed-cost conversion.
10. Feature flag disabled.

Each test must assert transaction state, published-result state, audit state, and user-visible error/status.

## 19. Final implementation process

Implement in phases:

### Phase 1

Classification, demand observations, forecast models, predictive distributions, cold-start prior, weekly/daily bridge, backtesting, lead-time analytics, reorder policies, EOQ, quality gates, APIs, basic frontend, fixtures, and tests.

### Phase 2

Inventory-policy Monte Carlo, multi-product aggregation, deterministic budget allocation, CRN, supplier constraints, supplier scoring, substitutes, BOMs, jobs, caching, and performance benchmarks.

### Phase 3

Alerts, assistant tools, strict schemas, authorisation/rate limits, approval/audit integration, feature flag, accessibility, CI, chaos tests, retention, migration hardening, and UI polish.

At the end of each phase:

- Run existing tests.
- Run quant unit/integration/API/golden tests.
- Run lint/type-check/build.
- Run the acceptance matrix for that phase.
- Record measured performance.
- Fix failures before proceeding.

## 20. Final instruction

Begin by inspecting the repository. Implement Phase 1 fully before Phase 2, and Phase 2 before Phase 3. Do not leave formula-level decisions unresolved. Do not use arbitrary defaults outside this prompt. Do not fabricate evidence. Do not return only a plan. At completion, report exact changed files, migrations, endpoints, seams used, versions, acceptance-matrix results, benchmark results, deviations, and remaining limitations.