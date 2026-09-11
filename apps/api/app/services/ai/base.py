"""AI provider abstraction (spec §4, Phase 4).

Phase 1 defines the seam ONLY — there is deliberately no LLM call anywhere in the
codebase yet. The critical architectural rule lives here as documentation and as
the shape of the future interface: the LLM interprets intent and explains results;
it never produces numbers. Numbers come exclusively from the simulation/analytics
engines.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)


@dataclass
class AIMessage:
    role: str
    content: str


class AIProvider(Protocol):
    """A provider-agnostic chat/tool interface. Implemented in Phase 4."""

    def complete(self, messages: list[AIMessage], tools: list[ToolSpec] | None = None) -> AIMessage:
        ...


class NullAIProvider:
    """Default. Refuses to fabricate output, per the no-fake-intelligence rule."""

    def complete(self, messages: list[AIMessage], tools: list[ToolSpec] | None = None) -> AIMessage:
        raise NotImplementedError(
            "AI provider not configured. The AI assistant is a Phase 4 capability; "
            "no LLM is wired in Phase 1."
        )


def get_ai_provider() -> AIProvider:
    return NullAIProvider()
