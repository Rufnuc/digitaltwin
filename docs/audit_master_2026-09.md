# Master Operational Risk Audit — DigitalTwin (internal business OS)

Scope: full-system audit as high-consequence internal software (real stock, invoices, payments, receivables, decisions). Every finding cites where it was seen in code or is marked "cannot verify from provided code." Confidence: Confirmed / Likely / Possible.

Audited: `deps.py`, `crud.py` (generic CRUD factory), `invoices.py` (create/sell/edit), `receivables.py`, `stock.py`, `ai/tools.py`, `ai/assistant.py`, `router.py`, `models/invoice.py`.

---

## 1. Executive diagnosis

The system is well-structured and unusually honest about provenance for read/reporting paths — the audit listener, invoice versioning, lot ledger, and REAL/MODEL/FORECAST tagging are genuinely good and above the norm for internal tooling. The reporting layer is largely trustworthy.

The danger is concentrated in the **write paths under real-world conditions**: concurrency, repeated clicks, edits-after-the-fact, direct table edits, and the LLM being allowed to write. The core records (stock, invoices, payments) are protected by *read-then-write* logic with **no locking, no idempotency, and no uniqueness**, so normal shop pressure (two staff, a double-tap, a retry on a flaky connection) can produce duplicate invoices, oversold stock, or double-recorded payments — silently. Stock has **two sources of truth** (the lot ledger and `Inventory.quantity_on_hand`) that are not reconciled and can be edited independently. Invoices can be **edited after payment/sale** without recomputing what's owed or reversing stock. And the assistant is allowed to **commit financial and stock writes with no confirmation step and no kill switch**, while its "never invent numbers" guarantee is **prompt-only**, not enforced.

Bottom line: the reports can be trusted more than the records they summarize. Before real operational use, the write paths need locking + idempotency + uniqueness, one stock source of truth, edit-after-payment guards, and the assistant put in read-only/confirm-gated mode with a kill switch. None of these are large; all are blocking.

---

## 2. Critical issues table

| Issue | Sev | Conf | Area | Operational risk | Fix | Timing |
|---|---|---|---|---|---|---|
| C1 No idempotency/uniqueness on invoices & sales | Critical | Confirmed | Backend/Data model | Double-click or retry creates duplicate invoice + draws stock twice; two staff reuse a number | Unique `invoice_number`; idempotency key on `/sell` & `POST /invoices` | Now |
| C2 Sale allocation has no row locking | Critical | Confirmed | Backend | Two concurrent sales oversell the same lots → negative real stock, wrong COGS | `SELECT … FOR UPDATE` on lots; serialize per (product,warehouse) | Now |
| C3 Two sources of truth for stock | Critical | Confirmed | Data model | `Inventory.quantity_on_hand` (editable) diverges from lot ledger; reports disagree | One source (lots); make Inventory a read-only projection | Now |
| C4 Payment recording not idempotent; overpayment guard races | Critical | Confirmed | Backend | Double-tap records the payment twice; concurrent pays exceed balance | Idempotency key; lock invoice row during recalc | Now |
| C5 Invoice edit after payment/sale doesn't recalc or reverse stock | Critical | Confirmed | Workflow | Edited total leaves `payment_status` stale; edited qty leaves stock wrong | Recalc payment status on edit; block/adjust stock-moving invoices | Now |
| C6 Assistant commits writes with no confirm + no kill switch | Critical | Confirmed | Assistant | LLM misreads a sentence and sets inventory / records a payment instantly | Confirm-gate all mutating tools; global assistant kill switch / read-only mode | Now |
| C7 "Never invent numbers" is prompt-only, unenforced | Critical | Likely | Assistant | 7B model emits or miscopies an unsourced figure a decision rests on | Post-check every number in the answer against tool outputs; refuse/flag if unmatched | Now |

### Critical finding cards (full fields)

