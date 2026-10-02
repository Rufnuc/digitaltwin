"""Seed the knowledgebase with (1) the project's real development history as a
detailed, dated changelog, and (2) how-to guides for using the app.

Idempotent and refreshable: articles created by the seed are tagged with
CONTENT_VERSION. On boot the seed recreates its own articles when the content
version changes, but never touches articles a human created or edited (seed_tag
NULL). Commit dates/messages are the real git history of this repository.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.knowledge import KbArticle, KbArticleVersion
from app.models.user import User

CONTENT_VERSION = "3"
CHANGELOG_TITLE = "Development Changelog"

# (ISO timestamp, short title, detailed description) — the real commit history.
COMMITS: list[tuple[str, str, str]] = [
    ("2026-09-15T00:47:13", "Benfieg chat history + fewer duplicate alerts",
     "Added saved chat history for the Benfieg AI assistant so past conversations "
     "reopen with their answers, and collapsed duplicate suggestion notifications."),
    ("2026-09-15T01:03:05", "Quant: weekly→daily forecast bridge",
     "Added the forecasting bridge that turns weekly demand into daily figures, plus a "
     "golden test harness to keep results stable."),
    ("2026-09-15T01:07:34", "Quant: lead-time statistics in safety stock",
     "Added lead-time averages and variability to the safety-stock maths so reorder "
     "levels account for how unpredictable supply is."),
    ("2026-09-15T01:19:12", "Wire the quant brain into the app",
     "Connected the inventory maths to the dashboards and intelligence screens."),
    ("2026-09-15T01:40:02", "Quant inside Benfieg + per-product tools",
     "Embedded the quant engine in Benfieg's analysis and added per-product tools."),
    ("2026-09-15T10:53:45", "Quant: ABC-aware service levels",
     "Added ABC classification so your most valuable items (class A) are protected with "
     "higher stock service levels than low-value (class C) items."),
    ("2026-09-15T10:57:50", "Quant: rank reorder by money at risk",
     "Changed reorder ranking to sort by the margin (money) at risk, so the most "
     "financially important restocks surface first."),
    ("2026-09-15T11:06:57", "Quant Phase 2: Monte-Carlo inventory policy",
     "Added a daily simulation that stress-tests inventory policy against random demand."),
    ("2026-09-15T12:46:40", "Quant: budget-constrained reorder plan",
     "Added a reorder plan that fits within a cash budget, wired into Benfieg."),
    ("2026-09-15T23:11:56", "Quant: supplier scoring + landed cost",
     "Added supplier scoring and landed-cost estimation."),
    ("2026-09-15T23:17:22", "Quant: portfolio stockout simulation",
     "Added a whole-catalogue stockout risk simulation."),
    ("2026-09-15T23:20:49", "Quant: golden test files",
     "Added locked reference results so the engine's numbers can't drift unnoticed."),
    ("2026-09-16T00:07:58", "Quant: cache heavy maths for speed",
     "Cached the expensive forecast/backtest calculations so pages load faster."),
    ("2026-09-16T00:10:13", "Quant: landed-cost placeholders",
     "Added clearly-marked placeholder landed-cost percentages (freight, duty, levies) "
     "and the questions to confirm with an import expert — not used in decisions until set."),
    ("2026-09-16T00:18:10", "Quant: product substitutes",
     "Added cross-brand alternative products so substitutes can be suggested."),
    ("2026-09-16T00:26:57", "Quant: cold-start demand for new products",
     "Added a low-confidence demand estimate for brand-new products using similar items."),
    ("2026-09-16T00:36:01", "Changed Suggestions into a reorder Action List",
     "Repurposed the Suggestions tab into a plain, actionable reorder list."),
    ("2026-09-16T00:58:36", "Docs + cloud-DB readiness",
     "Documented the quant roadmap and database hosting plan and made the app ready to "
     "run on a cloud database."),
    ("2026-09-16T01:38:36", "Automatic audit trail",
     "Added a complete, automatic audit trail recording every change in the database — "
     "the foundation of the activity log and the knowledgebase change feed."),
    ("2026-09-16T02:33:27", "Money: payments & receivables",
     "Added recording customer payments and tracking who owes what."),
    ("2026-09-16T02:38:28", "Money: Receivables page",
     "Added the Receivables screen."),
    ("2026-09-16T02:44:43", "Money: payables + cash flow",
     "Added supplier payables and a cash-flow view."),
    ("2026-09-16T02:46:01", "Money: Cash Flow page",
     "Added the Cash Flow screen."),
    ("2026-09-16T11:46:50", "Dashboard links + who's owing",
     "Linked the dashboard to features and surfaced outstanding balances with a "
     "customer modal."),
    ("2026-09-16T11:59:03", "Record payment inside customer modal",
     "Made invoices clickable within the customer modal to record payment inline."),
    ("2026-09-16T12:12:24", "Show who recorded each payment",
     "Each payment now records and shows which user entered it."),
    ("2026-09-16T12:27:59", "Bank-transfer traceability on payments",
     "Added transaction id and from/to account details to payments for traceability."),
    ("2026-09-16T12:31:51", "Tax: VAT + company income tax estimate",
     "Added a Nigerian VAT and company-income-tax estimate (guidance, not advice)."),
    ("2026-09-17T00:51:00", "Supplier traceability backend",
     "Added the backend linking products, warehouses, shipments and supplier payments."),
    ("2026-09-17T00:52:24", "Fix: customer lifetime revenue",
     "Fixed lifetime revenue so each customer's rollup is populated correctly."),
    ("2026-09-17T00:58:49", "Admin user management",
     "Added resetting passwords, per-user activity and log export; made OWNER the top role."),
    ("2026-09-17T01:08:40", "Simulations rework",
     "Reworked simulations into plain-language Auto / Manual / History modes."),
    ("2026-09-17T01:19:29", "Product history timeline",
     "Added a searchable, filterable, sortable product-history modal."),
    ("2026-09-17T09:23:16", "Supplier detail screen",
     "Added a supplier detail screen and a Benfieg tool to trace a supplier."),
    ("2026-09-18T00:30:19", "Operational safety hardening (backend)",
     "Hardened the backend: row locking, idempotency keys, confirm-gating and stricter "
     "role checks to prevent double-submits and unsafe actions."),
    ("2026-09-18T00:30:28", "Safety hardening (frontend)",
     "Added idempotency plumbing, an assistant confirmation UI and frontend tests."),
    ("2026-09-18T00:30:36", "Docs: operational audit",
     "Added the operational audit and remediation reports."),
    ("2026-09-19T16:21:34", "Supplier CSV import",
     "Added importing suppliers from CSV with downloadable templates."),
    ("2026-09-19T16:21:34", "Waybills: dispatch tracking",
     "Added waybills to track dispatch against invoices."),
    ("2026-09-19T16:32:06", "Procurement flow",
     "Added request lists → order → receive, including transport cost."),
    ("2026-09-19T16:40:17", "Supplier cockpit",
     "Added a supplier statement (owed/paid with receipts) and slow-mover view."),
    ("2026-09-28T11:51:39", "SCM, soft-delete, analytics, salesgirl role, device binding",
     "Added supply-chain docs/currency, soft-delete (records are hidden, never destroyed), "
     "more analytics, the restricted SALESGIRL front-desk role, and device binding."),
    ("2026-09-28T11:51:53", "Hosting prep",
     "Added the production Docker image, Render blueprint, config hardening and a runbook."),
    ("2026-09-28T12:06:12", "Durable file storage (R2/S3)",
     "Added a Cloudflare R2 / S3 driver so uploaded documents persist."),
    ("2026-09-28T13:31:15", "Security: patch Next.js",
     "Upgraded Next.js to the patched 15.5.26 to clear a security gate."),
    ("2026-09-28T13:40:52", "Config: flexible CORS",
     "Accept a plain or comma-separated website address list from the environment."),
    ("2026-09-28T15:34:35", "Removed demo accounts from login",
     "Cleaned up the login page — REMOVED the demo/sample accounts — and allowed changing "
     "the login email."),
    ("2026-09-28T18:59:12", "Fix: clearing an optional field saves empty",
     "Fixed editing so clearing an optional field now saves as empty instead of keeping "
     "the old value."),
    ("2026-09-29T09:16:41", "Fix: show product name on invoices",
     "Invoices showed a bare 'Product' instead of the item name; now the linked product's "
     "name is shown (and existing invoices are fixed on read)."),
    ("2026-09-29T09:35:49", "Improve invoice-print line mapping",
     "Tidied how invoice lines are rendered for printing."),
    ("2026-09-29T09:36:31", "Store product name on sold lines",
     "Sales now store the product name on each line so the name shows everywhere, "
     "including the printed invoice and version history."),
    ("2026-09-29T10:05:45", "Invoice void, customer returns, customer-copy print",
     "Added voiding an invoice, processing customer returns, and a customer invoice copy "
     "that omits the internal version history."),
    ("2026-09-29T10:22:13", "Fix: resilient Market Intelligence refresh",
     "Made the market-data refresh fetch sources concurrently with short timeouts so it "
     "no longer hangs and shows a NetworkError."),
    ("2026-09-29T13:06:03", "Void a paid invoice now refunds the customer",
     "Changed void so a paid invoice refunds the customer (its payments are voided) and "
     "settles at zero — no more negative balance; negative balances now read 'Refund due'."),
    ("2026-10-02T13:00:21", "POS (Moniepoint) payment reconciliation",
     "Added linking card-terminal payments to invoices: 'expect' a payment / push to the "
     "terminal, automatic matching (full and partial), and an Unmatched screen."),
    ("2026-10-02T13:05:22", "POS: flag possible duplicate charges",
     "Flagged unmatched POS transactions that look like a double charge (same amount + "
     "terminal within minutes)."),
    ("2026-10-02T13:06:49", "POS: flag unusually large charges",
     "Flagged POS amounts far above your normal sales as possible mistakes/fraud."),
    ("2026-10-02T13:16:00", "Market refresh: per-source errors",
     "Changed refresh to report exactly which data source failed and why, instead of a "
     "blanket error."),
    ("2026-10-02T13:26:19", "GIS user tracking + Team Map",
     "Added tracking each logged-in user's location on company devices, a live Team Map, "
     "and 'location changed' entries in the activity log."),
    ("2026-10-02T13:40:46", "Knowledgebase: versioned articles + change feed",
     "Added the knowledgebase: managers write versioned articles and see a live feed of "
     "every change across the app."),
    ("2026-10-02T13:52:13", "Market: source connectivity diagnostics",
     "Added a 'Test data sources' button that checks, from the server, whether each "
     "market-data source is reachable."),
    ("2026-10-02T15:00:00", "GIS addresses + how-to guides + detailed changelog",
     "Changed the Team Map and activity log to show a readable address (reverse-geocoded) "
     "instead of only coordinates; added how-to guides to the knowledgebase; and expanded "
     "this changelog with a detailed description of every change."),
]

# How-to guides (title, category, body). Each is seeded as a single-version article.
GUIDES: list[tuple[str, str, str]] = [
    ("How to record a sale", "How-to",
     "# Record a sale\n\n"
     "1. Go to **New Sale** (or Invoices → New Sale).\n"
     "2. Choose the customer (or type a new name to create one on the fly) and the sale "
     "location (Home/Office).\n"
     "3. Add each item: pick the product, quantity and unit price. Stock on hand shows "
     "beside each line.\n"
     "4. Add tax/discount/shipping if any, then **Record sale & draw stock**.\n\n"
     "Stock is drawn from the warehouse (oldest batch first) and every unit is traced to "
     "the buyer."),
    ("How to take a POS (Moniepoint) payment", "How-to",
     "# Take a POS payment\n\n"
     "1. Open the invoice and click **Charge on POS (Moniepoint)**.\n"
     "2. Enter the amount (full or part). Optionally enter the terminal ID and **Push to "
     "terminal** to make it pop up on the machine; or use **Expect only** and charge on the "
     "terminal directly.\n"
     "3. When the customer pays, the transaction links to the invoice automatically.\n\n"
     "Anything that doesn't link appears under **POS Payments** with suggestions — one tap "
     "to assign. Possible duplicates and unusually large charges are flagged."),
    ("How to void an invoice (and refund)", "How-to",
     "# Void an invoice\n\n"
     "1. Open the invoice and click **Void invoice** (managers and above).\n"
     "2. Enter a reason.\n\n"
     "Voiding returns the stock to your warehouse, **refunds any money the customer paid**, "
     "and removes the invoice from sales and receivables. The record is kept and marked "
     "VOID — it is never deleted."),
    ("How to process a customer return", "How-to",
     "# Process a return\n\n"
     "1. Open the invoice and click **Return items**.\n"
     "2. Choose where to put the returned goods, enter the quantity returned per item, and "
     "a reason.\n\n"
     "The goods go back into stock and the invoice (and what the customer owes) is reduced. "
     "If the customer had already paid, the balance shows **Refund due**."),
    ("How to print an invoice for a customer", "How-to",
     "# Print an invoice\n\n"
     "Open the invoice and choose **Print for customer** (clean copy, no internal edit "
     "history) or **Print (with history)** for your own records."),
    ("How to use the Team Map", "How-to",
     "# Team Map\n\n"
     "Managers can see where each team member was last seen (as an address) while logged "
     "in on a company device, under **Team Map**. Click a person to see their recent "
     "movement trail. Location changes are also recorded in the **Activity Log**.\n\n"
     "Note: a web app can only read location while it is open and after the device grants "
     "permission once."),
    ("How to use the Knowledgebase", "How-to",
     "# Knowledgebase\n\n"
     "Under **Knowledgebase** (managers only):\n\n"
     "- **Search** or browse by topic in the left sidebar; filter by **#tags**.\n"
     "- **Write** an article with the **+ New article** button — headings, bold, lists, "
     "links and **images** are supported (use **Insert image**). Use **Preview** to check it.\n"
     "- Every save adds a numbered **version**; open **History** on an article to see what "
     "changed and when.\n"
     "- **★ Feature** important articles so they pin to the top, and tag them for easy "
     "finding.\n"
     "- Readers can mark an article **helpful** so you know which guides work.\n\n"
     "For a full log of every change across the whole app, see the **Activity Log**."),
    ("How to refresh Market Intelligence", "How-to",
     "# Market Intelligence\n\n"
     "Click **Refresh from sources** to pull Nigerian economic indicators, FX and business "
     "news (kept with their source and date). If it reports a problem, click **Test data "
     "sources** to see which source your server can and can't reach."),
]


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def _changelog_body() -> str:
    lines = [f"# {CHANGELOG_TITLE}", "",
             f"How this app was built — {len(COMMITS)} tracked changes from "
             f"{COMMITS[0][0][:10]} to {COMMITS[-1][0][:10]}.", ""]
    day = None
    for iso, title, detail in reversed(COMMITS):  # newest first
        d = iso[:10]
        if d != day:
            lines.append(f"\n## {d}")
            day = d
        lines.append(f"- **{iso[11:16]} — {title}**  \n  {detail}")
    return "\n".join(lines)


def _upsert(db, *, title: str, category: str, body: str, author_id: int | None,
            versions: list[tuple[str | None, str, str]]) -> str:
    """Create or refresh a seeded article. Never clobbers a human article (seed_tag NULL)."""
    existing = db.scalar(select(KbArticle).where(KbArticle.title == title))
    if existing is not None:
        if existing.seed_tag is None:
            return "skip-human"
        if existing.seed_tag == CONTENT_VERSION:
            return "current"
        db.delete(existing)  # older seed version → rebuild
        db.flush()

    art = KbArticle(title=title, category=category, body=body, seed_tag=CONTENT_VERSION,
                    version_no=len(versions) or 1,
                    created_by_user_id=author_id, updated_by_user_id=author_id)
    db.add(art)
    db.flush()
    for i, (iso, note, vbody) in enumerate(versions, start=1):
        v = KbArticleVersion(article_id=art.id, version_no=i, title=title, body=vbody,
                             change_note=note, changed_by_user_id=author_id)
        if iso:
            v.created_at = _dt(iso)
        db.add(v)
    dated = [iso for iso, _, _ in versions if iso]
    if dated:
        art.created_at = _dt(dated[0])
        art.updated_at = _dt(dated[-1])
    return "seeded"


def seed(db) -> dict:
    author = db.scalar(select(User).order_by(User.id))
    author_id = author.id if author else None

    results: dict[str, str] = {}
    results[CHANGELOG_TITLE] = _upsert(
        db, title=CHANGELOG_TITLE, category="Build History", body=_changelog_body(),
        author_id=author_id,
        versions=[(iso, title, detail) for iso, title, detail in COMMITS],
    )
    for title, category, body in GUIDES:
        results[title] = _upsert(db, title=title, category=category, body=body,
                                 author_id=author_id, versions=[(None, "created", body)])
    db.commit()
    return results


def main() -> None:
    db = SessionLocal()
    try:
        res = seed(db)
        print("seed_kb_history:", res)
    finally:
        db.close()


if __name__ == "__main__":
    main()
