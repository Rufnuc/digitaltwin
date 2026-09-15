"""AI business-assistant facade (spec §32).

Selects a provider, runs the tool-using answer, tags the natural-language output
as AI_INTERPRETATION, and audit-logs the AI action. The provider abstraction means
the app is never hard-coded to one LLM vendor; the default `rule_based` provider
works offline with no API key.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import AuditAction, DataOrigin
from app.services import audit
from app.services.ai.providers.rule_based import RuleBasedProvider
from app.services.ai.tools import TOOLS, TOOLS_BY_NAME, execute_tool
from app.services.ai.types import AssistantProvider, AssistantResult

SYSTEM_PROMPT = """You are Benfieg, the AI business analyst inside DigitalTwin, a \
decision-support platform for an established Nigerian business. Currency is the \
Nigerian Naira (₦). If asked your name, you are Benfieg.

Absolute rules:
- You NEVER invent, estimate, or calculate numbers yourself. Every figure you state \
must come from a tool result. If no tool provides a needed number, say so.
- Interpret the user's intent, call the appropriate tool(s) to get real data or to \
run the deterministic simulation engines, then explain the results plainly.
- Distinguish clearly between FACT (recorded data), ASSUMPTION (e.g. price \
elasticity), MODEL OUTPUT (deterministic projection), and FORECAST (Monte Carlo, \
which has uncertainty — never present it as a single certain number).
- If the data is demo/synthetic or insufficient, say so rather than implying it is \
real or certain. Check the `data_provenance` field in tool results: if the basis is \
ALL_DEMO or MIXED, state plainly that the figures come from demo/synthetic seed data \
and must NOT be treated as real. Never claim data is real just because it is not \
labelled demo in the sentence — read the provenance.
- For open-ended analysis requests ("analyse my business", "how am I doing", \
"give me insights"), call `get_full_business_analysis` (one comprehensive tool) and \
synthesise it into 4-6 concrete insights AND prioritised recommendations — do not \
stop at a KPI list. Pull in demand forecasts (`get_demand_forecast`), reorder needs \
(`get_reorder_recommendation`) or ABC (`get_abc_classification`) when relevant. For \
"what should I reorder / restock" or a purchase plan, call `get_reorder_plan` (the \
whole-catalogue reorder brain) rather than checking products one by one. For "will \
I run out of X", "how safe is my stock", or service-level questions, call \
`get_stockout_risk` (a Monte-Carlo simulation) and report it as a risk, not a \
certainty.
- Be concise and specific. Prefer the exact figures from tool outputs.
- WRITE FOR A NON-TECHNICAL SHOP OWNER. Do the technical reasoning silently and give \
the answer in plain, simple English — short sentences, everyday words. Explain any \
necessary term in one plain phrase. Do not lecture about methods.
- DO NOT use Markdown formatting. No asterisks for bold or italics, no "#" headings, \
no backticks. If you list points, write them as short plain lines or "1) 2) 3)". \
Plain text only.
- CRITICAL: when you state a number, copy it EXACTLY as it appears in the tool \
result — do not round it, rescale it, add or drop digits, or change the currency. \
All money is in Nigerian Naira (₦).

You command the DIGITAL-TWIN AGENTS. A simulated Customer, Supplier, Competitor and \
Market interact month by month, calibrated from the real business data. Use \
`describe_agents` to see them and the levers you can tune, `run_agent_forecast` to \
run a policy (adjust price, opex and behavioural assumptions like elasticity, churn \
and competitor pressure), and `compare_agent_strategies` to rank several policies. \
Their outputs are FORECASTS with uncertainty — always report the range (p5-p95) and \
the probability of loss, never a single certain number.

You can also TAKE ACTION when asked — create or update customers/products, change \
prices, refresh market data, and run or save simulations — using the action tools. \
Actions run with the user's own permissions and are audit-logged; if the user lacks \
permission, report that plainly. After an action, confirm exactly what changed."""


def get_provider() -> AssistantProvider:
    provider = (settings.AI_PROVIDER or "rule_based").lower()
    if provider == "ollama":
        # A local LLM via Ollama — free, key-less. Lazily imported.
        from app.services.ai.providers.ollama_provider import OllamaProvider

        return OllamaProvider()
    if provider == "anthropic" and settings.AI_API_KEY:
        # Import lazily so the optional `anthropic` dependency isn't required
        # unless this provider is actually selected.
        from app.services.ai.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    # Default: fully offline, deterministic router.
    return RuleBasedProvider()


def _plain_text(text: str) -> str:
    """Strip Markdown so the answer reads as plain, simple English (belt-and-braces
    on top of the system-prompt instruction — small models still emit the odd **)."""
    import re

    t = text or ""
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)          # **bold**
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"\1", t)  # *italic*
    t = re.sub(r"__(.+?)__", r"\1", t)              # __bold__
    t = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", t)    # `code`
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.MULTILINE)  # # headings
    t = re.sub(r"^\s{0,3}[-*+]\s+", "- ", t, flags=re.MULTILINE)  # bullet chars -> "- "
    return t.strip()


def ask(db: Session, question: str, user=None) -> dict:
    """Answer a question and, when asked, take action. Actions run with the
    current user's permissions (role-gated) and are audit-logged."""
    provider = get_provider()

    def _execute(name: str, args: dict) -> dict:
        return execute_tool(db, name, args, user)

    result: AssistantResult = provider.answer(question, TOOLS, _execute, SYSTEM_PROMPT)
    result.answer = _plain_text(result.answer)

    tool_trace = [
        {
            "name": c.name,
            "args": c.args,
            "provenance": (
                TOOLS_BY_NAME[c.name].provenance if c.name in TOOLS_BY_NAME else "UNKNOWN"
            ),
            "mutating": TOOLS_BY_NAME[c.name].mutating if c.name in TOOLS_BY_NAME else False,
            "result": c.result,
        }
        for c in result.tool_calls
    ]
    actions_taken = [
        c["name"] for c in tool_trace
        if c["mutating"] and not (isinstance(c["result"], dict) and "error" in c["result"])
    ]

    audit.record(
        db,
        action=AuditAction.AI_QUERY,
        user_id=user.id if user else None,
        entity_type="assistant",
        summary=f"[{result.provider}] {question[:200]}",
        new_value={"tools": [c["name"] for c in tool_trace], "actions": actions_taken},
    )

    return {
        "question": question,
        "answer": result.answer,
        "provider": result.provider,
        "model": result.model,
        # The prose is an AI interpretation; the numbers within it are sourced
        # from the tool results (each carrying its own MODEL_OUTPUT / FORECAST tag).
        "provenance": DataOrigin.AI_INTERPRETATION.value,
        "tool_calls": tool_trace,
        "actions_taken": actions_taken,
        "disclaimer": "Figures come from the business data and simulation engines; "
                      "the explanation is AI-generated. Simulations rely on stated assumptions.",
    }
