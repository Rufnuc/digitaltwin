"""Local LLM provider via Ollama (spec §4, §32).

A real language model running locally through Ollama — free and key-less. It does
genuine tool-calling over the same tool registry: the model decides which tools to
call, we execute them against the deterministic engines, and feed the results
back. The model interprets and explains; it never produces the numbers itself.

Requires Ollama running with a tool-capable model (e.g. qwen2.5). Uses the native
/api/chat endpoint over httpx — no extra SDK.
"""
from __future__ import annotations

import json

import httpx

from app.core.config import settings
from app.services.ai.tools import ToolDef
from app.services.ai.types import AssistantResult, Executor, ToolCall

_MAX_TURNS = 6
_TIMEOUT = 120.0


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL

    def _chat(self, client: httpx.Client, messages: list[dict], tools: list[dict]) -> dict:
        r = client.post(
            f"{self.base_url}/api/chat",
            json={"model": self.model, "messages": messages, "tools": tools, "stream": False},
        )
        r.raise_for_status()
        return r.json().get("message", {})

    def answer(
        self, question: str, tools: list[ToolDef], execute: Executor, system: str
    ) -> AssistantResult:
        ollama_tools = [
            {"type": "function",
             "function": {"name": t.name, "description": t.description,
                          "parameters": t.input_schema}}
            for t in tools
        ]
        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ]
        trace: list[ToolCall] = []

        with httpx.Client(timeout=_TIMEOUT) as client:
            for _ in range(_MAX_TURNS):
                msg = self._chat(client, messages, ollama_tools)
                calls = msg.get("tool_calls") or []
                if not calls:
                    return AssistantResult(
                        answer=(msg.get("content") or "").strip(),
                        tool_calls=trace, provider=self.name, model=self.model,
                    )

                messages.append({"role": "assistant", "content": msg.get("content", ""),
                                 "tool_calls": calls})
                for c in calls:
                    fn = c.get("function", {})
                    name = fn.get("name", "")
                    args = fn.get("arguments", {})
                    # Ollama usually returns a dict; be defensive if it's a JSON string.
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    result = execute(name, args)
                    trace.append(ToolCall(name=name, args=args, result=result))
                    messages.append({"role": "tool", "tool_name": name,
                                     "content": json.dumps(result)})

        return AssistantResult(
            answer="I gathered the data but reached the tool-call limit before summarising.",
            tool_calls=trace, provider=self.name, model=self.model,
        )
