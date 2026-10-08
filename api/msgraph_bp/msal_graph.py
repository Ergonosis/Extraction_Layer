"""MSAL helpers for Microsoft Graph delegated connect (separate from portal SSO)."""

from __future__ import annotations

import msal
from flask import current_app


def build_msal_app() -> msal.ConfidentialClientApplication:
    client_id = current_app.config.get("MS_CLIENT_ID") or ""
    client_secret = current_app.config.get("MS_CLIENT_SECRET") or ""
    authority = current_app.config.get("MS_AUTHORITY") or (
        "https://login.microsoftonline.com/organizations"
    )
    if not client_id or not client_secret:
        raise RuntimeError(
            "MS_CLIENT_ID and MS_CLIENT_SECRET must be configured for Microsoft Graph"
        )
    return msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )


def graph_redirect_uri() -> str:
    return current_app.config.get("MS_GRAPH_REDIRECT_URI") or (
        "http://localhost:5175/api/msgraph/callback"
    )


def authorization_url(*, state: str, scopes: list[str]) -> str:
    app = build_msal_app()
    return app.get_authorization_request_url(
        scopes=scopes,
        state=state,
        redirect_uri=graph_redirect_uri(),
    )


def exchange_auth_code(*, code: str, scopes: list[str]) -> dict:
    app = build_msal_app()
    result = app.acquire_token_by_authorization_code(
        code=code,
        scopes=scopes,
        redirect_uri=graph_redirect_uri(),
    )
    return result or {}


def refresh_access_token(*, refresh_token: str, scopes: list[str]) -> dict:
    app = build_msal_app()
    result = app.acquire_token_by_refresh_token(
        refresh_token=refresh_token,
        scopes=scopes,
    )
    return result or {}
