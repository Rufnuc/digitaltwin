# Claude quant implementation prompt v6: final open-item closure

This document is the final addendum to the DigitalTwin quantitative inventory implementation specification. It resolves the remaining open items from v5. It supersedes conflicting earlier wording. For all other requirements, use the precedence table in Section 9 and the referenced canonical rules below.

Do not leave any item in this document as prose-only guidance. Implement the rules, persist the relevant method/assumptions, expose them through APIs, test them, and document them.

## 1. Cold-start demand prior

`COLD_START_DEMAND_PRIOR` applies when a product has no eligible non-zero sales periods but has verified backorders, structured product-linked enquiries, or a verified substitute-group prior.

It is not an ordinary sales-history forecast. It is a low-confidence estimated prior.

### 1.1 Evidence quantities

For an evidence window of `W` complete days and a forecast horizon of `H` days, calculate:

- `B = sum(verified_backordered_quantity)`.
- `E = sum(enquiry_equivalent_quantity)`.
- `S = substitute_prior_units` from the verified substitute-group rule below.

Enquiry-equivalent quantity:

- If a verified enquiry has `quantity_requested`, contribute `0.25 * quantity_requested`.
- Otherwise contribute `0.25` units.
- Only verified/resolved product-linked enquiries qualify.
- `E` is an assumption-weighted signal, not observed demand.

Backorders:

- Verified backorders are weighted at 1.0.
- A backorder is not counted again as an enquiry if it originated from an enquiry record; deduplicate by source reference.

### 1.2 Evidence-window rate

Define an evidence-equivalent quantity:

`Q_evidence = B + E`

If a verified substitute prior exists, calculate it separately as `S`; do not add it to `Q_evidence` before blending.

Evidence rate:

`r_evidence = Q_evidence / max(W, 1)`

If `W` is unknown, use the number of complete calendar days from the earliest eligible evidence event to the latest as-of date. If that is less than 7 days, set `W=7` and return `COLD_START_SHORT_WINDOW`.

### 1.3 Horizon scaling

Raw horizon demand:

`D_raw = r_evidence * H`

Evidence-duration confidence:

`c_duration = min(1, W / 90)`

Evidence-type confidence:

- Backorder-only: `c_type = 0.75`.
- Enquiry-only: `c_type = 0.25`.
- Backorders plus enquiries: `c_type = 0.75`.
- Substitute prior only: `c_type = 0.40`.
- No qualifying evidence: no cold-start prior.

Combined evidence confidence:

`c_evidence = c_duration * c_type`

Conservative demand estimate:

`D_conservative = D_raw * c_evidence`

Return both `D_raw` and `D_conservative`; the simulation and reorder policy use `D_conservative` by default.

### 1.4 Substitute-prior calculation

For a verified substitute group, use eligible products with at least 3 complete periods and verified demand:

`group_rate = sum(verified_demand_units across eligible substitutes) / sum(exposure_days across eligible substitutes)`

For the new product, apply a compatibility transfer factor:

- Verified one-to-one replacement relationship: `transfer_factor = 0.50`.
- Verified same-function compatible group without one-to-one evidence: `transfer_factor = 0.25`.
- No verified relationship: no substitute prior.

`S = group_rate * H * transfer_factor`

`c_substitute = 0.50` for one-to-one replacement; `0.25` otherwise.

Do not infer compatibility from product names or LLM output.

### 1.5 Blending evidence and substitute prior

If both evidence and substitute prior exist:

`w_evidence = c_evidence / max(c_evidence + c_substitute, epsilon)`

`w_substitute = c_substitute / max(c_evidence + c_substitute, epsilon)`

`D_blended = w_evidence * D_conservative + w_substitute * S`

If only evidence exists:

`D_blended = D_conservative`

If only substitute prior exists:

`D_blended = S * c_substitute`

The predictive distribution is a capped non-negative empirical/Poisson-gamma mixture around `D_blended`:

- Mean = `D_blended`.
- Coefficient of variation default = 1.0 for backorder evidence, 2.0 for enquiry-only, and 1.5 for substitute-only.
- If `D_blended > 0`, use a negative-binomial distribution with mean `mu=D_blended` and variance `(1 + CV²) * mu²`.
- If `D_blended == 0`, return no numeric prior.
- Cap the result at `max(5 * D_blended, 10)` units over the requested horizon and return `COLD_START_DEMAND_CAP` if applied.

No seasonality or price elasticity is applied. The result carries:

- `model_name = COLD_START_DEMAND_PRIOR`.
- `data_origin = FORECAST` for the distribution.
- Evidence components as `REAL`/`ESTIMATED` according to their sources.
- `ASSUMPTION` for weights, transfer factors, CV, and cap.
- `confidence = c_evidence` or the blended confidence.

A cold-start prior may be displayed in forecast results but cannot produce a `READY` reorder recommendation. It can produce `REVIEW_REQUIRED` only when all required inventory, price, cost, lead-time, and critical/manual-override conditions are met.

## 2. Optimiser upper-bound semantics