**C1 — No idempotency or uniqueness on invoices and sales**
- Severity: Critical · Confidence: Confirmed · Area: Backend / Data model
- Where seen: `app/api/v1/endpoints/invoices.py` `sell()` and `create_invoice()` (client supplies `invoice_number`, no idempotency key); `app/models/invoice.py:16` — `invoice_number` is `index=True` but **not** `unique=True`.
- Why it matters: On a flaky Nigerian connection a submit that times out is retried; a slow "Sell" button is tapped twice. Nothing stops two identical invoices, and `/sell` draws stock on each.
- Likely failure mode: Duplicate invoice `INV-…-00123`; stock decremented twice; customer billed twice; COGS doubled.
- Business impact: Wrong stock, wrong revenue, wrong receivables, disputes with customers.
- Required fix: `UNIQUE` constraint on `invoice_number` (migration); accept a client-generated idempotency key on `/sell` and `POST /invoices`, store it, and return the original result on replay.
- Timing: Now · Test needed: Yes

**C2 — Sale/transfer allocation has no row locking (oversell race)**
- Severity: Critical · Confidence: Confirmed · Area: Backend
- Where seen: `app/services/stock.py` `_open_lots()` / `_draw_fifo()` / `allocate_for_sale()` — reads `quantity_remaining`, checks availability, then decrements, with no `with_for_update()` and default READ COMMITTED isolation.
- Why it matters: Two sales of the last units of a product run concurrently; both read "have 10", both pass the check, both decrement → remaining goes negative or a lot is double-sold.
- Likely failure mode: Physical stock oversold; lot `quantity_remaining` inconsistent with movements; a customer is promised stock that isn't there.
- Business impact: Failed fulfilment, emergency reorders, loss of trust in on-hand numbers.
- Required fix: Lock the candidate lots (`SELECT … FOR UPDATE`) inside the sale transaction, or serialize allocation per (product, warehouse); re-check availability after lock.
- Timing: Now · Test needed: Yes (two concurrent sells of the last units)

**C3 — Two sources of truth for stock**
- Severity: Critical · Confidence: Confirmed · Area: Data model
- Where seen: lot ledger `StockLot.quantity_remaining` / `StockMovement` (`stock.py`) vs scalar `Inventory.quantity_on_hand`, which is writable via generic CRUD `PATCH /inventory/{id}` (`router.py:168`, `write_role` defaults to STAFF) **and** via the assistant `_set_inventory` (`ai/tools.py:347`). `sell()` updates lots only and never touches `Inventory`.
- Why it matters: The two never reconcile. A direct inventory edit writes **no** `StockMovement`, so it's invisible to product history and lot traceability, and disagrees with `stock.on_hand`.
- Likely failure mode: Dashboard/reorder logic reads one number, the sale engine another; "we have 40" on one screen, "12" on another.
- Business impact: Reorder decisions on false stock; the whole traceability promise breaks for hand-edited items.
- Required fix: Make lots the single source; derive on-hand from lots everywhere; forbid direct `quantity_on_hand` edits — route corrections through `adjust_lot(reason=…)` which writes a movement. Remove Inventory from generic CRUD writes (or make it a read projection).
- Timing: Now · Test needed: Yes

