"""Strict JSON body helpers for mutation endpoints."""

from __future__ import annotations

from typing import Any, Iterable


class ValidationError(Exception):
    """Request body failed allowlist / shape checks."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def require_object(body: object) -> dict[str, Any]:
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ValidationError("JSON body must be an object")
    return body


def reject_unknown_fields(body: dict[str, Any], allowed: Iterable[str]) -> None:
    """Reject unexpected top-level keys with HTTP 400."""
    allowed_set = set(allowed)
    unknown = sorted(k for k in body.keys() if k not in allowed_set)
    if unknown:
        raise ValidationError(f"Unexpected fields: {', '.join(unknown)}")
