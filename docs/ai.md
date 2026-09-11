# AI (Phase 4 — interface only)

No LLM is wired in Phase 1. The seam lives in `app/services/ai/base.py`:
`AIProvider` (provider-agnostic chat/tool interface), `ToolSpec`, `AIMessage`,
and a `NullAIProvider` that refuses to fabricate output.

## The rule this seam enforces

The assistant will **interpret intent** and **explain results**; it will call
tools (`query_*`, `run_simulation`, `run_monte_carlo`, `compare_scenarios`,
`get_business_alerts`, …) to obtain data and numbers. It will **never** invent a
database value or a calculation. AI actions will be audit-logged
(`audit_logs`, action = AI-specific) and answers will cite provenance.

Provider selection is by `AI_PROVIDER` env var; the application is never
hard-coded to one vendor (spec §4).
