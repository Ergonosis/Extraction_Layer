"""Content-Security-Policy helpers for the portal SPA (issue #33)."""

from __future__ import annotations

# Allows same-origin SPA + Plaid Link + Microsoft Entra / Graph.
# Start with REPORT_ONLY in non-production; ENFORCE in production by default.
DEFAULT_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self' https://*.plaid.com https://production.plaid.com "
    "https://sandbox.plaid.com https://login.microsoftonline.com "
    "https://graph.microsoft.com https://*.microsoftonline.com; "
    "frame-src 'self' https://cdn.plaid.com https://*.plaid.com "
    "https://login.microsoftonline.com https://*.microsoftonline.com; "
    "form-action 'self' https://login.microsoftonline.com https://*.microsoftonline.com"
)


def resolve_csp_mode(raw: str | None, *, flask_env: str) -> str:
    """Return off | report-only | enforce."""
    value = (raw or "").strip().lower()
    if value in {"off", "report-only", "enforce"}:
        return value
    env = (flask_env or "").strip().lower()
    if env == "production":
        return "enforce"
    return "report-only"
