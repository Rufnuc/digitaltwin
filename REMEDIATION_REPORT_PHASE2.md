# Remediation Report — Phase 2 (remaining risks)

Date: 2026-09-17. Scope: the seven remaining items from `docs/remediation_report_2026-09.md`. **No commits, pushes, branches, or tags were made — all changes are left uncommitted for review.**

**Status legend:** *Verified fixed* = code changed and the relevant test passed here. *Implemented but unverified* = code changed but the test could not run here. *Not fixed* = still open.

Test run: full backend suite **passes (exit 0, 0 failures)**, including the new Postgres concurrency tests (a real Postgres was available). Frontend typechecks clean; the payment idempotency path was verified live in the browser. Two schema migrations were applied to the live Postgres and verified.

---

## Completed fixes

| # | Item | Status | Evidence |
|---|------|--------|----------|
| 1 | Postgres true-concurrency proof (stock + payment locking) | **Verified fixed** | `tests/test_concurrency_postgres.py` — two threads on separate Postgres connections: `test_concurrent_sales_cannot_oversell` (one sale wins, on_hand=0) and `test_concurrent_payments_cannot_exceed_balance` (one payment wins, total=1000) both pass against a throwaway `digitaltwin_conc_test` DB |
| 2 | Confirm-gated assistant writes | **Verified fixed** | Mutating tools now PROPOSE (never execute) on first call; a signed token must be confirmed to run. `tests/test_hardening_phase2.py` (5 tests) + updated `tests/test_assistant.py`: propose→confirm, kill-switch overrides confirm, tampered token rejected, cross-user token rejected, endpoint executes |
| 3 | Frontend idempotency plumbing + disabled submit | **Verified fixed** | `newIdempotencyKey()` sent as `Idempotency-Key` on sell + all 3 payment modals; submit already disabled via `busy`. Live browser test: a recorded payment created an `idempotency_keys` row (scope `record_payment`, UUID key, completed) in the live DB — proving the header reaches the backend end-to-end. Frontend `tsc --noEmit` clean |
| 4 | Idempotency TTL / stranded-key cleanup | **Verified fixed** | Stranded in-progress reservations (older than `STRANDED_TTL`=2min) are reclaimed by a retry; completed keys never expire. `cleanup_stranded()` sweep added. 3 tests pass |
| 5 | Login rate limiting / brute-force protection | **Verified fixed** | Per-account failure counter + lockout (`LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`); locked accounts get 429 even with the correct password; success resets. 3 tests pass; live login smoke = 200 |
| 6 | Purge-demo completeness (no orphans) | **Verified fixed** | Purge now removes demo-linked `StockMovement`, `StockLot`, `Payment`, `SupplierPayment` (by FK linkage) before their parents, atomically. `test_purge_demo_leaves_no_orphaned_demo_linked_rows` passes |
| 7 | Inventory reconciliation (legacy cutover) | **Verified fixed** | `app/services/inventory_reconcile.py` + `scripts/reconcile_inventory.py`: dry-run by default, explicit `--apply` (audited, conservative — only products with lots). 3 tests pass; CLI runs against the live DB |

### Notes on design decisions (safest-restrictive choices)
- **Confirm-gating preserves the read-only default.** When `ASSISTANT_ALLOW_WRITES=False` (the default), mutating tools still return the read-only refusal — unchanged. Confirm-gating only adds the mandatory two-step when writes are explicitly enabled, so the default posture is not weakened; it is strengthened (writes-on no longer executes immediately).
- **SimulationRun intentionally excluded from purge-demo:** it has no product/invoice foreign key and no provenance tag, so no simulation row is ever orphaned by the purge; deleting runs would destroy the operator's real analysis. Documented in `admin.py`.
- **Reconciliation never silently overwrites:** dry-run is the default; `--apply` is explicit, audited (`source="inventory_reconcile"`), and touches only products that have lots.
- **Item 3 UI tests:** the web app has no test runner configured; adding one was out of scope. The disabled-submit + key-per-action behavior is in code and typechecked, and the header path was verified live against the backend (which itself has unit tests).

---

## Files changed

**Backend (code):**
- `app/models/idempotency.py` — `response_json` now `JSON(none_as_null=True)` so IS-NULL filters work.
- `app/models/user.py` — `failed_login_count`, `lockout_until`.
- `app/core/config.py` — `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES` (ASSISTANT_ALLOW_WRITES already present).
- `app/services/idempotency.py` — stranded-reservation reclaim (`STRANDED_TTL`) + `cleanup_stranded()`.
- `app/services/ai/confirm.py` — NEW: signed confirmation tokens (HMAC + TTL).
- `app/services/ai/tools.py` — `execute_tool(confirmed=…)`: propose-then-confirm for mutating tools; structured proposed/confirmed audit.
- `app/services/ai/assistant.py` — surface `proposals`, exclude proposals from `actions_taken`.
- `app/services/ai/providers/rule_based.py` — relay a proposal instead of formatting an unexecuted write (`_ProposalPending`).
- `app/services/inventory_reconcile.py` — NEW: divergence report + conservative apply.
- `app/api/v1/endpoints/assistant.py` — `POST /assistant/confirm` (token → execute; kill-switch & role re-checked; cross-user rejected).
- `app/api/v1/endpoints/auth.py` — login lockout logic.
- `app/api/v1/endpoints/admin.py` — purge-demo now removes demo-linked child rows first.

