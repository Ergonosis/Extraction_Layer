"""MSAL confidential-client helpers for multi-tenant Entra SSO."""

from __future__ import annotations

import msal
from flask import current_app


def build_msal_app() -> msal.ConfidentialClientApplication:
    """Build an MSAL app for the multi-tenant portal SSO registration."""
    client_id = current_app.config.get("MS_CLIENT_ID") or ""
    client_secret = current_app.config.get("MS_CLIENT_SECRET") or ""
    authority = current_app.config.get("MS_AUTHORITY") or (
        "https://login.microsoftonline.com/organizations"
    )
    if not client_id or not client_secret:
        raise RuntimeError(
            "MS_CLIENT_ID and MS_CLIENT_SECRET must be configured for Microsoft SSO"
        )
    return msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )


def authorization_url(state: str) -> str:
    """Return the Microsoft authorize URL for the auth-code flow."""
    app = build_msal_app()
    return app.get_authorization_request_url(
        scopes=list(current_app.config.get("MS_SSO_SCOPES") or ["openid", "profile", "email"]),
        state=state,
        redirect_uri=current_app.config["MS_REDIRECT_URI"],
    )


def exchange_auth_code(code: str) -> dict:
    """Exchange an authorization code for tokens; returns the MSAL result dict."""
    app = build_msal_app()
    result = app.acquire_token_by_authorization_code(
        code=code,
        scopes=list(current_app.config.get("MS_SSO_SCOPES") or ["openid", "profile", "email"]),
        redirect_uri=current_app.config["MS_REDIRECT_URI"],
    )
    return result or {}
