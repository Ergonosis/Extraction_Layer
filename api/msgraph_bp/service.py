"""MS Graph delegated connect / disconnect / status business logic."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, session

from api.crypto import decrypt_token, encrypt_token
from api.extensions import db
from api.integrations.constants import MS_GRAPH_SCOPE_LABELS
from api.integrations.service import ensure_provider_rows, serialize_integration
from api.models import Integration, MsGraphCredential, MsGraphPermission
from api.msgraph_bp import msal_graph

logger = logging.getLogger(__name__)

SESSION_STATE_KEY = "msgraph_oauth_state"
SESSION_SCOPES_KEY = "msgraph_requested_scopes"

# Always request offline_access so we receive a refresh token.
OFFLINE_ACCESS = "offline_access"


class MsGraphServiceError(Exception):
    """Domain error with HTTP-friendly message + status."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _allowlist() -> frozenset[str]:
    return frozenset(MS_GRAPH_SCOPE_LABELS.keys())


def _msgraph_integration(*, user_id: int, organization_id: int) -> Integration:
    rows = ensure_provider_rows(user_id=user_id, organization_id=organization_id)
    for row in rows:
        if row.provider == "msgraph":
            return row
    raise MsGraphServiceError("MS Graph integration row missing", status_code=500)


def validate_requested_scopes(requested: object) -> list[str]:
    """Validate against hardcoded allowlist; default to full allowlist if empty."""
    allow = _allowlist()
    if requested is None or requested == [] or requested == "":
        return sorted(allow)

    if isinstance(requested, str):
        items = [s.strip() for s in requested.split() if s.strip()]
    elif isinstance(requested, (list, tuple)):
        items = [str(s).strip() for s in requested if str(s).strip()]
    else:
        raise MsGraphServiceError("scopes must be a list of strings", status_code=400)

    # offline_access is added by us; strip if client sent it
    items = [s for s in items if s != OFFLINE_ACCESS]
    unsupported = [s for s in items if s not in allow]
    if unsupported:
        raise MsGraphServiceError(
            f"Unsupported scopes: {', '.join(unsupported)}",
            status_code=400,
        )
    if not items:
        raise MsGraphServiceError("At least one allowlisted scope is required", status_code=400)
    # Preserve stable order from allowlist definition
    return [s for s in MS_GRAPH_SCOPE_LABELS if s in set(items)]


def _scopes_for_msal(delegated: list[str]) -> list[str]:
    return list(delegated) + [OFFLINE_ACCESS]


def start_connect(
    *,
    user_id: int,
    organization_id: int,
    requested_scopes: object = None,
) -> dict:
    """Validate scopes, set connecting, store OAuth state, return authorize_url."""
    delegated = validate_requested_scopes(requested_scopes)
    integration = _msgraph_integration(user_id=user_id, organization_id=organization_id)

    try:
        state = secrets.token_urlsafe(32)
        url = msal_graph.authorization_url(
            state=state,
            scopes=_scopes_for_msal(delegated),
        )
    except RuntimeError as exc:
        raise MsGraphServiceError(str(exc), status_code=503) from exc

    session.permanent = True
    session[SESSION_STATE_KEY] = state
    session[SESSION_SCOPES_KEY] = delegated

    integration.status = "connecting"
    integration.updated_at = _utcnow()
    db.session.commit()

    return {
        "authorize_url": url,
        "scopes": delegated,
        "integration": serialize_integration(integration),
    }


def _parse_expiry(result: dict) -> datetime | None:
    expires_in = result.get("expires_in")
    if expires_in is None:
        return None
    try:
        return _utcnow() + timedelta(seconds=int(expires_in))
    except (TypeError, ValueError):
        return None


def _upsert_permissions(integration: Integration, granted: list[str]) -> None:
    """Ensure allowlist permission rows exist; mark granted ones active."""
    granted_set = set(granted)
    by_scope = {p.scope: p for p in (integration.ms_graph_permissions or [])}
    now = _utcnow()
    for scope in MS_GRAPH_SCOPE_LABELS:
        row = by_scope.get(scope)
        active = scope in granted_set
        if row is None:
            row = MsGraphPermission(
                integration_id=integration.id,
                scope=scope,
                is_active=active,
                granted_at=now if active else None,
            )
            db.session.add(row)
        else:
            row.is_active = active
            if active and row.granted_at is None:
                row.granted_at = now
            if not active:
                row.granted_at = None


def _account_from_result(result: dict) -> str | None:
    claims = result.get("id_token_claims") or {}
    email = claims.get("email") or claims.get("preferred_username") or claims.get("upn")
    if email:
        return str(email)
    return None


