"""Static integration metadata (shared by dashboard and later MS Graph issues)."""

from __future__ import annotations

SUPPORTED_PROVIDERS = ("plaid", "msgraph")

PROVIDER_LABELS = {
    "plaid": "Plaid",
    "msgraph": "Microsoft Graph",
}

# Hardcoded allowlist / display labels for MS Graph delegated scopes.
MS_GRAPH_SCOPE_LABELS = {
    "User.Read": "Basic profile",
    "Mail.Read": "Email",
    "Calendars.Read": "Calendar",
    "Files.Read": "Files",
}
