"""Microsoft Entra SSO auth routes (multi-tenant)."""

from __future__ import annotations

import secrets

from flask import current_app, jsonify, redirect, request, session

from api.auth import bp
from api.auth import msal_client
from api.auth.decorators import login_required
from api.auth.dev_login import is_dev_login_allowed, upsert_dev_identity
from api.auth.service import AuthError, complete_sso_login
from api.auth.session_utils import (
    destroy_session,
    regenerate_session,
    safe_post_login_url,
)
from api.extensions import db
from api.middleware import ensure_csrf_token
from api.models import User
from api.rate_limit import (
    auth_callback_limit,
    auth_login_limit,
    auth_me_limit,
    mutation_limit,
)


@bp.get("/ping")
def ping():
    """Scaffold placeholder so the blueprint is reachable."""
    return jsonify({"blueprint": "auth", "status": "ok"})


@bp.get("/csrf-token")
def csrf_token():
    """Issue (or return) the CSRF token for the SPA double-submit header."""
    session.permanent = True
    token = ensure_csrf_token()
    return jsonify({"csrf_token": token})


@bp.post("/ping")
@mutation_limit
def ping_mutation():
    """Mutation stub for CSRF / rate-limit checks."""
    return jsonify({"blueprint": "auth", "status": "ok", "method": "POST"})


@bp.get("/login")
@auth_login_limit
def login():
    """Start Microsoft SSO: redirect browser to Entra authorize URL."""
    if not current_app.config.get("MS_CLIENT_ID") or not current_app.config.get(
        "MS_CLIENT_SECRET"
    ):
        return (
            jsonify(
                {
                    "error": "SSO not configured",
                    "detail": "Set MS_CLIENT_ID and MS_CLIENT_SECRET",
                }
            ),
            503,
        )

    state = secrets.token_urlsafe(32)
    session.permanent = True
    session["oauth_state"] = state

    redirect_after = request.args.get("redirect")
    if redirect_after:
        session["post_login_redirect"] = redirect_after

    try:
        url = msal_client.authorization_url(state=state)
    except RuntimeError as exc:
        return jsonify({"error": "SSO not configured", "detail": str(exc)}), 503

    return redirect(url, code=302)


@bp.get("/callback")
@auth_callback_limit
def callback():
    """Handle Entra redirect: validate OAuth state, complete login, set session."""
    error = request.args.get("error")
    if error:
        detail = request.args.get("error_description") or error
        return jsonify({"error": "Authentication failed", "detail": detail}), 401

    code = request.args.get("code")
    state = request.args.get("state")
    expected_state = session.pop("oauth_state", None)
    post_login_redirect = session.pop("post_login_redirect", None)

    if not code or not state or not expected_state:
        return (
            jsonify(
                {
                    "error": "Authentication failed",
                    "detail": "Missing authorization code or state",
                }
            ),
            400,
        )
    if not secrets.compare_digest(state, expected_state):
        return (
            jsonify({"error": "Authentication failed", "detail": "Invalid state"}),
            400,
        )

    try:
        result = complete_sso_login(
            code,
            tenant_allowlist=current_app.config.get("MS_TENANT_ALLOWLIST") or [],
        )
    except AuthError as exc:
        return jsonify({"error": exc.error, "detail": exc.detail}), exc.status_code

    # Session fixation prevention: new sid before attaching identity
    regenerate_session()
    session.permanent = True
    session["user_id"] = result.user_id
    session["organization_id"] = result.organization_id
    ensure_csrf_token()

    return redirect(safe_post_login_url(post_login_redirect), code=302)


@bp.get("/me")
@auth_me_limit
@login_required
def me():
    """Return the logged-in user and organization (no tokens)."""
    user = db.session.get(User, session["user_id"])
    org = user.organization
    return jsonify(
        {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "organization": {
                "id": org.id,
                "name": org.name,
                "ms_tenant_id": org.ms_tenant_id,
            },
        }
    )


@bp.post("/logout")
@mutation_limit
@login_required
def logout():
    """Destroy the portal session (does not revoke Microsoft SSO)."""
    destroy_session()
    return jsonify({"status": "logged_out"})


@bp.get("/dev-status")
def dev_status():
    """Whether local SSO bypass endpoints are available (never true in production)."""
    allowed = is_dev_login_allowed()
    return jsonify(
        {
            "dev_login_enabled": allowed,
            "warning": (
                "LOCAL ONLY — disable ENABLE_DEV_LOGIN before production"
                if allowed
                else None
            ),
        }
    )


@bp.post("/dev-login")
@mutation_limit
def dev_login():
    """Create a real session as the fixed local-dev user (no Microsoft).

    Requires ENABLE_DEV_LOGIN=true and FLASK_ENV != production.
    CSRF applies like other POSTs. NEVER enable in production.
    """
    if not is_dev_login_allowed():
        return (
            jsonify(
                {
                    "error": "Dev login disabled",
                    "detail": "Set ENABLE_DEV_LOGIN=true only in non-production",
                }
            ),
            404,
        )

    user, org = upsert_dev_identity()
    regenerate_session()
    session.permanent = True
    session["user_id"] = user.id
    session["organization_id"] = org.id
    ensure_csrf_token()

    return jsonify(
        {
            "status": "ok",
            "warning": "LOCAL ONLY — disable ENABLE_DEV_LOGIN before production",
            "user": {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "organization": {
                    "id": org.id,
                    "name": org.name,
                    "ms_tenant_id": org.ms_tenant_id,
                },
            },
        }
    )
