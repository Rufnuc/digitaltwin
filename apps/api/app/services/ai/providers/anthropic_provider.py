"""Anthropic LLM provider (spec §4, §32).

A real language-model provider behind the same seam as the offline router. The
LLM interprets the question and explains results; it obtains every number by
calling the registered tools (which hit the deterministic engines) and is
instructed never to invent figures. Uses a manual agentic loop over the standard
Anthropic SDK so the package is only imported when this provider is selected.
"""
from __future__ import annotations

import json

from app.core.config import settings
from app.services.ai.tools import ToolDef
from app.services.ai.types import AssistantResult, Executor, ToolCall

_MAX_TURNS = 6  # cap tool-call rounds to bound cost/latency


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.AI_API_KEY
        self.model = model or settings.AI_MODEL

    def _client(self):
        # Lazy import: the `anthropic` package is optional and only needed here.
        import anthropic

        return anthropic.Anthropic(api_key=self.api_key or None)

    def answer(
        self, question: str, tools: list[ToolDef], execute: Executor, system: str
    ) -> AssistantResult:
        client = self._client()
        anthropic_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]
        messages: list[dict] = [{"role": "user", "content": question}]
        trace: list[ToolCall] = []

        for _ in range(_MAX_TURNS):
            resp = client.messages.create(
                model=self.model,
                max_tokens=1600,
                system=system,
                tools=anthropic_tools,
                messages=messages,
            )
            if resp.stop_reason != "tool_use":
                text = "".join(b.text for b in resp.content if b.type == "text")
                return AssistantResult(
                    answer=text.strip(), tool_calls=trace, provider=self.name, model=self.model
                )

            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                # Tool inputs must be parsed as JSON objects, never string-matched.
                args = block.input if isinstance(block.input, dict) else json.loads(block.input)
                result = execute(block.name, args)
                trace.append(ToolCall(name=block.name, args=args, result=result))
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
            messages.append({"role": "user", "content": results})

        # Ran out of turns — return whatever tools produced with an honest note.
        return AssistantResult(
            answer="I gathered the data but reached the tool-call limit before finalising a "
                   "summary. See the tool results below.",
            tool_calls=trace,
            provider=self.name,
            model=self.model,
        )
