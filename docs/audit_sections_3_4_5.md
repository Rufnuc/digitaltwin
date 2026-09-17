# DigitalTwin Audit — Sections 3 (Workflows), 4 (Files), 5 (Phased Backlog)

Continues `audit_master_2026-09.md`. Same rubric (Severity / Confidence, evidence-cited). New findings from this pass are numbered N-x; earlier ones referenced as C-x / H-x.

---

# SECTION 3 — WORKFLOW AUDITS

## 3A. Sale → invoice → stock fulfilment (`POST /invoices/sell`)

The single most consequential workflow: it creates money owed and moves physical stock in one call.

**1. What can go wrong**
- Double submit / retry → two invoices, stock drawn twice (C1).
- Two concurrent sales of the last units → oversell (C2, no lot locking).
- Reused `invoice_number` → duplicates (C1, no unique constraint).
- Sale succeeds but the customer's dashboard stock value never changes (N1 — see below).

**2. What would silently corrupt trust**
- N1 (Confirmed, Critical): `/sell` decrements `StockLot.quantity_remaining` only. But the **dashboard inventory value** (`analytics.py:122`, `sum(Inventory.quantity_on_hand * unit_cost)`) and **product BI on-hand** (`bi/products.py:52`) read `Inventory.quantity_on_hand`, which selling never touches. So after every sale the headline "inventory value" is stale, and the quant module (`quant/service.py:_on_hand`, lots-first-else-legacy) shows a *third* answer. Three modules, three stock truths. This corrupts trust silently because each screen looks internally consistent.
- Partial failure mid-loop: `sell` wraps allocation in try/except with `db.rollback()` on `StockError` (good — atomic). Confirmed OK.

**3. Must be blocked/constrained in the UI**
- Disable the Sell button while the request is in flight; one idempotency key per click.
- Don't let the operator pick a warehouse with insufficient stock without a clear pre-check (currently the 422 comes back after submit).

**4. Must be enforced only on the backend**
- Unique `invoice_number`; idempotency; lot row locking; on-hand derived from lots everywhere. UI cannot guarantee any of these.

**5. What to log**
- Already good: invoice version snapshot + audit CREATE with warehouse. Add the idempotency key and the allocated lot ids to the audit payload.

**6. Tests to prove it safe**
- Concurrent double-sell of last units; idempotent replay; duplicate number rejected; dashboard value == lot-derived value after a sale (N1).

Issue cards:
- **N1 — Dashboard/BI read a stock number that selling never updates** · Critical · Confirmed · Data model/Reporting · Where: `analytics.py:122`, `bi/products.py:52` vs `stock.py sell/_draw_fifo` and `quant/service.py:31`. Fix: derive on-hand/value from lots in analytics and BI (or make `Inventory` a maintained projection updated in the same transaction as the lot draw). Test: Yes.

## 3B. Payment recording → receivables

**1. What can go wrong**: double-tap records two payments (C4); concurrent payments exceed balance (C4); a payment recorded against the wrong invoice can't be corrected except by void.

**2. Silent trust corruption**: `void_payment` flips status to VOIDED with **no reason and no actor captured** (`receivables.py:82`) — a reversal leaves no "why". If an invoice total is later edited (C5), `amount_paid` isn't re-derived, so status lies.

**3. UI constraints**: disable "Record payment" while pending; show the exact outstanding at submit time and re-fetch after.

**4. Backend-only**: idempotency key; lock invoice row during `_recalc`; payment status always derived by the single writer `_recalc`; block edits to paid invoices.

**5. Log**: who recorded (already captured — `recorded_by_user_id`, good); add void reason + actor; capture bank fields (already present — good).

**6. Tests**: double-submit → one payment; two concurrent partials past balance → one rejected; void requires reason; edit total after full payment → status recomputed (C5).

Issue card:
- **N2 — Void payment has no reason/actor** · High · Confirmed · Workflow · Where: `receivables.py:82` `void_payment`. Fix: require `reason`, record actor/source, audit old→new status. Test: Yes.

## 3C. Assistant-triggered write (Benfieg action tools)

**1. What can go wrong**: the LLM misparses intent and commits a write instantly — set inventory, record payment, change cost (C6). A STAFF user pulls MANAGER-only financials via chat (H2). No kill switch to stop it (C6).

