# AI Business Assistant (Phase 4)

An assistant that answers plain-language business questions. It **interprets
intent and explains results**; it obtains every number by calling tools that hit
the deterministic analytics/simulation engines, and it **never invents figures**
(spec §2, §32, §50, §51).

## Architecture

```
question -> provider.answer(question, tools, execute, system)
              provider decides which tool(s) to call
              execute(name, args) -> tool hits a real service -> data
            -> natural-language answer composed FROM the tool results
```

- **Tools** (`services/ai/tools.py`) — read/compute-only wrappers over existing
  services: `get_business_summary`, `get_financials`, `get_customer_intelligence`,
  `get_product_intelligence`, `get_supplier_intelligence`, `get_data_quality`,
  `run_scenario`, `run_monte_carlo`, `run_sensitivity`, `compare_price_strategies`.
  Each carries a provenance tag (`MODEL_OUTPUT` or `FORECAST`).
- **Providers** (`services/ai/providers/`) — behind one seam:
  - `rule_based` (**default, offline**) — a transparent intent router that maps
    questions to tools and templates the answer *entirely from tool output*, so
    the "never invent numbers" guarantee is trivially true and the assistant works
    with zero API keys or external calls.
  - `anthropic` — a real LLM using a manual tool-use loop over the Anthropic SDK
    (lazy-imported). Enabled with `AI_PROVIDER=anthropic` + `AI_API_KEY`
    (`AI_MODEL` defaults to `claude-opus-5`). The system prompt enforces the rules
    and the same tools back it.
- **Facade** (`services/ai/assistant.py`) — selects the provider, tags the prose as
  `AI_INTERPRETATION`, and writes an `AI_QUERY` audit-log entry with the tools used.

## API

```
POST /api/v1/assistant/ask    { question }  -> answer + provider + tool_calls + disclaimer
GET  /api/v1/assistant/tools                -> the tool catalogue
```

Available to any authenticated user (all tools are read/compute-only).

## Provenance in the response

- `provenance: "AI_INTERPRETATION"` on the prose.
- Each `tool_calls[]` entry carries the tool's own `provenance` (`MODEL_OUTPUT` /
  `FORECAST`) and its full result — surfaced in the UI's "data sources" drawer so
  every figure is traceable to the engine that produced it.

## What the assistant will not do
Invent or estimate numbers, present a Monte Carlo forecast as a single certainty,
or imply demo data is real. If a needed number has no tool, it says so.
