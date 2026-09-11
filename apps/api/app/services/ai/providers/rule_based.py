"""Deterministic offline assistant router (default provider).

This is NOT a language model — it is a transparent rule-based intent router that
maps common business questions to the appropriate tool(s), then composes an
answer *entirely from the tool outputs*. It exists so the assistant is fully
functional and testable with zero external dependencies or API keys, and so the
"never invent numbers" guarantee is trivially true: every figure printed here is
read straight from a tool result.

For genuine open-ended natural language, configure the Anthropic provider
(AI_PROVIDER=anthropic + AI_API_KEY); the same tools back both.
"""
from __future__ import annotations

import re

from app.services.ai.tools import ToolDef
from app.services.ai.types import AssistantResult, Executor, ToolCall

_PRICE_RE = re.compile(
    r"(raise|increase|put up|hike|lower|reduce|cut|drop|decrease|change)\D{0,20}?(\d+(?:\.\d+)?)\s*%",
    re.I,
)
_DOWN = ("lower", "reduce", "cut", "drop", "decrease")


def _money(v) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)


def _pct(v) -> str:
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(v)


class RuleBasedProvider:
    name = "rule_based"

    def answer(
        self, question: str, tools: list[ToolDef], execute: Executor, system: str
    ) -> AssistantResult:
        q = question.lower()
        calls: list[ToolCall] = []

        def call(name: str, args: dict | None = None) -> dict:
            res = execute(name, args or {})
            calls.append(ToolCall(name=name, args=args or {}, result=res))
            return res

        # --- Price / what-if scenario ---
        m = _PRICE_RE.search(q)
        if m and ("price" in q or "pricing" in q):
            pct = float(m.group(2))
            if any(w in q for w in _DOWN):
                pct = -pct
            if "monte" in q or "uncertain" in q or "risk" in q and "simulat" in q:
                res = call("run_monte_carlo", {"price_mean": pct, "price_std": max(abs(pct) / 2, 2)})
                answer = self._explain_mc(pct, res)
            else:
                res = call("run_scenario",
                           {"scenario_type": "price_change", "change_percent": pct})
                answer = self._explain_scenario(pct, res)
            return AssistantResult(answer=answer, tool_calls=calls, provider=self.name)

        # --- Compare price strategies ---
        if "compare" in q and ("price" in q or "strateg" in q):
            res = call("compare_price_strategies", {})
            return AssistantResult(answer=self._explain_compare(res), tool_calls=calls,
                                   provider=self.name)

        # --- What matters most / sensitivity ---
        if "matter" in q or "sensitiv" in q or "biggest lever" in q:
            res = call("run_sensitivity", {})
            return AssistantResult(answer=self._explain_sensitivity(res), tool_calls=calls,
                                   provider=self.name)

        # --- Risks ---
        if "risk" in q or "threat" in q or "worried" in q:
            cust = call("get_customer_intelligence")
            dq = call("get_data_quality")
            return AssistantResult(answer=self._explain_risks(cust, dq), tool_calls=calls,
                                   provider=self.name)

        # --- Churn / at-risk customers ---
        if "churn" in q or ("customer" in q and ("risk" in q or "leaving" in q or "lost" in q)):
            res = call("get_customer_intelligence")
            return AssistantResult(answer=self._explain_churn(res), tool_calls=calls,
                                   provider=self.name)

        # --- Customers (top / profitable) ---
        if "customer" in q:
            res = call("get_customer_intelligence")
            return AssistantResult(answer=self._explain_customers(res), tool_calls=calls,
                                   provider=self.name)

        # --- Products ---
        if "product" in q or "best sell" in q or "sell" in q or "stock" in q:
            res = call("get_product_intelligence")
            return AssistantResult(answer=self._explain_products(res), tool_calls=calls,
                                   provider=self.name)

        # --- Suppliers ---
        if "supplier" in q or "vendor" in q:
            res = call("get_supplier_intelligence")
            return AssistantResult(answer=self._explain_suppliers(res), tool_calls=calls,
                                   provider=self.name)

        # --- Data quality ---
        if "data quality" in q or "quality" in q or "clean" in q:
            res = call("get_data_quality")
            return AssistantResult(answer=self._explain_dq(res), tool_calls=calls,
                                   provider=self.name)

        # --- Default: business health ---
        res = call("get_business_summary")
        return AssistantResult(answer=self._explain_summary(res), tool_calls=calls,
                               provider=self.name)

    # ---- explanation templates (numbers taken verbatim from tool output) ----
    def _explain_summary(self, r: dict) -> str:
        k = r.get("kpis", {})
        demo = " (Note: this workspace currently holds DEMO data only.)" if r.get(
            "data_status", {}).get("is_demo_only") else ""
        return (
            f"Revenue is {_money(k.get('revenue'))} with a gross margin of "
            f"{_pct(k.get('gross_margin'))} and net profit of {_money(k.get('net_profit'))} "
            f"(net margin {_pct(k.get('net_margin'))}). There are {k.get('orders')} orders across "
            f"{k.get('active_customers')} active customers, and inventory is valued at "
            f"{_money(k.get('inventory_value'))}.{demo}"
        )

    def _explain_scenario(self, pct: float, r: dict) -> str:
        if r.get("error"):
            return f"I couldn't run that scenario: {r['error']}"
        by = {x["metric"]: x for x in r.get("results", [])}
        rev, gp, un = by.get("revenue", {}), by.get("gross_profit", {}), by.get("units", {})
        e = r.get("assumptions", {}).get("price_elasticity")
        warn = (" " + " ".join(r["warnings"])) if r.get("warnings") else ""
        return (
            f"A {pct:+g}% price change (assuming price elasticity {e}) is projected to move "
            f"revenue from {_money(rev.get('baseline'))} to {_money(rev.get('scenario'))} "
            f"({rev.get('change_percent'):+.1f}%) and gross profit from "
            f"{_money(gp.get('baseline'))} to {_money(gp.get('scenario'))} "
            f"({gp.get('change_percent'):+.1f}%). Units change {un.get('change_percent'):+.1f}%. "
            f"These are model outputs; the elasticity is an assumption, not measured.{warn}"
        )

    def _explain_mc(self, pct: float, r: dict) -> str:
        net = r.get("net_profit", {})
        return (
            f"Across {r.get('iterations'):,} Monte Carlo draws around a {pct:+g}% price move, "
            f"net profit ranges from {_money(net.get('p5'))} (P5) to {_money(net.get('p95'))} (P95), "
            f"median {_money(net.get('p50'))}. Probability of a loss is "
            f"{_pct(r.get('probability_of_loss'))}. Price is the most influential input "
            f"(correlation {r.get('sensitivity', [{}])[0].get('correlation')}). This is a forecast "
            f"with uncertainty, not a single guaranteed number."
        )

    def _explain_compare(self, r: dict) -> str:
        best = r.get("best_by_net_profit")
        lines = [
            f"• {s['name']}: net profit {_money(s['values'].get('net_profit'))} "
            f"(Δ {_money(s['deltas'].get('net_profit'))})"
            for s in r.get("scenarios", [])
        ]
        return "Comparing the strategies (by net profit):\n" + "\n".join(lines) + (
            f"\nBest by net profit: {best}." if best else ""
        )

    def _explain_sensitivity(self, r: dict) -> str:
        rows = r.get("ranking", [])
        lines = [f"• {x['variable']}: swing {_money(x['swing'])} in net profit" for x in rows]
        return (
            f"Starting from a base net profit of {_money(r.get('base_value'))}, the levers that "
            f"move net profit the most are:\n" + "\n".join(lines)
        )

    def _explain_churn(self, r: dict) -> str:
        at = r.get("at_risk", [])
        if not at:
            return "No customers currently meet the evidence-based churn-risk criteria."
        lines = [f"• {c['name']} — {c.get('churn_reason')}" for c in at]
        return (
            f"{r['summary'].get('at_risk_count')} customers show churn-risk signals "
            f"(a gap well beyond their usual purchase cadence):\n" + "\n".join(lines)
        )

    def _explain_customers(self, r: dict) -> str:
        top = r.get("top_by_profit", [])
        lines = [f"• {c['name']}: {_money(c['gross_profit'])} gross profit, {c['orders']} orders"
                 for c in top]
        s = r.get("summary", {})
        return (
            f"Top customers by gross profit:\n" + "\n".join(lines) +
            f"\nRevenue concentration: top-5 customers are {_pct(s.get('top5_revenue_share'))} of "
            f"revenue; {s.get('at_risk_count')} customers are at churn risk."
        )

    def _explain_products(self, r: dict) -> str:
        best = r.get("best_sellers", [])
        lines = [f"• {p['name']}: {_money(p['revenue'])} revenue, {p['gross_margin'] * 100:.0f}% margin"
                 for p in best]
        dead = r.get("summary", {}).get("dead_stock_count", 0)
        return ("Best-selling products:\n" + "\n".join(lines) +
                f"\nDead-stock lines (on hand, no sales): {dead}.")

    def _explain_suppliers(self, r: dict) -> str:
        sup = r.get("suppliers", [])[:5]
        lines = [f"• {s['name']}: spend {_money(s['spend'])}, {s['product_count']} products, "
                 f"reliability {s.get('reliability_score')}" for s in sup]
        return "Suppliers by spend:\n" + "\n".join(lines)

    def _explain_risks(self, cust: dict, dq: dict) -> str:
        at = cust.get("summary", {}).get("at_risk_count", 0)
        conc = cust.get("summary", {}).get("top5_revenue_share")
        parts = [
            f"Customer concentration: top-5 customers make up {_pct(conc)} of revenue.",
            f"Churn risk: {at} customers show declining activity.",
            f"Data quality score: {dq.get('score')} (grade {dq.get('grade')}), "
            f"{len(dq.get('issues', []))} issue categor{'y' if len(dq.get('issues', [])) == 1 else 'ies'}.",
        ]
        return "Key risks based on current data:\n• " + "\n• ".join(parts)

    def _explain_dq(self, r: dict) -> str:
        issues = r.get("issues", [])
        if not issues:
            return f"Data-quality score is {r.get('score')} (grade {r.get('grade')}); no issues detected."
        lines = [f"• {i['description']} ({i['count']}, {i['severity']})" for i in issues]
        return (f"Data-quality score is {r.get('score')} (grade {r.get('grade')}). Issues:\n" +
                "\n".join(lines))
