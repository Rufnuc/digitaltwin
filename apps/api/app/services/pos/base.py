"""POS provider abstraction.

A provider knows how to (a) verify and parse a terminal's webhook into a normalised
transaction, and (b) optionally push a charge to a terminal so it pops the amount.
Concrete providers (Moniepoint) plug in; the Null provider keeps the app running with
auto-receiving disabled (manual reconciliation still works).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.core.config import settings


@dataclass
class PosTxn:
    """A normalised POS transaction parsed from a provider webhook."""

    provider: str
    provider_txn_id: str
    amount: float
    terminal_id: str | None = None
    reference: str | None = None
    masked_pan: str | None = None
    occurred_at: datetime | None = None
    raw: dict = field(default_factory=dict)


class PosProviderError(RuntimeError):
    """Raised when a provider cannot verify/parse a webhook or push a charge."""


class PosProvider(Protocol):
    name: str
    can_push: bool

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool: ...
    def parse_webhook(self, payload: dict) -> PosTxn: ...
    def push_charge(self, *, terminal_id: str, amount: float, reference: str) -> dict: ...


class NullPosProvider:
    """No external POS wired up. Webhooks are rejected and pushing is unavailable;
    cashiers still reconcile manually from the Unmatched screen."""

    name = "none"
    can_push = False

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
        return False

    def parse_webhook(self, payload: dict) -> PosTxn:
        raise PosProviderError("No POS provider configured. Set POS_PROVIDER=moniepoint.")

    def push_charge(self, *, terminal_id: str, amount: float, reference: str) -> dict:
        raise PosProviderError(
            "Push-to-terminal is not available: configure Moniepoint API credentials."
        )


def get_pos_provider() -> PosProvider:
    provider = (settings.POS_PROVIDER or "none").lower()
    if provider == "moniepoint":
        from app.services.pos.moniepoint import MoniepointProvider

        return MoniepointProvider()
    return NullPosProvider()
