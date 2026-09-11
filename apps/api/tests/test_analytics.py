"""Deterministic financial-calculation tests (spec §46)."""
from __future__ import annotations

from app.services.analytics import pnl


def test_pnl_known_values():
    # spec §46 canonical case.
    result = pnl(revenue=100, cogs=40, operating_expenses=20)
    assert result.gross_profit == 60
    assert result.net_profit == 40
    assert result.gross_margin == 0.6
    assert result.net_margin == 0.4


def test_pnl_zero_revenue_no_divide_by_zero():
    result = pnl(revenue=0, cogs=0, operating_expenses=0)
    assert result.gross_margin == 0.0
    assert result.net_margin == 0.0


def test_pnl_loss():
    result = pnl(revenue=100, cogs=80, operating_expenses=40)
    assert result.gross_profit == 20
    assert result.net_profit == -20
    assert result.net_margin == -0.2
