# Controlled Hardening Pass — Remediation Report (2026-09-17)

Executed the Phase A→D hardening from the operational audit. Analysis + code + tests + migration. **Status rule:** *Verified fixed* = a test for it passes; *Implemented (unverified)* = code changed but that specific property couldn't be exercised here; *Not fixed* = still open.

New tests: `tests/test_hardening_phase_a.py` (10), `_b.py` (7), `_c.py` (7), `_d.py` (12) + updates to `tests/test_assistant.py`. Migration: `alembic/versions/c1a2b3d4e5f6_hardening_invoice_unique_idempotency.py` (applied to the live Postgres, verified). All new + existing suites green.

---

## Completed fixes (by phase)

### Phase A — dangerous write failures
| # | Fix | Status | Evidence |
|---|-----|--------|----------|
| A1 | `invoice_number` unique at DB level | **Verified fixed** | `test_duplicate_invoice_number_rejected`, `test_sell_duplicate_number_rejected_stock_drawn_once` pass; migration applied to live DB (`uq_invoices_invoice_number` present) |
| A2 | Idempotency on sell / create-invoice / payment (`Idempotency-Key` header, reserve-first) | **Verified fixed** | `test_sell_idempotent_replay_draws_stock_once`, `test_create_invoice_idempotent_replay`, `test_payment_idempotent_replay_records_once` pass (one write per key) |
| A3 | Lot row-locking (`FOR UPDATE`) on sale/transfer; re-check availability under lock | **Verified fixed (guard)** / **Implemented (unverified: true concurrency)** | `test_sequential_draws_never_exceed_stock` passes. SQLite ignores `FOR UPDATE`, so the *parallel-writer* race is covered by the lock code but provable only on Postgres |
| A4 | Invoice-row lock + idempotency in `record_payment`; re-validate balance under lock | **Verified fixed (guard)** / **Implemented (unverified: true concurrency)** | `test_overpayment_rejected`, payment idempotency pass; parallel-writer overpay needs Postgres |

### Phase B — consistency of business truth
| # | Fix | Status | Evidence |
|---|-----|--------|----------|
| B1 | One stock source of truth: lot ledger authoritative; `analytics`/`bi` value & on-hand read lots-first-else-legacy; `Inventory` CRUD read-only; assistant `set_inventory` quantity refused | **Verified fixed** | `test_stock_value_is_lot_authoritative_and_ignores_legacy`, `test_stock_value_reflects_a_sale`, `test_inventory_direct_write_refused` pass; assistant inventory-quantity refusal in `test_assistant_inventory_quantity_write_refused_but_cost_allowed` |
| B2 | Block line/amount edits on paid or stock-moved invoices; re-derive payment status on total change | **Verified fixed** | `test_edit_paid_invoice_amounts_blocked`, `test_edit_fulfilled_invoice_lines_blocked`, `test_edit_unpaid_invoice_still_allowed_and_status_consistent` pass |
| B3 | Plain `create_invoice` refuses product lines (stock must sell via `/sell`) | **Verified fixed** | `test_plain_create_with_product_line_blocked` passes |

### Phase C — assistant safety
| # | Fix | Status | Evidence |
|---|-----|--------|----------|
| C1 | Read-only by default + kill switch (`ASSISTANT_ALLOW_WRITES`, default False); mutating tools refused when off | **Verified fixed** | `test_mutating_tool_disabled_in_read_only_mode`, `test_mutating_tool_allowed_when_writes_enabled`, `test_assistant_read_only_by_default_blocks_writes` pass |
| C2 | Enforce `min_role` for **all** tools (reads too) | **Verified fixed** | `test_restricted_read_tool_blocked_for_low_role`, `test_restricted_read_tool_allowed_for_manager` pass |
| C3 | Confirm-gated writes | **Not implemented (by design)** | Left writes disabled instead; see "Unsafe behaviors disabled". Re-enabling requires confirm-gating first |
| C4 | Numeric provenance check on answers (flag + log unverified figures) | **Verified fixed** | `test_unverified_number_flagged`, `test_sourced_number_passes`, `test_small_bare_numbers_ignored` pass |
| C5 | Structured AI-write audit (actor/entity/old→new/source) | **Implemented (unverified)** | Code in `execute_tool`; only exercised when writes are enabled (off by default), so no dedicated failing/passing assertion beyond the enabled-write path |

### Phase D — privilege & deletion
| # | Fix | Status | Evidence |
|---|-----|--------|----------|
| D1 | No granting a role above your own; no self-role change; only OWNER appoints OWNER; last-OWNER protected | **Verified fixed** | `test_admin_cannot_grant_owner_role`, `test_admin_cannot_change_own_role`, `test_owner_can_grant_owner`, `test_admin_cannot_deactivate_sole_owner` pass |
| D2 | No password reset of equal/higher-privilege users; password hashes never in audit | **Verified fixed** | `test_admin_cannot_reset_owner_password`, `test_admin_can_reset_staff_password`, `test_password_hash_never_in_audit` pass |
| D3 | Delete refused when referenced by financial/stock records; soft-delete via status/is_active otherwise | **Verified fixed** | `test_delete_referenced_product_refused`, `test_delete_unreferenced_customer_archives`, `test_delete_referenced_customer_refused` pass |
| D4 | Sensitive-field gating (supplier `reliability_score` → MANAGER+); `data_origin` never client-settable | **Verified fixed** | `test_staff_cannot_change_supplier_reliability`, `test_manager_can_change_supplier_reliability` pass |