**Backend (scripts):**
- `scripts/reconcile_inventory.py` — NEW CLI (`python -m scripts.reconcile_inventory [--apply]`).

**Frontend:**
- `apps/web/lib/api.ts` — `newIdempotencyKey()`; `Idempotency-Key` header on `invoiceSell`, `recordPayment`, `createResource`.
- `apps/web/app/(app)/sell/page.tsx` — key per sale, regenerated on success.
- `apps/web/app/(app)/receivables/page.tsx`, `customers/page.tsx`, `invoices/page.tsx` — key per payment modal.

## Migrations added (both applied to the live Postgres and verified)
- `alembic/versions/c1a2b3d4e5f6_hardening_invoice_unique_idempotency.py` (Phase 1; applied earlier).
- `alembic/versions/d2b3c4e5f6a7_login_lockout_fields.py` — `users.failed_login_count`, `users.lockout_until` (Phase 2; applied now).

## Tests added or updated
- NEW `tests/test_concurrency_postgres.py` (2 Postgres tests; auto-skips without a Postgres URL).
- NEW `tests/test_hardening_phase2.py` (confirm-gating 5, TTL 3, login 3, purge 1, reconcile 3 = 15).
- Updated `tests/test_assistant.py` (two-step propose/confirm), `tests/test_hardening_phase_c.py` (proposal semantics), `tests/quant/test_substitutes.py` (`confirmed=True`).

## Test results
- Full backend suite: **exit 0, 0 failures** (includes the 2 Postgres concurrency tests).
- Frontend: `tsc --noEmit` clean.
- Lint: changed files pass `ruff` (one pre-existing E501 in unrelated `tests/test_shipping.py` left untouched per containment rules).

## Unsafe behaviors intentionally left disabled
- **Assistant writes remain OFF by default** (`ASSISTANT_ALLOW_WRITES=False`). Confirm-gating is now built and tested, but the default posture is unchanged; enabling writes is a deliberate operator action, and even then every write is two-step.
- Direct `Inventory.quantity_on_hand` editing — still disabled.
- Hard delete of referenced core entities — still disabled (soft-delete/refuse).
- Editing paid/fulfilled invoices' amounts/lines — still blocked.
- Plain `create_invoice` with product lines — still blocked (stock sells via `/sell`).

## Remaining unresolved risks
- IP-based login throttling is deliberately **not** added in-app (see follow-up 5 below) — the per-account DB lockout is the auditable protection; IP throttling belongs at the reverse-proxy/gateway in production.

---

# Follow-ups — completed (2026-09-17, later same day)

The manual follow-ups were then done. Same status rules.

| # | Follow-up | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Schedule `cleanup_stranded()` | **Verified fixed** | `app/services/maintenance.py` — hourly background loop started in `main.py` startup / stopped on shutdown; sweep runs off the event loop. `test_maintenance_sweep_removes_stranded` passes; live startup log shows "Maintenance loop started." |
| 2 | In-app proposal→confirm UI | **Verified fixed** | `apps/web/.../assistant/page.tsx` `ProposalCard` + `api.assistantConfirm`. Browser end-to-end (writes temporarily enabled, `rule_based`): "Add customer Acme Motors" → amber "Needs your confirmation — no change made yet" with Confirm/Dismiss → Confirm → "✓ Change applied"; customer count 1→2; audit shows a **PROPOSED** and a **CONFIRMED** entry. Test record cleaned up; API restored to writes-OFF. |
| 3 | Reconcile at cutover | **Operational step** | `python -m scripts.reconcile_inventory` dry-run on the live DB reports 0 divergences (live has no lots yet). Re-run (dry-run then `--apply`) at the real-data cutover — nothing to apply now. |
| 4 | Frontend test runner | **Verified fixed** | Vitest + jsdom added (`vitest.config.ts`, `npm test`). `lib/__tests__/idempotency.test.ts` (5 tests) covers key uniqueness, header attachment on sell + payment, same-key reuse across a retry, and no-header when omitted. All pass. |
| 5 | IP-based login throttling | **Intentionally not implemented (documented)** | The per-account lockout (item 5) is the robust, auditable control and covers targeted brute force. An in-memory per-IP throttle would be per-process/fragile — exactly what the brief warned against — so IP throttling is left to the production reverse proxy/gateway. |

**Also fixed:** the pre-existing `ruff` E501 in `tests/test_shipping.py:20` (previously left untouched under containment) — now `ruff check` is fully clean.

### Additional files changed by the follow-ups
- Backend: `app/services/maintenance.py` (NEW), `app/main.py` (start/stop the loop), `tests/test_hardening_phase2.py` (+maintenance test), `tests/test_shipping.py` (lint).
- Frontend: `apps/web/lib/api.ts` (`AssistantProposal`, `assistantConfirm`), `apps/web/app/(app)/assistant/page.tsx` (`ProposalCard`), `apps/web/vitest.config.ts` (NEW), `apps/web/package.json` (test script + vitest/jsdom devDeps), `apps/web/lib/__tests__/idempotency.test.ts` (NEW).

### Verification after follow-ups
- Full backend suite: **exit 0, 0 failures**. Frontend: `tsc --noEmit` clean + `vitest` 5/5. `ruff`: all checks pass.
- API restarted on the **default safe posture** (`ASSISTANT_ALLOW_WRITES=False`, `.env` provider); maintenance loop running.
- Still **not committed** — all changes remain in the working tree for review.