The optimiser must not report an invalid optimality gap.

### 2.1 Valid bound

A value may be called `relaxation_upper_bound` only when:

- The relaxed feasible region is provably a superset of the integer feasible region.
- Every MOQ/order-multiple activation is represented using valid binary variables and a true mixed-integer relaxation, or the MOQ constraints are not binding in the relaxed problem.
- Budget and supplier-capacity constraints are preserved correctly.
- The objective is relaxed upward or remains an upper bound.

If these conditions hold:

`optimality_gap = max(0, upper_bound - heuristic_objective) / max(abs(upper_bound), 1)`

Return `bound_status = VALID_RELAXATION_UPPER_BOUND`.

### 2.2 Invalid or approximate bound

If MOQ, order multiples, supplier constraints, or nonlinear simulation objective are approximated such that a superset cannot be proven:

- Store the result as `relaxed_estimate`, not `relaxation_upper_bound`.
- Set `optimality_gap = null`.
- Return `bound_status = RELAXED_ESTIMATE_NOT_CERTIFIED`.
- Return warning `OPTIMALITY_GAP_UNAVAILABLE`.

Never subtract a heuristic objective from an uncertified estimate and call it an optimality gap.

The heuristic result remains `HEURISTIC` in all cases.

## 3. Reorder quality gate horizon

The reorder recommendation horizon is the **protection horizon**:

- Continuous review: `ceil(mean_lead_time_days)`.
- Periodic review: `review_period_days + ceil(mean_lead_time_days)`.

Forecast quality must be evaluated at that horizon.

- If a validated backtest exists exactly at the protection horizon, use its WAPE, bias, interval coverage, and sample count.
- Otherwise use the nearest validated horizon that is not shorter than the protection horizon, if available.
- If only a shorter validated horizon exists, use it only as a provisional proxy and return `QUALITY_GATE_PROXY_HORIZON`.
- If no validated horizon exists, return `REVIEW_REQUIRED`; do not silently use horizon-1 WAPE as if it represented the protection horizon.

Default suppression:

- WAPE at selected quality horizon >0.80: `FORECAST_UNRELIABLE`.
- Uncertainty ratio >2.0: `FORECAST_UNRELIABLE`.
- p05–p95 coverage outside [0.75, 0.99] with >=5 observations: `FORECAST_UNRELIABLE`.
- Missing quality evidence: `REVIEW_REQUIRED`.

Persist `quality_evaluation_horizon`, `quality_horizon_method`, and the selected diagnostics in each recommendation.

## 4. Portfolio stockout naming and metrics

Rename the primary portfolio field:

`probability_any_product_stockout`

Do not expose an ambiguous portfolio field named only `probability_of_stockout`.

Return:

- `probability_any_product_stockout` = P(at least one product has a stockout event).
- `probability_product_stockout_fraction_above_threshold` for configurable thresholds, default 0.10.
- `expected_stockout_product_fraction`.
- `expected_stockout_product_days_per_product`.
- `portfolio_fill_rate`.
- `portfolio_cycle_service_level`.
- Per-product distributions.

Frontend dashboards must promote `expected_stockout_product_fraction` and `portfolio_fill_rate` alongside the any-product event probability so users are not misled by a large portfolio event probability.

## 5. Substitution in simulation

v1 inventory-policy simulation is **substitution-aware only when explicitly enabled** and when verified substitution relationships exist.

Default:

- `substitution_enabled = false`.
- Simulation is substitution-blind by default and returns `SUBSTITUTION_NOT_SIMULATED` when verified substitutes exist but the flag is false.

When enabled:

1. A primary product demand unit cannot be fulfilled from primary stock.
2. With probability equal to the verified substitution probability, search active substitutes in deterministic order:
   - compatibility status priority.
   - highest available quantity.
   - lowest landed cost.
   - product ID ascending.
3. If a substitute fulfils the demand:
   - increment substitute `fulfilled_units`.
   - increment substitute `substitution_fulfilled_units`.
   - increment primary `demand_units`.
   - do not increment primary `lost_units` or `backordered_units`.
   - increment primary `substitution_received_units`.
4. If no substitute fulfils it, apply the primary product’s backorder/lost-sales policy.
5. Revenue and margin are assigned to the product actually supplied, while the primary demand remains visible.

Portfolio metrics:

- `portfolio_demand_units` includes primary demand events once, not twice.
- `portfolio_fulfilled_units` counts units actually supplied.
- `portfolio_lost_units` counts demand unmet after substitution attempts.
- Return substitution rate and substitution assumptions.

Optimisation may use substitution only when the simulation flag and verified relationships are both enabled.

## 6. Approval-to-purchase workflow

Recommendation approval is not a purchase order.

Exact v1 flow:

1. MANAGER approves a reorder recommendation.
2. The system creates a `PURCHASE_ORDER_DRAFT` or `PURCHASE_REQUISITION` in the existing procurement workflow, linked to the recommendation.
3. No supplier-facing purchase order is sent automatically.
4. A separate existing procurement confirmation step must convert the draft/requisition into an official PO.
5. If the existing repository has no draft/requisition model, create a quant-linked draft object only; do not create or send an external PO.
6. Approval is idempotent and cannot approve a recommendation that is stale, already approved, rejected, or superseded.

