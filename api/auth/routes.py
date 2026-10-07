"""Microsoft Entra SSO auth routes (multi-tenant)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from flask import current_app, jsonify, redirect, request, session

from api.auth import bp
from api.auth.decorators import login_required
from api.auth import msal_client
from api.auth.session_utils import regenerate_session, safe_post_login_url
from api.extensions import db
from api.middleware import ensure_csrf_token
from api.models import Organization, User
from api.rate_limit import (
    auth_callback_limit,
    auth_login_limit,
    auth_me_limit,
    mutation_limit,
)


def _utcnow():
    return datetime.now(timezone.utc)


def _org_name_from_claims(email: str, tid: str) -> str:
    if email and "@" in email:
        return email.split("@", 1)[1]
    return tid


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
    """Handle Entra redirect: exchange code, upsert org/user, establish session."""
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
        result = msal_client.exchange_auth_code(code)
    except RuntimeError as exc:
        return jsonify({"error": "Authentication failed", "detail": str(exc)}), 401

    if "error" in result or "id_token_claims" not in result:
        detail = result.get("error_description") or result.get("error") or "token exchange failed"
        return jsonify({"error": "Authentication failed", "detail": detail}), 401

    claims = result["id_token_claims"]
    # Intentionally discard access_token / refresh_token — SSO is identity only.
    oid = claims.get("oid")
    tid = claims.get("tid")
    email = (
        claims.get("email")
        or claims.get("preferred_username")
        or ""
    )
    name = claims.get("name") or email or "User"

    if not oid or not tid:
        return (
            jsonify(
                {
                    "error": "Authentication failed",
                    "detail": "Missing oid or tid in id_token claims",
                }
            ),
            401,
        )

    allowlist = current_app.config.get("MS_TENANT_ALLOWLIST") or []
    if allowlist and tid not in allowlist:
        return (
            jsonify(
                {
                    "error": "Tenant not allowed",
                    "detail": "This Microsoft tenant is not permitted to sign in",
                }
            ),
            403,
        )

    org = Organization.query.filter_by(ms_tenant_id=tid).one_or_none()
    if org is None:
        org = Organization(
            name=_org_name_from_claims(email, tid),
            ms_tenant_id=tid,
        )
        db.session.add(org)
        db.session.flush()

    user = User.query.filter_by(organization_id=org.id, ms_oid=oid).one_or_none()
    if user is None:
        user = User(
            organization_id=org.id,
            email=email or f"{oid}@{tid}",
            display_name=name,
            ms_oid=oid,
            last_login=_utcnow(),
        )
        db.session.add(user)
    else:
        if email:
            user.email = email
        if name:
            user.display_name = name
        user.last_login = _utcnow()

    db.session.commit()

    # Session fixation prevention: new sid before attaching identity
    regenerate_session()
    session.permanent = True
    session["user_id"] = user.id
    session["organization_id"] = org.id
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
    session.clear()
    session.modified = True
    return jsonify({"status": "logged_out"})
