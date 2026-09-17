"""Numeric provenance enforcement for assistant answers.

The system prompt tells Benfieg never to invent numbers, but an instruction is not
a guarantee — a small local model can miscopy or fabricate a figure. This module
checks it: every business-critical number in the answer must trace to a value that
actually appeared in a tool result. Unverified figures are flagged (and logged) so a
fabricated number is never presented as fact.

A "business-critical" number is one that reads like money or a real quantity: it
carries a ₦ sign, a thousands separator or decimals, or is >= 1000. Small bare
integers (list markers "1) 2)", "4-6 insights", years) are ignored to avoid noise.
"""
from __future__ import annotations

import re

# A number, optionally money-formatted: ₦1,234,567.89 / 1234.5 / 42
_NUM = re.compile(r"₦\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*\.\d+|\d[\d,]*")
_TOL_ABS = 0.5      # naira rounding tolerance
_TOL_REL = 0.005    # or 0.5% for large figures


def collect_source_numbers(obj) -> set[float]:
    """Every numeric value that appeared anywhere in the tool results."""
    out: set[float] = set()

    def walk(o) -> None:
        if isinstance(o, bool):
            return
        if isinstance(o, int | float):
            out.add(float(o))
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list | tuple):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            for m in _NUM.findall(o):
                try:
                    out.add(float(m.replace("₦", "").replace(",", "").strip()))
                except ValueError:
                    pass

    walk(obj)
    # Also index rounded forms so "₦3,012,000" matches a source of 3012000.49.
    out |= {round(n) for n in list(out)}
    out |= {round(n, 2) for n in list(out)}
    return out


def _matches(value: float, sources: set[float]) -> bool:
    for s in sources:
        if abs(s - value) <= max(_TOL_ABS, abs(value) * _TOL_REL):
            return True
    return False


def _is_business_critical(token: str, value: float) -> bool:
    return "₦" in token or "," in token or "." in token or abs(value) >= 1000


def unverified_numbers(answer: str, sources: set[float]) -> list[str]:
    """Business-critical numbers in `answer` that do not trace to any tool value."""
    bad: list[str] = []
    for token in _NUM.findall(answer or ""):
        try:
            value = float(token.replace("₦", "").replace(",", "").strip())
        except ValueError:
            continue
        if not _is_business_critical(token, value):
            continue
        if not _matches(value, sources):
            bad.append(token.strip())
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    return [t for t in bad if not (t in seen or seen.add(t))]


def verify_answer(answer: str, tool_calls: list) -> list[str]:
    """Return the list of unverified business-critical figures in the answer.

    `tool_calls` are the trace dicts (each with a `result`); their numbers are the
    only sanctioned source of figures.
    """
    sources: set[float] = set()
    for c in tool_calls or []:
        sources |= collect_source_numbers(c.get("result") if isinstance(c, dict) else None)
    if not sources and not (answer or "").strip():
        return []
    return unverified_numbers(answer, sources)