def complete_callback(*, code: str, state: str) -> dict:
    """Exchange code, encrypt tokens, upsert credentials + permissions."""
    expected = session.pop(SESSION_STATE_KEY, None)
    requested = session.pop(SESSION_SCOPES_KEY, None) or sorted(_allowlist())

    if not expected or not state or not secrets.compare_digest(str(state), str(expected)):
        raise MsGraphServiceError("Invalid OAuth state", status_code=400)
    if not code:
        raise MsGraphServiceError("Missing authorization code", status_code=400)

    user_id = session.get("user_id")
    organization_id = session.get("organization_id")
    if not user_id or not organization_id:
        raise MsGraphServiceError("Authentication required", status_code=401)

    integration = _msgraph_integration(user_id=user_id, organization_id=organization_id)

    try:
        result = msal_graph.exchange_auth_code(
            code=code,
            scopes=_scopes_for_msal(list(requested)),
        )
    except RuntimeError as exc:
        raise MsGraphServiceError(str(exc), status_code=503) from exc

    if "error" in result or "access_token" not in result:
        detail = result.get("error_description") or result.get("error") or "token exchange failed"
        integration.status = "error"
        integration.updated_at = _utcnow()
        db.session.commit()
        raise MsGraphServiceError(str(detail), status_code=401)

    access_token = result["access_token"]
    refresh_token = result.get("refresh_token")
    if not refresh_token:
        integration.status = "error"
        integration.updated_at = _utcnow()
        db.session.commit()
        raise MsGraphServiceError(
            "Microsoft did not return a refresh_token (ensure offline_access)",
            status_code=502,
        )

    # Encrypt immediately — plaintext must never hit the DB.
    access_enc = encrypt_token(access_token)
    refresh_enc = encrypt_token(refresh_token)
    expiry = _parse_expiry(result)

    raw_scopes = result.get("scope") or ""
    granted = [
        s
        for s in str(raw_scopes).split()
        if s in _allowlist()
    ]
    if not granted:
        granted = list(requested)

    cred = integration.ms_graph_credential
    if cred is None:
        cred = MsGraphCredential(integration_id=integration.id)
        db.session.add(cred)

    cred.access_token_enc = access_enc
    cred.refresh_token_enc = refresh_enc
    cred.token_expiry = expiry
    cred.scopes_granted = granted

    _upsert_permissions(integration, granted)

    account = _account_from_result(result)
    integration.status = "connected"
    integration.connected_account = account
    integration.connected_at = _utcnow()
    integration.updated_at = _utcnow()
    db.session.commit()
    db.session.refresh(integration)

    return {"integration": serialize_integration(integration)}


def disconnect(*, user_id: int, organization_id: int) -> dict:
    """Delete credentials without decrypting; clear permissions; set not_connected."""
    integration = _msgraph_integration(user_id=user_id, organization_id=organization_id)

    cred = integration.ms_graph_credential
    if cred is not None:
        db.session.delete(cred)

    for perm in list(integration.ms_graph_permissions or []):
        db.session.delete(perm)

    integration.status = "not_connected"
    integration.connected_account = None
    integration.connected_at = None
    integration.updated_at = _utcnow()
    db.session.commit()

    return {"integration": serialize_integration(integration)}


def cancel_connect(*, user_id: int, organization_id: int) -> dict:
    """Abandon connecting when no credential exists."""
    integration = _msgraph_integration(user_id=user_id, organization_id=organization_id)
    session.pop(SESSION_STATE_KEY, None)
    session.pop(SESSION_SCOPES_KEY, None)

    if integration.ms_graph_credential is not None:
        return {"integration": serialize_integration(integration)}

    if integration.status == "connecting":
        integration.status = "not_connected"
        integration.updated_at = _utcnow()
        db.session.commit()

    return {"integration": serialize_integration(integration)}


def check_status(*, user_id: int, organization_id: int) -> dict:
    """Refresh tokens via MSAL; re-encrypt on success; reauth_required on failure."""
    integration = _msgraph_integration(user_id=user_id, organization_id=organization_id)
    cred = integration.ms_graph_credential

    if cred is None:
        if integration.status not in ("not_connected", "connecting", "error"):
            integration.status = "not_connected"
            integration.connected_account = None
            integration.connected_at = None
            integration.updated_at = _utcnow()
            db.session.commit()
        return {"integration": serialize_integration(integration)}

    scopes = list(cred.scopes_granted or []) or sorted(_allowlist())
    try:
        refresh_plain = decrypt_token(cred.refresh_token_enc)
        result = msal_graph.refresh_access_token(
            refresh_token=refresh_plain,
            scopes=_scopes_for_msal(scopes),
        )
    except RuntimeError as exc:
        raise MsGraphServiceError(str(exc), status_code=503) from exc
    except Exception:
        logger.exception("MS Graph status refresh failed")
        integration.status = "reauth_required"
        integration.updated_at = _utcnow()
        db.session.commit()
        return {"integration": serialize_integration(integration)}

    if "error" in result or "access_token" not in result:
        logger.warning(
            "MS Graph refresh error: %s",
            result.get("error_description") or result.get("error"),
        )
        integration.status = "reauth_required"
        integration.updated_at = _utcnow()
        db.session.commit()
        return {"integration": serialize_integration(integration)}

    # Re-encrypt rotated tokens
    cred.access_token_enc = encrypt_token(result["access_token"])
    if result.get("refresh_token"):
        cred.refresh_token_enc = encrypt_token(result["refresh_token"])
    cred.token_expiry = _parse_expiry(result)

    raw_scopes = result.get("scope") or ""
    granted = [s for s in str(raw_scopes).split() if s in _allowlist()]
    if granted:
        cred.scopes_granted = granted
        _upsert_permissions(integration, granted)

    if integration.status != "connected":
        integration.status = "connected"
    integration.updated_at = _utcnow()
    db.session.commit()

    return {"integration": serialize_integration(integration)}


def portal_post_connect_url() -> str:
    base = (current_app.config.get("PORTAL_URL") or "http://localhost:5175").rstrip("/")
    return f"{base}/connections"
