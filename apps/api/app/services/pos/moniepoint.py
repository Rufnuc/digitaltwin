"""Moniepoint POS adapter.

IMPORTANT: Moniepoint's exact webhook payload, signature header and push-to-terminal
endpoint depend on your business/developer account. The field names and the signature
scheme below are the common pattern (HMAC-SHA256 over the raw body, JSON body with
amount in the major unit or kobo); confirm them against the docs Moniepoint gives you
and adjust `_FIELD_ALIASES`, `_SIGNATURE_HEADER` and `push_charge` accordingly. Until
MONIEPOINT_WEBHOOK_SECRET / MONIEPOINT_API_KEY are set, verification/pushing fail
closed (safe) and reconciliation falls back to manual.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.services.pos.base import PosProviderError, PosTxn

logger = logging.getLogger("digitaltwin.pos")

_SIGNATURE_HEADER = "x-moniepoint-signature"
_TIMEOUT = 8.0

# Tolerant field lookup: try several likely key names so a minor payload difference
# doesn't break ingestion. Adjust to match the real Moniepoint payload.
_FIELD_ALIASES = {
    "txn_id": ["transactionReference", "transactionId", "reference", "id", "rrn"],
    "amount": ["amount", "transactionAmount", "amountPaid"],
    "terminal_id": ["terminalId", "terminalSerial", "terminal", "deviceId"],
    "reference": ["rrn", "stan", "narration", "paymentReference", "reference"],
    "masked_pan": ["maskedPan", "cardNumber", "pan"],
    "occurred_at": ["transactionTime", "paymentDate", "timestamp", "createdAt"],
    "status": ["status", "responseCode", "transactionStatus"],
}


def _pick(payload: dict, key: str) -> object | None:
    for alias in _FIELD_ALIASES[key]:
        if alias in payload and payload[alias] not in (None, ""):
            return payload[alias]
    # Some providers nest the fields under "data".
    data = payload.get("data")
    if isinstance(data, dict):
        for alias in _FIELD_ALIASES[key]:
            if alias in data and data[alias] not in (None, ""):
                return data[alias]
    return None


def _to_amount(value: object) -> float:
    """Amount may arrive as naira (e.g. 1500.00) or kobo (e.g. 150000). We treat a
    value with no fractional part and >= 1000 that is divisible by 100 as kobo only
    when the payload says so; by default assume the major unit (naira). Adjust once
    the real unit is known."""
    try:
        return round(float(value), 2)  # assume naira (major unit)
    except (TypeError, ValueError) as e:
        raise PosProviderError(f"unparseable amount: {value!r}") from e


def _to_dt(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    s = str(value)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:26], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class MoniepointProvider:
    name = "moniepoint"

    @property
    def can_push(self) -> bool:
        return bool(settings.MONIEPOINT_API_KEY and settings.MONIEPOINT_PUSH_URL)

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> bool:
        secret = settings.MONIEPOINT_WEBHOOK_SECRET
        if not secret:
            logger.warning("Moniepoint webhook secret not set — rejecting webhook")
            return False
        # Headers are compared case-insensitively.
        lower = {k.lower(): v for k, v in headers.items()}
        sent = lower.get(_SIGNATURE_HEADER, "")
        if not sent:
            return False
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        # Accept either raw hex or a "sha256=" prefixed form.
        candidate = sent.split("=", 1)[1] if "=" in sent else sent
        return hmac.compare_digest(expected, candidate)

    def parse_webhook(self, payload: dict) -> PosTxn:
        txn_id = _pick(payload, "txn_id")
        amount = _pick(payload, "amount")
        if txn_id is None or amount is None:
            raise PosProviderError("webhook missing transaction id or amount")
        return PosTxn(
            provider=self.name,
            provider_txn_id=str(txn_id),
            amount=_to_amount(amount),
            terminal_id=(str(_pick(payload, "terminal_id")) if _pick(payload, "terminal_id") else None),
            reference=(str(_pick(payload, "reference")) if _pick(payload, "reference") else None),
            masked_pan=(str(_pick(payload, "masked_pan")) if _pick(payload, "masked_pan") else None),
            occurred_at=_to_dt(_pick(payload, "occurred_at")),
            raw=payload,
        )

    def push_charge(self, *, terminal_id: str, amount: float, reference: str) -> dict:
        if not self.can_push:
            raise PosProviderError(
                "Moniepoint push-to-terminal is not configured (set MONIEPOINT_API_KEY "
                "and MONIEPOINT_PUSH_URL)."
            )
        try:
            r = httpx.post(
                settings.MONIEPOINT_PUSH_URL,
                headers={"Authorization": f"Bearer {settings.MONIEPOINT_API_KEY}"},
                json={"terminalId": terminal_id, "amount": amount, "reference": reference},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json() if r.content else {}
        except httpx.HTTPError as e:
            raise PosProviderError(f"could not reach the terminal: {e}") from e
        return {"request_id": str(data.get("requestId") or data.get("reference") or reference),
                "raw": data}
