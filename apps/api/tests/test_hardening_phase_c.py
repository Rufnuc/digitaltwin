"""Phase C hardening: assistant read-only, kill switch, role enforcement,
numeric provenance."""
from __future__ import annotations

from app.core.config import settings
from app.services.ai import provenance
from app.services.ai.tools import execute_tool


class _U:
    def __init__(self, role):
        self.role = role
        self.id = 1


# --- C1: read-only / kill switch -------------------------------------------
def test_mutating_tool_disabled_in_read_only_mode(db, monkeypatch):
    monkeypatch.setattr(settings, "ASSISTANT_ALLOW_WRITES", False)
    r = execute_tool(db, "create_customer", {"name": "X Ltd"}, user=_U("OWNER"))
    assert "error" in r and "read-only" in r["error"].lower()


def test_mutating_tool_proposes_when_writes_enabled(db, monkeypatch):
    # With writes enabled the first call PROPOSES (never executes); confirming runs it.
    monkeypatch.setattr(settings, "ASSISTANT_ALLOW_WRITES", True)
    prop = execute_tool(db, "create_customer", {"name": "Y Ltd"}, user=_U("STAFF"))
    assert prop.get("status") == "PROPOSED" and prop.get("confirmation_token")
    out = execute_tool(db, "create_customer", {"name": "Y Ltd"}, user=_U("STAFF"),
                       confirmed=True)
    assert out.get("created") == "customer", out


# --- C2: role enforcement on ALL tools (not just mutating) -----------------
def test_restricted_read_tool_blocked_for_low_role(db):
    # get_payables is MANAGER-only; a STAFF chat user must be refused.
    r = execute_tool(db, "get_payables", {}, user=_U("STAFF"))
    assert "error" in r and "requires role" in r["error"].lower()


def test_restricted_read_tool_allowed_for_manager(db):
    r = execute_tool(db, "get_payables", {}, user=_U("MANAGER"))
    assert "error" not in r


# --- C4: numeric provenance ------------------------------------------------
def test_unverified_number_flagged():
    tool_calls = [{"result": {"total_outstanding": 3012000.0}}]
    # The model states a figure that never appeared in the tool result.
    bad = provenance.verify_answer("Your debtors owe ₦9,999,999 in total.", tool_calls)
    assert bad == ["₦9,999,999"]


def test_sourced_number_passes():
    tool_calls = [{"result": {"total_outstanding": 3012000.0}}]
    ok = provenance.verify_answer("Your debtors owe ₦3,012,000.", tool_calls)
    assert ok == []


def test_small_bare_numbers_ignored():
    # List markers / small counts must not be flagged as unsourced figures.
    tool_calls = [{"result": {"count": 3}}]
    assert provenance.verify_answer("Here are 3 points: 1) buy 2) sell 3) hold.",
                                    tool_calls) == []
