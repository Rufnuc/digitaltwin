# Claude quant implementation prompt v7: last formula-level closures

This is the final addendum to the DigitalTwin quantitative inventory implementation specification. It supersedes only the six items below. All other rules remain governed by the precedence table in v6 and the earlier prompts referenced there.

Implement these decisions in executable code, tests, API metadata, provenance, and documentation.

## 1. Correct cold-start coefficient-of-variation formula

The cold-start parameter is the coefficient of variation, not a dispersion parameter.

For mean horizon demand `mu = D_blended` and coefficient of variation `CV`:

`variance = CV^2 * mu^2`

Default CV values:

- Backorder evidence: `CV = 1.0`.
- Enquiry-only evidence: `CV = 2.0`.
- Substitute-only prior: `CV = 1.5`.

Return `coefficient_of_variation`, `variance_formula="CV^2 * mu^2"`, and the resulting variance. Do not use `(1 + CV^2) * mu^2`.

## 2. Small-mean cold-start distribution fallback

A negative-binomial distribution is valid only when its variance exceeds its mean.

For `mu > 0`:

1. Calculate `var = CV^2 * mu^2`.
2. If `var > mu`, use the specified negative-binomial parameterisation:

`r = mu^2 / (var - mu)`

`p = r / (r + mu)`

and use the repository’s pinned SciPy/NumPy convention.
3. If `var == mu`, use Poisson with lambda `mu`.
4. If `var < mu`, use Poisson with lambda `mu` and return warning `COLD_START_VARIANCE_UNDERDISPERSED_POISSON_FALLBACK`.
5. If `mu == 0`, return no numeric prior.

The predictive distribution’s `distribution_family`, parameters, variance, and fallback warning must be visible in the API response.

## 3. Deterministic substitute ordering

When substitution is enabled, sort eligible substitutes using this exact order:

1. `compatibility_status` priority: `VERIFIED_EXACT` first, then `VERIFIED_EQUIVALENT`, then `VERIFIED_FUNCTIONAL`, then `VERIFIED_POSSIBLE`.
2. Highest available quantity descending.
3. Lowest landed cost ascending.
4. Product ID ascending.

Only these statuses are eligible. Any other status is excluded. Return the selected status and the ordered candidate list in simulation metadata.

## 4. Fallback quant-linked purchase draft schema

If the repository has no purchase requisition or purchase-draft model, create `quant_purchase_drafts` and `quant_purchase_draft_lines`.

### `quant_purchase_drafts`

- `id` UUID primary key.
- `recommendation_id` UUID unique foreign key to the reorder recommendation.
- `branch_id` UUID nullable only under single-branch configuration.
- `supplier_id` UUID nullable when supplier selection is unresolved.
- `status`: `DRAFT`, `PENDING_PROCUREMENT_CONFIRMATION`, `CONVERTED`, `CANCELLED`, `EXPIRED`.
- `currency_code`.
- `estimated_total_cost` Decimal(16,2).
- `requires_procurement_confirmation` boolean default true.
- `created_by_id`.
- `approved_by_id` nullable.
- `created_at`, `updated_at`.
- `confirmed_at` nullable.
- `cancelled_at` nullable.
- `expires_at` nullable.
- `data_origin` and provenance fields.
- `source_input_data_version`.
- `model_version`.
- `config_version`.

### `quant_purchase_draft_lines`

- `id` UUID primary key.
- `draft_id` foreign key.
- `product_id` foreign key.
- `supplier_id` nullable.
- `quantity` Decimal(14,3), strictly positive.
- `unit_cost` Decimal(16,2) nullable.
- `landed_unit_cost` Decimal(16,2) nullable.
- `estimated_line_total` Decimal(16,2) nullable.
- `moq` Decimal(14,3) nullable.
- `order_multiple` Decimal(14,3) nullable.
- `recommendation_line_reference` string.
- `created_at`, `updated_at`.

Lifecycle:

1. MANAGER approval of a valid recommendation creates one idempotent draft.
2. Draft starts as `PENDING_PROCUREMENT_CONFIRMATION`.
3. Procurement confirmation converts it through the existing procurement workflow if available.
4. Conversion records the resulting official purchase-order ID.
5. No external supplier communication occurs from quant approval alone.
6. Draft may be cancelled by MANAGER, OWNER, or ADMIN with a reason code.
7. Draft expires after 30 days if not confirmed; it cannot be converted after expiry without revalidation.
8. If current inventory, supplier price, lead time, or recommendation input hash has materially changed before confirmation, require revalidation and keep the draft unconverted.
9. Approval and draft creation are one idempotent transaction: duplicate approval requests return the existing draft.

If an existing procurement draft/requisition model exists, use it instead and map these fields through an adapter. Do not create two draft systems.

## 5. Substitute-group prior and product heterogeneity

The substitute-group prior must not silently let one high-volume product dominate without disclosure.

Default method: **equal-weight per-product rate average**.

For each eligible substitute product j:

`rate_j = verified_demand_units_j / max(exposure_days_j, 1)`

Require at least 3 complete periods per product. Exclude products without sufficient evidence and return them in `excluded_sources`.

Then:

`group_rate = mean(rate_j across eligible substitute products)`

`S = group_rate * H * transfer_factor`

Return:

- Each product’s rate.
- Each product’s exposure days.
- Number of eligible and excluded products.
- Aggregation method `EQUAL_WEIGHT_PRODUCT_RATE_MEAN`.
- Warning `SUBSTITUTE_PRIOR_HETEROGENEITY_NOT_MODELLED` when the coefficient of variation of eligible product rates exceeds 1.0.

Optional future method `EXPOSURE_WEIGHTED_RATE` may be supported only through an explicit configuration setting. It must not be silently substituted for the default.

## 6. Acceptance matrix correction

Replace documentation-only Q-063 with behavioural acceptance tests:

- `Q-063A`: When v6/v7 defaults override an earlier conflicting default, the effective configuration contains the v7 value and the result stores the v7 config version.
- `Q-063B`: When a repository-driven deviation is configured, the API response includes the deviation code and explanation in metadata/warnings.
- `Q-063C`: Replaying an old persisted result returns its stored formula/config/schema versions rather than applying the current defaults.

Keep a separate documentation checklist item:

- `DOC-001`: Precedence table and deviation report are present and match the effective configuration registry.

## 7. Required tests

Add these exact tests:

- `Q-064`: Cold-start variance equals `CV^2 * mu^2` for each evidence type.
- `Q-065`: Small-mean cold-start demand uses Poisson fallback when `variance <= mean`.
- `Q-066`: Negative-binomial cold-start parameters are used only when `variance > mean`.
- `Q-067`: Substitute ordering follows exact compatibility-status, quantity, cost, and ID ordering.
- `Q-068`: Fallback purchase draft schema links exactly one recommendation and creates idempotently.
- `Q-069`: Draft lifecycle prevents conversion after expiry or stale-input detection.
- `Q-070`: Substitute prior uses equal-weight product-rate mean by default and returns heterogeneity warning.
- `Q-071`: Older persisted results retain old formula/config versions after defaults change.
- `Q-072`: Configuration precedence/deviation metadata is behaviourally exposed by the API.

## 8. Final instruction

Begin by inspecting the repository. Implement these closures together with the earlier phased quant specification. Do not leave cold-start variance, small-mean distribution validity, substitute ordering, purchase-draft schema, substitute heterogeneity, or version-precedence behaviour to implementer discretion. Do not return only a plan; produce executable code and tests.