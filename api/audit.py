"""Structured audit events for portal auth and integration lifecycle (issue #33).

Logs JSON lines to the ``portal.audit`` logger (stdout → Cloud Logging on Cloud Run).
Never log tokens, cookies, CSRF secrets, or Fernet key material.
"""

from __future__ import annotations

import json
import logging
from typing import Any

_audit = logging.getLogger("portal.audit")

# Keys that must never appear in audit payloads (defense in depth).
_BLOCKED_SUBSTRINGS = (
    "token",
    "secret",
    "password",
    "cookie",
    "csrf",
    "fernet",
    "authorization",
    "api_key",
    "apikey",
)


def _sanitize(extra: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in extra.items():
        lowered = str(key).lower()
        if any(bad in lowered for bad in _BLOCKED_SUBSTRINGS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean


def audit(
    event: str,
    *,
    user_id: int | None = None,
    organization_id: int | None = None,
    **extra: Any,
) -> None:
    """Emit one structured audit event (info level JSON)."""
    payload = {
        "event": event,
        "user_id": user_id,
        "organization_id": organization_id,
        **_sanitize(extra),
    }
    _audit.info(json.dumps(payload, default=str, separators=(",", ":")))
