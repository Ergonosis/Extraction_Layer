"""Plaid API client factory (mirrors plaid/extractors/plaid_ext.PlaidExtractor)."""

from __future__ import annotations

import plaid
from flask import current_app
from plaid.api import plaid_api


def get_plaid_client() -> plaid_api.PlaidApi:
    """Build a PlaidApi from app config. Raises RuntimeError if unset."""
    client_id = (current_app.config.get("PLAID_CLIENT_ID") or "").strip()
    secret = (current_app.config.get("PLAID_SECRET") or "").strip()
    env = (current_app.config.get("PLAID_ENV") or "sandbox").strip().lower()

    if not client_id or not secret:
        raise RuntimeError("Plaid is not configured (set PLAID_CLIENT_ID and PLAID_SECRET)")

    host = plaid.Environment.Sandbox
    if env == "development":
        host = plaid.Environment.Development
    elif env == "production":
        host = plaid.Environment.Production

    configuration = plaid.Configuration(
        host=host,
        api_key={"clientId": client_id, "secret": secret},
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))