**C4 — Payment recording is not idempotent; overpayment guard races**
- Severity: Critical · Confidence: Confirmed · Area: Backend
- Where seen: `app/services/receivables.py` `record_payment()` — reads `balance(inv)`, checks overpayment, inserts `Payment`, then `_recalc`; no idempotency key, no `FOR UPDATE` on the invoice.
- Why it matters: Double-tap on "Record payment" inserts two real payments. Two concurrent payments each see the same outstanding and both pass the overpayment check.
- Likely failure mode: Customer shown as having paid twice; `amount_paid` exceeds `total`; receivables understated.
- Business impact: Wrong debtor balances, wrong cash position, chasing customers who already paid (or missing ones who didn't).
- Required fix: Idempotency key per payment submit; lock the invoice row during recalc; re-validate outstanding under lock.
- Timing: Now · Test needed: Yes (double submit; concurrent partial payments summing past balance)

**C5 — Editing an invoice after payment/sale doesn't recalc balances or reverse stock**
- Severity: Critical · Confidence: Confirmed · Area: Workflow
- Where seen: `invoices.py` `update_invoice()` (role MANAGER) recomputes `total` but never calls `receivables._recalc`, and never adjusts stock; nothing blocks editing an invoice that already has payments or that moved stock via `/sell`.
- Why it matters: Raise a paid invoice's total → `payment_status` stays "PAID" while a real balance now exists (list shows a balance, status says PAID — contradiction). Change a sale's line quantity → stock was already drawn for the old quantity; ledger and invoice now disagree.
- Likely failure mode: Silent receivables corruption and stock drift, preserved forever in version history as "correct."
- Business impact: Misstated debtors and stock that look authoritative.
- Required fix: On edit, recompute `payment_status`/balance from payments; block editing stock-moving invoices (or post a compensating stock adjustment with reason); disallow line edits once payments exist — require credit-note/void instead.
- Timing: Now · Test needed: Yes

**C6 — Assistant executes financial/stock writes with no confirmation and no kill switch; read-tool role gates ignored**
- Severity: Critical · Confidence: Confirmed · Area: Assistant
- Where seen: `ai/assistant.py` `ask()` runs `execute_tool` inline; each mutating handler `db.commit()`s immediately (`_set_inventory`, `_record_payment`, `_set_product_cost`, `_set_product_price`, `_create_*`). `ai/tools.py` `execute_tool()` checks `role_at_least` **only when `tool.mutating`** — so MANAGER-only *read* tools (`get_payables`, `get_cash_flow`, `get_tax_estimate`) are callable by any role through the assistant. No global disable/read-only flag exists.
- Why it matters: A shop owner types "Musa took 5 timing belts, paid 200k" and the model may record a payment and set inventory — committed, no preview. And a STAFF user can pull payables/tax via chat despite the MANAGER gate on those screens.
- Likely failure mode: Wrong payment/stock write from a misparse; sensitive financial data leaked to lower roles; no way to stop it fast.
- Business impact: Corrupted records authored by an LLM; permission model bypassed; no emergency stop.
- Required fix: (a) A settings-backed kill switch / "assistant read-only" mode checked in `execute_tool`; (b) mutating tools return a *proposed action* that a human confirms in the UI before a second, explicit execute call; (c) enforce `min_role` for **all** tools, not just mutating ones.
- Timing: Now · Test needed: Yes

**C7 — Provenance is a prompt instruction, not an enforced guarantee**
- Severity: Critical · Confidence: Likely · Area: Assistant
- Where seen: `ai/assistant.py` `SYSTEM_PROMPT` ("You NEVER invent … numbers") and `_plain_text()` (strips markdown only). No code verifies the numbers in `result.answer` came from a tool result. Default provider can be a local `qwen2.5:7b`.
- Why it matters: The product's core promise ("the LLM never invents numbers") rests entirely on a small model obeying an instruction and copying digits exactly. Small models miscopy and interpolate.
- Likely failure mode: An answer states ₦3,120,000 where the tool said ₦3,012,000, or invents a figure when no tool ran; the owner acts on it.
- Business impact: A decision made on a number the system swears is real but isn't.
- Required fix: Extract numeric tokens from the answer and require each to match a value present in the tool results (within rounding); otherwise strip/flag it and append "figure not verified." Log any mismatch.
- Timing: Now · Test needed: Yes

---

## 3. High-priority issues table

| Issue | Sev | Conf | Area | Operational risk | Fix | Timing |
|---|---|---|---|---|---|---|
| H1 Hard delete of core entities | High | Confirmed | Data model | `DELETE /products|customers|suppliers|warehouses/{id}` (`crud.py` `delete_item`, `db.delete`) destroys records referenced by invoices/lots → FK error or data loss | Soft-delete/archive flag; forbid delete when references exist | Now |
| H2 `min_role` ignored for read tools | High | Confirmed | Assistant | Financial data (payables/cash/tax) leaks to any role via chat | Enforce role for all tools (part of C6) | Now |
| H3 Assistant mutation audit lacks entity_id/old→new | High | Confirmed | Assistant | Can't reconstruct what the AI changed; summary string only (`execute_tool` audit.record) | Log entity_type/id + old/new per AI write | Next |
| H4 Expenses (tax base) freely editable/deletable | High | Confirmed | Reporting | Generic CRUD on `Expense` (STAFF write, MANAGER delete) silently changes tax owed | Restrict role; audit reason; lock closed periods | Next |
| H5 No duplicate-submit / double-click guard on any POST | High | Confirmed | Frontend/Backend | Retries and double-taps create duplicates system-wide | Idempotency keys (C1/C4) + disable button while pending | Now |
| H6 Generic PATCH can set sensitive columns | High | Likely | Backend | If `credit_limit`, `data_origin`, `reliability_score` are in update schemas, any STAFF can change them unaudited-by-reason | Whitelist editable fields per resource; gate sensitive ones | Next |
| H7 Void payment captures no reason, weak actor guarantee | High | Confirmed | Workflow | `void_payment` flips status with no reason; reversals untraceable | Require reason; ensure actor/source recorded | Next |
| H8 Two parallel "make an invoice" paths | High | Confirmed | Workflow | `create_invoice` bills without moving stock; `sell` moves stock — operator confusion, un-fulfilled invoices | Make `/sell` the only path for stock items; label the other clearly | Next |
| H9 Actor/source not guaranteed on every write | Medium | Likely | Backend | `db.info` actor set in `get_current_user`; a write path not depending on it logs no actor; only assistant sets SOURCE | Set actor+source in one middleware for all authed requests | Next |

---

## 4. Backend enforcement requirements (must hold even if the UI looks correct)

1. **Uniqueness**: `invoice_number` unique; payment idempotency keys unique.
2. **Idempotency**: `/sell`, `POST /invoices`, `record_payment` replay-safe via a stored key.
3. **Locking**: lot rows locked during sale/transfer/adjust; invoice row locked during payment recalc.
4. **Single stock truth**: on-hand always derived from lots; `quantity_on_hand` never directly writable.
5. **Transactional integrity**: sale = invoice + lines + movements + version in one transaction, all-or-nothing (already mostly true in `sell`; keep it).
6. **Immutability where it matters**: once an invoice has a confirmed payment, its financial fields are locked; corrections go through void + credit note, never in-place edit.
7. **Payment status is always derived** from confirmed payments (single writer = `receivables._recalc`); anything that changes an invoice total must re-derive it.
8. **Role enforced server-side for every tool and endpoint** (not only mutating tools; not only the UI).
9. **Audit captures** actor, timestamp, action, entity, old, new, reason, source — including assistant writes (currently summary-only).
10. **Assistant writes are gated**: kill switch honored server-side; mutating tools require an explicit confirmed second call.
11. **Hard delete forbidden** on entities with financial/stock history; soft-delete instead.
12. **Numeric provenance check** on assistant answers before they're returned.

---

## 5. Immediate test cases to add (highest-risk failures)

1. Two concurrent `/sell` of the last N units → total drawn never exceeds stock; one fails cleanly (C2).
2. Same `/sell` submitted twice with one idempotency key → exactly one invoice, one stock draw (C1/H5).
3. `record_payment` submitted twice → one payment; `amount_paid` correct (C4).
4. Two concurrent partial payments summing above balance → second rejected under lock (C4).
5. Duplicate `invoice_number` insert → rejected by constraint (C1).
6. Edit a fully-paid invoice's total upward → `payment_status` becomes PARTIAL/UNPAID and balance is correct (C5).
7. Edit a `/sell` invoice's line quantity → either blocked or a compensating stock movement exists; ledger matches invoice (C5).
8. Direct `PATCH /inventory` of `quantity_on_hand` → rejected (or writes a movement); `stock.on_hand` and Inventory never diverge (C3).
9. STAFF user asks the assistant for payables/tax → refused by role (C6/H2).
10. Assistant told "record a ₦200k payment" → returns a proposal requiring confirmation, writes nothing until confirmed; kill switch on → refuses (C6).
11. Assistant answer contains a number not present in any tool result → flagged/stripped (C7).
12. `DELETE /products/{id}` for a product with invoice lines → rejected, not cascaded (H1).

---

## 6. Things to simplify, pause, or remove

- **Pause assistant write tools** (`set_inventory`, `record_payment`, `set_product_cost`, `set_product_price`, `create_*`) until confirmation + kill switch + provenance check exist. Ship the assistant **read-only** first.
- **Remove `Inventory` from generic write CRUD** (no direct `quantity_on_hand` edits). Corrections via `adjust_lot(reason=…)` only.
- **Pause the plain `create_invoice` path for stock items** — one blessed way to sell (`/sell`) reduces "phantom invoice, no stock moved" confusion.
- **Remove hard delete** from the generic router for products/customers/suppliers/warehouses; archive instead.
- Don't add more assistant autonomy, more forecasting surfaces, or the cloud migration's multi-user concurrency **until C1–C6 land** — more users is exactly what turns these races from rare to daily.

---

## 7. Recommended implementation order

1. `invoice_number` unique + idempotency keys on `/sell`, `POST /invoices`, `record_payment` (C1, C4, H5).
2. Row locking on lot allocation and invoice payment recalc (C2, C4).
3. Assistant → read-only mode + kill switch + enforce role on all tools (C6, H2). This is small and removes a whole class of risk immediately.
4. Single stock truth: derive on-hand from lots; block direct `quantity_on_hand` writes (C3).
5. Edit-after-payment guards + payment-status re-derivation on any total change (C5).
6. Numeric provenance check on assistant answers (C7).
7. Soft-delete for core entities (H1); assistant confirm-gate for writes (C6b); assistant write-audit with old/new (H3).
8. Expense/period controls, void reasons, field whitelists, actor/source middleware (H4, H6, H7, H9).

---

## Final sections

**1. Critical before live use**: C1 uniqueness+idempotency; C2 lot locking; C3 one stock truth; C4 payment idempotency+lock; C5 edit-after-payment guards; C6 assistant read-only/kill-switch/role-for-all-tools. Until these exist, every extra concurrent user multiplies the risk.

**2. Highest-value next fixes**: C7 provenance enforcement; H1 soft-delete; H3 assistant write-audit; H8 one selling path; H4 expense/period controls.

**3. Backend rules that must exist even if the UI looks correct**: see Section 4 — unique invoice numbers, idempotency, locking, single stock source, derived payment status, immutable-after-payment, server-side role for every tool, full audit incl. AI, hard-delete ban, numeric provenance check. The UI's disabled buttons and confirmations are convenience, not guarantees.

**4. Missing tests that expose the riskiest failures**: see Section 5 — concurrency (double-sell, double-pay), idempotency replay, edit-after-payment recalculation, inventory-vs-ledger divergence, assistant role/confirm/kill-switch, assistant numeric provenance, delete referential integrity.

**5. Things not to build yet**: cloud multi-user rollout, more assistant autonomy/automation, additional forecasting/analytics surfaces, any new feature that adds concurrent writers — all should wait until C1–C6 are in.

**6. Minimum safe operating mode (if full controls aren't ready)**:
- Assistant in **read-only** (all mutating tools disabled via the kill switch); it answers, it never writes.
- **One** person recording sales/payments at a time; treat concurrency as unsafe until locking lands.
- Add the **`invoice_number` unique constraint now** (small migration) even before full idempotency — it stops the worst duplicates.
- **No editing** invoices after a payment is recorded — void and re-issue instead.
- **No direct inventory edits** — receive/sell/adjust only, so every change writes a movement.
- Disable hard-delete of products/customers/suppliers.
- Reconcile lot on-hand vs `Inventory.quantity_on_hand` once before trusting either.

---

*Cannot verify from provided code (call these out honestly):* whether the dashboard/reorder logic reads `Inventory.quantity_on_hand` or the lot ledger (both exist and can diverge — C3); whether the frontend disables submit buttons while a POST is in flight; whether assistant conversation history is isolated per user/session (memory-bleed / mixed-context risk — check `models/assistant.py` and the assistant endpoint); the DB isolation level in production. These need a targeted Section 3 (workflow) / Section 4 (file) pass.
