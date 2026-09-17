"""Signed confirmation tokens for two-step assistant writes.

A mutating assistant tool never executes on first sight: it returns a proposal
carrying one of these tokens, which encodes exactly what would be done (tool name,
arguments, acting user) and expires quickly. The confirm endpoint verifies the
token — so the action that runs is the one that was proposed, unaltered — then
executes with the kill switch and role checks still applied.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.core.config import settings

_TTL_SECONDS = 600  # a proposal is valid for 10 minutes


def _secret() -> bytes:
    return (settings.AUTH_SECRET or "dev").encode()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(name: str, args: dict, user_id: int | None) -> str:
    payload = {"n": name, "a": args or {}, "u": user_id, "exp": int(time.time()) + _TTL_SECONDS}
    raw = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    sig = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_token(token: str) -> dict | None:
    """Return the decoded proposal ({name, args, user_id}) or None if the token is
    malformed, tampered, or expired."""
    try:
        raw, sig = token.split(".", 1)
    except (ValueError, AttributeError):
        return None
    expected = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_unb64(raw))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or int(payload.get("exp", 0)) < int(time.time()):
        return None
    return {"name": payload.get("n"), "args": payload.get("a") or {}, "user_id": payload.get("u")}
