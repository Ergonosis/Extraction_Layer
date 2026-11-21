"""Build the Microsoft Graph client used for delegated exports."""

from __future__ import annotations

from typing import Any

from src.microsoft.ms_graph_email_client import MicrosoftGraphEmailClient


def client_from_access_token(access_token: str) -> Any:
    """Build a Graph client that uses an in-memory delegated access token."""
    return MicrosoftGraphEmailClient.from_access_token(access_token)
