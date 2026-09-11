"""Assistant provider contract and result shapes."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.services.ai.tools import ToolDef


@dataclass
class ToolCall:
    name: str
    args: dict
    result: dict


@dataclass
class AssistantResult:
    answer: str            # AI_INTERPRETATION — natural-language explanation only
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider: str = "unknown"
    model: str | None = None


# execute(name, args) -> tool result dict
Executor = Callable[[str, dict], dict]


class AssistantProvider(Protocol):
    name: str

    def answer(
        self, question: str, tools: list[ToolDef], execute: Executor, system: str
    ) -> AssistantResult: ...