Return `approval_status`, `draft_id`, and `requires_procurement_confirmation=true`.

## 7. ABC display confidence

For products with fewer than 30 covered days:

- Exclude from ranked ABC by default.
- Display in a separate `new_products` section.
- Return `annualised_units_raw` and `annualisation_confidence_adjusted_units`.
- `annualisation_confidence_adjusted_units = annualised_units_raw * min(1, covered_days / 30)`.
- UI must label raw annualisation as `LOW-EVIDENCE ANNUALISED` and show covered days and confidence beside it.
- Never display the raw annualised figure alone as if it were a reliable annual usage estimate.

## 8. Precedence and governing specification

Use this precedence order:

1. Actual repository source and existing tests for existing conventions.
2. This v6 addendum for the open issues resolved here.
3. v5 for all other implementation-hardening rules.
4. v4 for phase plan, reference environment, scheduler intent, BOM/substitute contracts, audit integration, and frontend/CI requirements not contradicted here.
5. v3/v2/v1 only where not superseded and where v5/v4 do not define the subject.

The following v4 rules remain explicitly governing:

- Verified substitute table contract and verified BOM table contract.
- Single-branch v1 boundary and branch scope requirement.
- Feature flag `QUANT_INVENTORY_ENABLED`.
- Daily 02:00 scheduler intent through an existing scheduler or a CLI/cron-compatible command.
- Existing audit-log integration rather than a parallel audit system.
- Reference CI environment: Ubuntu 22.04, 4 vCPU, 8 GB RAM, Python 3.10.x, PostgreSQL 15.x, Node 20.x.
- Golden-file format, acceptance-matrix requirements, chaos-test requirement, and three-phase delivery plan.

The following v5 rules remain governing:

- Idempotency race, seven-day retention, abandoned-key expiry, and replay semantics.
- List status semantics.
- Forecast GET versus persisted POST behaviour.
- Assistant execution as the authenticated user.
- Job partial-result semantics.
- Approval audit fields.
- Priority-score collinearity warning.
- Certified versus uncertified optimisation bounds.
- Explicit acceptance matrix with at least 40 enumerated entries.

If two governing documents still conflict, implement the later document and record the conflict in the final deviation report.

## 9. Required tests for this addendum

Add at least these acceptance tests:

- `Q-041`: rare Croston SBA item does not produce unbounded conditional size.
- `Q-042`: Croston calibration gap warning is emitted when SBA rate differs from occurrence-size mean by >25%.
- `Q-043`: multi-product any-stockout probability differs from expected stockout product fraction.
- `Q-044`: hard-budget allocation follows deterministic tie-break order.
- `Q-045`: supplier failure independence assumption is returned and common-shock input is rejected.
- `Q-046`: enquiry-only product routes to cold-start prior, not ordinary Croston/TSB.
- `Q-047`: cold-start horizon scaling matches exact formula and evidence confidence.
- `Q-048`: cold-start substitute blending matches exact weights.
- `Q-049`: partial list has PARTIAL status and excluded/degraded arrays.
- `Q-050`: all-insufficient list has INSUFFICIENT_DATA status.
- `Q-051`: idempotency concurrent race returns one owner and one in-progress conflict.
- `Q-052`: idempotency records expire/clean according to TTL.
- `Q-053`: reorder quality uses protection-horizon diagnostics.
- `Q-054`: ABC short history shows raw and confidence-adjusted annualisation.
- `Q-055`: weekday evidence uses exposure-qualified calendar days.
- `Q-056`: SciPy negative-binomial moments match target mean/variance.
- `Q-057`: quantile-to-mean response contains tail assumption.
- `Q-058`: GET forecast reads compatible cache/persisted run and POST persists idempotently.
- `Q-059`: assistant tool runs as caller and consumes caller rate limit.
- `Q-060`: cancelled job result contains no partial publishable recommendation.
- `Q-061`: approval creates a draft/requisition but not an official PO.
- `Q-062`: substitution-enabled simulation assigns fulfilment to the substitute correctly.
- `Q-063`: v6 precedence/deviation report is generated.

## 10. Final implementation instruction

Begin by inspecting the repository. Implement this addendum together with Phase 1, Phase 2, and Phase 3 of v4/v5. Do not leave cold-start logic, optimisation bound semantics, reorder quality horizon, portfolio metrics, substitution, approval workflow, ABC display confidence, or document precedence to implementer discretion.

At completion, report:

- Exact files changed.
- Migrations.
- New models/endpoints/tools.
- Formula and algorithm versions.
- Configuration snapshots.
- Acceptance-matrix pass/fail results, including Q-041 through Q-063.
- Golden-file changes.
- Benchmark measurements.
- Any repository-driven deviations.
- Remaining limitations.

Do not return only a plan. Implement executable behaviour and tests.