**2. Silent trust corruption**: an unsourced or miscopied number in the prose (C7) — the guarantee is prompt-only.

**3. UI constraints**: mutating tools should return a *proposal* rendered for explicit confirmation before a second execute call; show a persistent "assistant is in read-only mode" state when the kill switch is on.

**4. Backend-only**: enforce `min_role` for **all** tools (not only mutating — `execute_tool` currently gates only `if tool.mutating`); honor a server-side kill switch; require a confirmation token for mutating tools; verify numbers against tool outputs before returning.

**5. Log**: AI mutations currently log summary only, no entity id/old→new (`execute_tool` audit.record) — upgrade to structured old/new (H3). The per-user AI_QUERY audit with tools+actions is good.

**6. Tests**: STAFF asks for payables → refused; "record a payment" → proposal, no write until confirmed; kill switch on → refused; answer with an unmatched number → flagged.

**Positives verified (credit where due):**
- Assistant chat history is **per-user with an ownership check** — `history.save_turn` refuses to write into another user's `conversation_id` (`ai/history.py`), and reads are user-scoped. No IDOR.
- Prior turns are **not fed back to the model** — `ask()` passes only the current question — so there is **no cross-turn or cross-user memory bleed** and no injection-via-stored-history into the model. (Trade-off: no real follow-up context; a UX limit, not a safety hole.)
- Voice transcription is local/offline (`transcribe_wav`, Whisper) — voice never leaves the machine.

## 3D. User management & destructive admin (roles, passwords, purge)

**1. What can go wrong** (all Confirmed from `auth.py:74-96`):
- **N3 — Privilege escalation via role edit**: `update_user` lets any ADMIN set any user's `role`, including their own, with **no check that you can't grant a role at or above your own**. Since OWNER is now the top role, an ADMIN can promote themselves or a colleague to OWNER.
- **N4 — Account takeover via password reset**: `update_user` lets an ADMIN set **any** user's password (`changes["password"]`), including a higher-privileged OWNER's — then log in as them. Admin-tier compromise = full compromise.
- **N5 — Last-owner lockout**: there's a self-deactivation guard (`user.id == admin.id and is_active False`), good — but **no guard against demoting/deactivating the last remaining OWNER**, which could lock the business out of owner-only actions (e.g. `purge-demo`).

**2. Silent trust corruption**: password-hash changes may be written to the audit trail as old→new `hashed_password` (verify the listener excludes it) — storing hashes in logs is a leak.

**3. UI constraints**: don't offer a role option above the actor's own; confirm password resets of other users.

**4. Backend-only**: cap the role an actor may grant at their own level; block reset of a higher-or-equal-role user's password; guarantee ≥1 active OWNER; exclude password fields from audit values.

**5. Log**: role changes and password resets must be audited with actor + target + old→new role (never the password).

**6. Tests**: ADMIN → set role OWNER = refused; ADMIN → reset OWNER password = refused; deactivate last OWNER = refused; audit never contains a password/hash.

