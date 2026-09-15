# Quant module — roadmap & status (revisit anytime)

_Last updated: 2026-09-16_

This is the plain-English map of the "quant" — the deterministic brain behind the
intelligence (Benfieg, the Action List). It never invents numbers; every figure
comes from your real data or the engines, tagged with where it came from.

---

## What "version" means (so it's not confusing)
- The spec documents in `docs/` are called **v4, v5, v6, v7**. Those are **drafts of
  the requirements**, not stages of the product. v7 is the newest and wins where
  they disagree. There is no "getting to v4" — it's one rulebook edited four times.
- What we are building is **version 1 (v1)** of the quant module. v1 is organised
  into three phases. **v2** is the set of advanced features the spec deliberately
  left for later.

---

## v1 — where we are (≈95% done)

**Done and live (all reachable through Benfieg + the Action List):**
- Demand forecasting for every product (steady, intermittent, lumpy), with a
  cold-start estimate for brand-new products from similar items in the same category.
- ABC classification (A/B/C by value) — A-items are protected with a higher
  service level automatically.
- Reorder recommendations: how much to order, safety stock (including how much the
  lead time varies), order-up-to level.
- Ranking by **money at risk** — the parts that cost you most to run out of come first.
- Budget-constrained purchase plan — "I have ₦X to restock, what should I buy?"
- Stockout risk simulation — per product and across the whole catalogue.
- Supplier scoring — who is most reliable, from reliability + real delivery times.
- Substitutes — cross-brand alternatives (a Turkey piston for a China one), and
  the system checks if an alternative is in stock before sounding the alarm.
- Speed: heavy maths is cached, so repeat views are near-instant.

**To finish v1 (small):**
1. **Landed cost** — waiting on your import/clearing expert's numbers. The
   placeholder is in place; see `docs/landed_cost_questions_for_expert.md`. Once you
   have the "total uplift %", we switch it on. _(Your action.)_
2. **Phase-3 hardening** — a formal alert lifecycle and a sign-off checklist.
   _(I can do this without you.)_

---

## v2 — advanced features (after v1 is finished)

Menu, most useful for an import auto-parts business first:

| Feature | What it does (plainly) | What I need from you | Priority |
|---|---|---|---|
| Seasonality / holidays | Knows demand rises before Sallah/Christmas, dips in the rainy season | Nothing — NG holidays are free, the rest is from your sales | **Do first** |
| Order-ahead planning | Plans purchases months ahead to cover long China/Turkey shipping | Nothing | **High** |
| Supplier-shock modelling | "What if Apapa closes / naira crashes / a supplier fails" | Rough likelihood (e.g. port delays ~2×/year) | **Valuable** |
| Kits / assembled items | Treats a kit as its sub-parts | Do you sell assembled kits? (yes/no) | Only if you sell kits |
| Tail-risk (CVaR) | Optimises against worst-case months, not just the average | Nothing | Low |
| Cross-product correlation | Models parts that sell together | Needs lots of history | Low (wait) |

**What you need to do for v2:**
1. Get the **landed-cost numbers** from your expert (finishes v1).
2. Tell me **whether you sell kits/assembled items**.
3. Give a **rough sense of supply disruptions** (how often port/FX/supplier trouble hits).

**Recommended order:** finish v1 hardening now → (when landed-cost arrives) start v2
with **seasonality + order-ahead planning** → then **supplier-shock**. Skip CVaR and
cross-product correlation until there's more sales history — effort without much
payoff yet.

**Out of scope by design (not skipped):** the spec itself pushes dynamic
multi-period optimisation, CVaR, cross-product correlation, weather/crop feeds, and
supplier common-shock to "future" — they are v2 candidates above, not v1 gaps.

---

## Open decisions waiting on you
- [ ] Landed-cost figures from the expert (finishes v1).
- [ ] Do you sell kits/assembled items? (drives whether we build BOMs in v2)
- [ ] Rough supply-disruption frequency (for supplier-shock in v2)