---

## Files changed
- Models: `app/models/invoice.py` (unique invoice_number), `app/models/idempotency.py` (new), `app/models/__init__.py` (register).
- Services: `app/services/idempotency.py` (new), `app/services/receivables.py` (lock + idempotency), `app/services/stock.py` (lot locking + `on_hand_totals`/`stock_value`), `app/services/analytics.py` + `app/services/bi/products.py` (lot-authoritative), `app/services/audit_listener.py` (redact `hashed_password`, exclude idempotency table), `app/services/ai/tools.py` (kill switch + role-for-all-tools + inventory-quantity refusal + structured audit), `app/services/ai/assistant.py` (numeric provenance), `app/services/ai/provenance.py` (new).
- API: `app/api/crud.py` (writable flag, delete safety, soft-delete, sensitive-field gate, drop data_origin), `app/api/v1/endpoints/invoices.py` (idempotency, dup handling, edit guards, status re-derive), `app/api/v1/endpoints/receivables.py` (idempotency header), `app/api/v1/endpoints/auth.py` (privilege/password/last-owner guards), `app/api/v1/router.py` (Inventory read-only).
- Core: `app/core/config.py` (`ASSISTANT_ALLOW_WRITES`), `app/core/security.py` (`role_rank`).

## Migrations added
- `c1a2b3d4e5f6_hardening_invoice_unique_idempotency.py`: creates `idempotency_keys`, adds `uq_invoices_invoice_number`. **Applied to the live Postgres and verified.** Precondition (0 duplicate invoice numbers) was checked before applying.

## Tests added or updated
- Added: `test_hardening_phase_a.py`, `_b.py`, `_c.py`, `_d.py` (36 new tests).
- Updated: `test_assistant.py` — three tests rewritten to assert the new safe behavior (read-only default; writes only when explicitly enabled; inventory-quantity always refused) instead of the old always-on writes.

## Unsafe behaviors disabled
- **Assistant writes are OFF by default** (`ASSISTANT_ALLOW_WRITES=False`). Mutating tools refuse until writes are enabled AND confirm-gating exists. This is the kill switch.
- **Direct `Inventory.quantity_on_hand` editing removed** — `/inventory` is read-only; assistant `set_inventory` refuses quantity. Corrections go through receive/adjust (audited movements).
- **Hard delete of referenced core entities removed** — refused when invoices/lots/payments point at them; otherwise soft-deleted (archived).
- **Editing paid or fulfilled invoices' amounts/lines blocked** — corrections via void/credit-note or stock adjustment.
- **Plain `create_invoice` no longer accepts product lines** — stock sales must go through `/sell`.

## Remaining unresolved risks / follow-ups before production
1. **True-concurrency proof (A3/A4)**: row-locking is in place but SQLite can't exercise a real parallel-writer race. Run a Postgres-backed concurrency test (two simultaneous `/sell` of the last units; two simultaneous payments) before relying on it under multi-user load.
2. **Confirm-gated assistant writes (C3)**: not implemented; writes stay disabled. Implementing a propose→confirm two-step is the prerequisite to safely re-enabling any assistant write.
3. **Idempotency-key plumbing on the frontend**: the backend honors `Idempotency-Key`; the web client should generate one per submit (sell / create-invoice / record-payment) and disable the button while pending to get the full double-click protection end-to-end.
4. **In-flight reservation cleanup**: a request that reserves a key then crashes before `complete()` leaves the key "in progress" (future retries get 409). Acceptable (fails safe), but add a short TTL/cleanup so a genuinely retried request isn't blocked forever.
5. **Login rate-limiting (audit N7)**: not in this pass — brute-force protection still to add.
6. **Purge-demo orphans (audit N6)**: not in this pass — demo Payment/StockLot/StockMovement rows aren't purged; unchanged.
7. **Legacy Inventory reconciliation**: `stock_value`/`on_hand_totals` prefer lots and fall back to Inventory per-product. Run a one-time reconciliation at cutover so no product silently relies on a stale Inventory scalar.
8. **Manual precondition for the migration on any other environment**: ensure 0 duplicate `invoice_number`s before `alembic upgrade` (it will fail rather than guess).

## Explicitly out of scope (containment rules honored)
No new features, no cloud rollout, no added automation/forecasting, no new assistant autonomy. Assistant writes NOT re-enabled (confirm-gating/kill-switch/audit not all complete → left off). Direct inventory editing and hard delete of referenced entities NOT preserved.