**Purge-demo (`admin.py`)**:
- Positives: OWNER-gated, provenance-precise (only DEMO rows), audited, FK-safe order for the tables it covers.
- **N6 — Purge leaves orphans** · Medium · Likely · Data model: `purge_demo` deletes demo Invoices/Customers/Products/etc. but **not** demo `Payment`, `SupplierPayment`, `StockLot`, `StockMovement`, or `SimulationRun` rows. Deleting demo invoices/products can dangle `Payment.invoice_id` / `StockMovement.product_id` (FK error, or orphaned rows if FKs aren't enforced). Fix: include those tables (by demo linkage) in the purge and run inside one transaction with FK checks on.

**Login**: no rate-limit/lockout on `/auth/login` → brute-force exposure. Medium (N7).

---

# SECTION 4 — FILE REVIEWS

## 4A. `app/services/stock.py` — role: the ledger engine (highest-value correctness code)
Risk profile: correct in single-user, unsafe under concurrency; the ledger itself is clean and immutable (good).
Top issues:
1. No lot locking in `_draw_fifo`/`allocate_for_sale`/`transfer_stock` (C2) · Critical · Confirmed. Fix: `select(StockLot)…with_for_update()` in `_open_lots` when called for a write; re-check availability after acquiring locks.
2. `on_hand` (lots) vs `Inventory.quantity_on_hand` divergence — this file is right, callers (`analytics`, `bi`) are wrong (N1) · Critical.
3. `adjust_lot` requires a reason (good); ensure `user_id` is always passed from endpoints (some callers pass None).
4. Lot-code generation retries 20× on collision (fine); `transfer_stock` suffix `-T{hex1}` (1 byte) could collide across many transfers — Low.
Backend rules that must also exist: locking, single stock source. Tests first: concurrent draw; transfer race; adjust-negative guard (present) .

## 4B. `app/services/receivables.py` — role: the single writer of payment status
Risk profile: the derived-status design is good; the write path is racy.
Top issues:
1. `record_payment` not idempotent + unlocked overpayment check (C4) · Critical.
2. `void_payment` no reason/actor (N2) · High.
3. `_recalc` is the single writer — good — but nothing forces callers that change `invoice.total` to call it (C5) · Critical (cross-file).
4. `customer_statement` running balance recomputed each call — fine; O(invoices×payments) queries in a loop → N+1, Medium perf for big customers.
Backend rules: idempotency, row lock, status always via `_recalc`. Tests: double-pay, concurrent partials, void reason, edit-after-pay recompute.

## 4C. `app/api/crud.py` — role: generic CRUD for 8 core entities (widest blast radius)
Risk profile: convenient but too permissive for high-consequence tables.
Top issues:
1. **Hard delete** (`delete_item`, `db.delete`) on products/customers/suppliers/warehouses (H1) · High · Confirmed. Fix: soft-delete flag; refuse when referenced.
2. **`Inventory` writable here** (`router.py:168`, STAFF) — direct `quantity_on_hand` PATCH bypasses the ledger (C3/N1) · Critical. Fix: remove Inventory from write CRUD.
3. **Field-level mass assignment**: `update_item` sets every field in the update schema; if `credit_limit`, `data_origin`, `reliability_score`, `payment_terms_days` are in those schemas, any STAFF can change them (H6) · High · Likely. Fix: per-resource editable-field whitelist; gate sensitive fields to MANAGER+.
4. Relies entirely on the audit **listener** for logging — no `reason` is ever captured on generic edits/deletes. Medium. Fix: accept an optional reason on sensitive resources.
5. String filters use `func.lower(col) == value.lower()` — fine; no SQL injection (parameterised).
Backend rules: soft-delete, field whitelist, sensitive-field role gates. Tests: delete-with-references refused; STAFF cannot change credit_limit; inventory PATCH refused.

## 4D. `app/services/ai/tools.py` + `ai/assistant.py` — role: the LLM's hands
Risk profile: powerful, under-gated, unenforced provenance.
Top issues:
1. `execute_tool` gates role **only if mutating** — read tools' `min_role` ignored (H2) · High · Confirmed. Fix: check `role_at_least(user.role, tool.min_role)` for every tool.
2. No confirmation + no kill switch on mutating tools (C6) · Critical. Fix: kill-switch setting checked first; mutating tools return a proposal, execute only on a confirmed follow-up.
3. Provenance is prompt-only (C7) · Critical. Fix: numeric cross-check of the answer against tool results.
4. AI mutation audit is summary-only, no entity/old→new (H3) · High.
5. `execute_tool` catches only `TypeError`; a handler raising anything else propagates — verify the endpoint rolls back and doesn't leave a half-write. Medium.
Backend rules: role for all tools, kill switch, confirm-gate, numeric provenance, structured AI audit. Tests: as in 3C.

## 4E. `app/services/analytics.py` — role: the dashboard's numbers
Top issues:
1. Inventory value from `Inventory.quantity_on_hand` (N1) · Critical · Confirmed (`analytics.py:122`). Fix: value from lots (`sum(quantity_remaining × unit_cost)`), consistent with the sale engine.
2. Verify every headline KPI carries provenance to the UI (revenue/margin from real invoices = REAL; anything demo-mixed flagged). Cannot fully verify here — check the dashboard endpoint.
Tests: dashboard inventory value == lot-derived value after a sale.

---

# SECTION 5 — PHASED IMPLEMENTATION BACKLOG

## Phase 1 — Critical before live use
Goal: make the write paths safe under real concurrency, retries and edits, and stop the LLM from writing unchecked. Nothing here is large; all are blocking. Turning on more users before this multiplies every race.

1. **Unique `invoice_number` + idempotency keys** (C1, C4, H5) · Backend/Data model · Medium · deps: none · Tests: Yes (replay + duplicate-constraint).
2. **Lot row locking on sale/transfer/adjust** (C2) · Backend · Medium · deps: none · Tests: Yes (concurrent draw).
3. **Invoice-row lock + idempotency on `record_payment`** (C4) · Backend · Small · deps: 1 · Tests: Yes.
4. **Single stock truth**: derive on-hand/value from lots in `analytics.py` & `bi/products.py`; remove `Inventory` from write CRUD; route corrections through `adjust_lot` (C3, N1) · Data model/Reporting · Medium · deps: none · Tests: Yes (value==lots after sale).
5. **Edit-after-payment guards**: recompute payment status on any total change; block line/total edits once payments exist or stock moved (credit-note/void instead) (C5) · Workflow · Medium · deps: 3 · Tests: Yes.
6. **Assistant safety trio**: server-side kill switch / read-only mode; enforce `min_role` for all tools; confirm-gate mutating tools (C6, H2) · Assistant · Medium · deps: none · Tests: Yes.
7. **Numeric provenance check** on assistant answers (C7) · Assistant · Medium · deps: 6 · Tests: Yes.
8. **Privilege-escalation & takeover guards**: cap grantable role at actor's own; block password reset of ≥-role users; guarantee ≥1 active OWNER; keep password fields out of audit (N3, N4, N5) · Backend · Small · deps: none · Tests: Yes.

## Phase 2 — Highest-value next fixes
Goal: durability, traceability and reporting reliability once the acute risks are closed.

1. **Soft-delete/archive** for products/customers/suppliers/warehouses; refuse delete when referenced (H1) · Data model · Medium · deps: none · Tests: Yes.
2. **Structured AI-write audit** (entity + old→new) (H3) · Assistant · Small · deps: P1.6 · Tests: Yes.
3. **Void reason + actor**; audit reversals (N2) · Workflow · Small · deps: none · Tests: Yes.
4. **Field-level whitelist + sensitive-field gates** in generic CRUD (H6) · Backend · Medium · deps: none · Tests: Yes.
5. **Purge-demo completeness**: include demo Payment/SupplierPayment/StockLot/StockMovement/SimulationRun; run atomically (N6) · Backend · Small · deps: 1 (soft-delete pattern helps) · Tests: Yes.
6. **One selling path**: make `/sell` the only stock-moving invoice route; relabel/limit `create_invoice` (H8) · Workflow · Small · deps: none · Tests: Some.
7. **Login rate-limit/lockout** (N7) · Backend · Small · deps: none · Tests: Yes.
8. **Actor+source middleware** so every authed write is attributed (H9) · Backend · Small · deps: none · Tests: Some.

## Phase 3 — Hardening & cleanup
Goal: reduce friction and debug burden; strengthen auditability; simplify.

1. Closed-period locks for expenses/tax so historical figures can't shift (H4) · Reporting · Medium · Tests: Yes.
2. N+1 cleanup in `customer_statement` and `_user_names` (load-all-users per list) · Backend · Small · Tests: No.
3. Reconciliation report: lot-derived vs `Inventory` per product, run once at cutover and periodically · Reporting · Small · Tests: No.
4. Assistant multi-turn context (safe, per-user) if follow-ups are wanted · Assistant · Medium · Tests: Some.
5. Transfer lot-code entropy bump; misc Low items · Backend · Small · Tests: No.

## Closing answers
1. **Before any further feature expansion**: complete Phase 1. More features/users before that just widen the exposure.
2. **Pause or remove now**: assistant write tools (ship read-only first); direct `Inventory` writes (CRUD + `_set_inventory`); hard delete of core entities; the plain `create_invoice` path for stock items.
3. **Do not build yet**: cloud multi-user rollout, more assistant autonomy/automation, additional analytics/forecasting surfaces — all until Phase 1 lands, because they add concurrent writers or unverified numbers.
4. **Order within phases**: follow the numbering. In Phase 1, items 1-3 (locking+idempotency) and item 6 (assistant read-only) are the fastest risk-per-hour wins; do them first, then 4/5, then 7/8.

---

*Still not verified from code (honest gaps):* exact DB isolation level in production; whether the dashboard endpoint forwards provenance for every KPI; whether the audit listener excludes `hashed_password` from stored old/new values (N4 hygiene). Each is a quick targeted check.
