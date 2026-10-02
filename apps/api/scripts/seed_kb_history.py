"""Seed the knowledgebase with the project's real development history.

Creates a single "Development Changelog" article whose version history mirrors the
actual git commit log — each version carries the real date and message of a change,
so the knowledgebase shows the true timeline of how the app was built.

Idempotent: if the article already exists, it does nothing. Safe to run on every
boot (see the Dockerfile).

The commit data below is the real `git log` of this repository, embedded here
because the production image may not ship the .git history.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.knowledge import KbArticle, KbArticleVersion
from app.models.user import User

ARTICLE_TITLE = "Development Changelog"

# (ISO timestamp, change message) — the real commit history, oldest first.
COMMITS: list[tuple[str, str]] = [
    ("2026-09-15T00:47:13", "Benfieg chat history + collapse duplicate suggestion notifications"),
    ("2026-09-15T01:03:05", "Quant: weekly->daily forecast bridge + golden harness"),
    ("2026-09-15T01:07:34", "Quant: lead-time statistics + variability in safety stock"),
    ("2026-09-15T01:19:12", "Wire the quant brain into the intelligence surfaces"),
    ("2026-09-15T01:40:02", "Embed the quant brain in Benfieg's analysis + per-product tools"),
    ("2026-09-15T10:53:45", "Quant: ABC-aware reorder service levels (A protected more than C)"),
    ("2026-09-15T10:57:50", "Quant: rank reorder by margin at risk, surfaced everywhere"),
    ("2026-09-15T11:06:57", "Quant Phase 2: daily inventory-policy Monte Carlo"),
    ("2026-09-15T12:46:40", "Quant: budget-constrained reorder plan, wired into Benfieg"),
    ("2026-09-15T23:11:56", "Quant: supplier scoring + landed cost, wired into Benfieg"),
    ("2026-09-15T23:17:22", "Quant: portfolio stockout simulation, wired into Benfieg"),
    ("2026-09-15T23:20:49", "Quant: golden files for the deterministic engine"),
    ("2026-09-16T00:07:58", "Quant: cache the heavy forecast/backtest maths for speed"),
    ("2026-09-16T00:10:13", "Quant: landed-cost placeholders + expert questions"),
    ("2026-09-16T00:18:10", "Quant: product substitutes (cross-brand alternatives)"),
    ("2026-09-16T00:26:57", "Quant: cold-start demand prior for new products"),
    ("2026-09-16T00:36:01", "Repurpose Suggestions tab as a plain reorder Action List"),
    ("2026-09-16T00:58:36", "Docs: quant roadmap + database hosting plan; cloud-DB ready"),
    ("2026-09-16T01:38:36", "Automatic, complete audit trail (traceability) into the database"),
    ("2026-09-16T02:33:27", "Money layer 1/3: payments & accounts receivable"),
    ("2026-09-16T02:38:28", "Money layer: Receivables page (frontend)"),
    ("2026-09-16T02:44:43", "Money layer 2-3/3: payables + cash flow"),
    ("2026-09-16T02:46:01", "Money layer: Cash Flow page (frontend)"),
    ("2026-09-16T11:46:50", "Link dashboard to features; show who's owing + customer modal"),
    ("2026-09-16T11:59:03", "Make invoices clickable inside the customer modal"),
    ("2026-09-16T12:12:24", "Track & show who recorded each payment on the invoice"),
    ("2026-09-16T12:27:59", "Payments carry bank-transfer traceability (txid, from/to)"),
    ("2026-09-16T12:31:51", "Tax area: VAT + company income tax estimate"),
    ("2026-09-17T00:51:00", "Supplier traceability backend: products/warehouses/shipments"),
    ("2026-09-17T00:52:24", "Fix customer lifetime revenue (populate the rollup)"),
    ("2026-09-17T00:58:49", "Admin user management: reset passwords, per-user activity, export"),
    ("2026-09-17T01:08:40", "Simulations rework: plain-language Auto / Manual / History"),
    ("2026-09-17T01:19:29", "Product history modal: searchable/filterable/sortable timeline"),
    ("2026-09-17T09:23:16", "Supplier detail screen + Benfieg get_supplier_trace tool"),
    ("2026-09-18T00:30:19", "Operational safety hardening: locking, idempotency, RBAC"),
    ("2026-09-18T00:30:28", "Frontend: idempotency-key plumbing, assistant confirm UI, Vitest"),
    ("2026-09-18T00:30:36", "Docs: operational audit + remediation reports"),
    ("2026-09-19T16:21:34", "Supplier CSV import + import templates"),
    ("2026-09-19T16:21:34", "Waybills: dispatch tracking linked to invoices"),
    ("2026-09-19T16:32:06", "Procurement: request lists -> order -> receive with transport cost"),
    ("2026-09-19T16:40:17", "Supplier cockpit: statement (owe/paid + receipts) and slow-movers"),
    ("2026-09-28T11:51:39", "SCM docs/currency, soft-delete, analytics, RBAC salesgirl + device binding"),
    ("2026-09-28T11:51:53", "Hosting prep: production Docker image, Render blueprint, runbook"),
    ("2026-09-28T12:06:12", "Durable object storage: Cloudflare R2 / S3 driver"),
    ("2026-09-28T13:31:15", "Bump Next.js to patched 15.5.26 (clears Vercel security gate)"),
    ("2026-09-28T13:40:52", "Accept plain/comma-separated CORS_ORIGINS from env"),
    ("2026-09-28T15:34:35", "Clean login page (no demo accounts) + allow changing login email"),
    ("2026-09-28T18:59:12", "Fix: clearing an optional field on edit now saves as empty"),
    ("2026-09-29T09:16:41", "Show product name on invoices instead of bare \"Product\""),
    ("2026-09-29T09:35:49", "Improve line mapping for invoice printing"),
    ("2026-09-29T09:36:31", "Record product name on sold invoice lines at sale time"),
    ("2026-09-29T10:05:45", "Add invoice void, customer returns, and customer-copy printing"),
    ("2026-09-29T10:22:13", "Make market-intelligence refresh resilient (fix NetworkError)"),
    ("2026-09-29T13:06:03", "Void a paid invoice refunds the customer (no negative balance)"),
    ("2026-10-02T13:00:21", "Add POS (Moniepoint) payment reconciliation"),
    ("2026-10-02T13:05:22", "Flag possible duplicate / anomalous POS charges"),
    ("2026-10-02T13:06:49", "Flag unusually large POS charges on the reconcile screen"),
    ("2026-10-02T13:16:00", "Market refresh: report which source failed, not a blanket error"),
    ("2026-10-02T13:26:19", "Add GIS user-location tracking + live Team Map"),
    ("2026-10-02T13:40:46", "Add knowledgebase: versioned articles + live app-wide change feed"),
    ("2026-10-02T13:52:13", "Add market-data source connectivity diagnostics"),
]


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def _body(commits: list[tuple[str, str]]) -> str:
    lines = ["# Development Changelog",
             "",
             f"A record of how this app was built — {len(commits)} tracked changes "
             f"from {commits[0][0][:10]} to {commits[-1][0][:10]}.",
             ""]
    current_day = None
    for iso, msg in reversed(commits):  # newest first in the readable body
        day = iso[:10]
        if day != current_day:
            lines.append(f"\n## {day}")
            current_day = day
        lines.append(f"- {iso[11:16]} — {msg}")
    return "\n".join(lines)


def seed(db) -> str:
    existing = db.scalar(select(KbArticle).where(KbArticle.title == ARTICLE_TITLE))
    if existing is not None:
        return "exists"

    author = db.scalar(select(User).order_by(User.id)) if db.scalar(select(User.id)) else None
    author_id = author.id if author else None

    first_dt, last_dt = _dt(COMMITS[0][0]), _dt(COMMITS[-1][0])
    art = KbArticle(
        title=ARTICLE_TITLE, category="Build History", body=_body(COMMITS),
        version_no=len(COMMITS), created_by_user_id=author_id, updated_by_user_id=author_id,
    )
    art.created_at = first_dt
    art.updated_at = last_dt
    db.add(art)
    db.flush()

    for i, (iso, msg) in enumerate(COMMITS, start=1):
        v = KbArticleVersion(
            article_id=art.id, version_no=i, title=ARTICLE_TITLE,
            body=msg, change_note=msg, changed_by_user_id=author_id,
        )
        v.created_at = _dt(iso)
        db.add(v)

    db.commit()
    return f"seeded ({len(COMMITS)} versions)"


def main() -> None:
    db = SessionLocal()
    try:
        print("seed_kb_history:", seed(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
