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
SESSION_DESIRED_ACTIVE_KEY = "msgraph_desired_active"
SESSION_INCREMENTAL_KEY = "msgraph_incremental"

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


def _parse_scope_list(requested: object) -> list[str]:
    """Parse and allowlist-check scopes; may return empty."""
    allow = _allowlist()
    if requested is None:
        return []

    if isinstance(requested, str):
        items = [s.strip() for s in requested.split() if s.strip()]
    elif isinstance(requested, (list, tuple)):
        items = [str(s).strip() for s in requested if str(s).strip()]
    else:
        raise MsGraphServiceError("scopes must be a list of strings", status_code=400)

    items = [s for s in items if s != OFFLINE_ACCESS]
    unsupported = [s for s in items if s not in allow]
    if unsupported:
        raise MsGraphServiceError(
            f"Unsupported scopes: {', '.join(unsupported)}",
            status_code=400,
        )
    return [s for s in MS_GRAPH_SCOPE_LABELS if s in set(items)]


def validate_requested_scopes(requested: object) -> list[str]:
    """Validate against hardcoded allowlist; default to full allowlist if empty."""
    if requested is None or requested == [] or requested == "":
        return [s for s in MS_GRAPH_SCOPE_LABELS]
    items = _parse_scope_list(requested)
    if not items:
        raise MsGraphServiceError("At least one allowlisted scope is required", status_code=400)
    return items


def validate_permission_scopes(requested: object) -> list[str]:
    """Validate allowlist scopes for PUT permissions (empty = deactivate all)."""
    if requested is None:
        raise MsGraphServiceError("scopes is required", status_code=400)
    return _parse_scope_list(requested)


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
    session.pop(SESSION_DESIRED_ACTIVE_KEY, None)
    session.pop(SESSION_INCREMENTAL_KEY, None)

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
    requested = session.pop(SESSION_SCOPES_KEY, None) or [s for s in MS_GRAPH_SCOPE_LABELS]
    desired_active = session.pop(SESSION_DESIRED_ACTIVE_KEY, None)
    incremental = bool(session.pop(SESSION_INCREMENTAL_KEY, False))

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

    cred = integration.ms_graph_credential
    previous = list(cred.scopes_granted or []) if cred is not None else []

    # Encrypt immediately — plaintext must never hit the DB.
    access_enc = encrypt_token(access_token)
    if refresh_token:
        refresh_enc = encrypt_token(refresh_token)
    elif incremental and cred is not None and cred.refresh_token_enc:
        # Incremental consent may omit a new refresh_token — keep the existing blob.
        refresh_enc = cred.refresh_token_enc
    else:
        integration.status = "error"
        integration.updated_at = _utcnow()
        db.session.commit()
        raise MsGraphServiceError(
            "Microsoft did not return a refresh_token (ensure offline_access)",
            status_code=502,
        )

    expiry = _parse_expiry(result)

    raw_scopes = result.get("scope") or ""
    from_token = [
        s
        for s in str(raw_scopes).split()
        if s in _allowlist()
    ]

    if incremental:
        granted = [
            s
            for s in MS_GRAPH_SCOPE_LABELS
            if s in set(previous) | set(from_token) | set(requested)
        ]
    else:
        granted = from_token or list(requested)

    if cred is None:
        cred = MsGraphCredential(integration_id=integration.id)
        db.session.add(cred)

    cred.access_token_enc = access_enc
    cred.refresh_token_enc = refresh_enc
    cred.token_expiry = expiry
    cred.scopes_granted = granted

    # Desired active set: explicit from incremental PUT, else all granted.
    active = (
        [s for s in MS_GRAPH_SCOPE_LABELS if s in set(desired_active or [])]
        if desired_active is not None
        else granted
    )
    _upsert_permissions(integration, active)

    account = _account_from_result(result)
    integration.status = "connected"
    if account:
        integration.connected_account = account
    if integration.connected_at is None:
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
    """Abandon connecting / incremental consent."""
    integration = _msgraph_integration(user_id=user_id, organization_id=organization_id)
    session.pop(SESSION_STATE_KEY, None)
    session.pop(SESSION_SCOPES_KEY, None)
    session.pop(SESSION_DESIRED_ACTIVE_KEY, None)
    session.pop(SESSION_INCREMENTAL_KEY, None)

    if integration.status == "connecting":
        # Incremental consent leaves credentials in place — restore connected.
        if integration.ms_graph_credential is not None:
            integration.status = "connected"
        else:
            integration.status = "not_connected"
        integration.updated_at = _utcnow()
        db.session.commit()

    return {"integration": serialize_integration(integration)}


def list_available_permissions(*, user_id: int, organization_id: int) -> dict:
    """Allowlist catalog with is_active merged from the user's permission rows."""
    integration = _msgraph_integration(user_id=user_id, organization_id=organization_id)
    by_scope = {p.scope: p for p in (integration.ms_graph_permissions or [])}
    permissions = []
    for scope, label in MS_GRAPH_SCOPE_LABELS.items():
        row = by_scope.get(scope)
        permissions.append(
            {
                "scope": scope,
                "label": label,
                "is_active": bool(row.is_active) if row else False,
            }
        )
    return {
        "permissions": permissions,
        "connected": integration.status == "connected"
        and integration.ms_graph_credential is not None,
    }


def update_permissions(
    *,
    user_id: int,
    organization_id: int,
    requested_scopes: object,
) -> dict:
    """Toggle is_active for granted scopes, or start incremental consent for new ones."""
    desired_active = validate_permission_scopes(requested_scopes)
    integration = _msgraph_integration(user_id=user_id, organization_id=organization_id)
    cred = integration.ms_graph_credential

    if cred is None or integration.status not in ("connected", "reauth_required", "connecting"):
        raise MsGraphServiceError(
            "Connect Microsoft Graph before updating permissions",
            status_code=400,
        )

    granted = set(cred.scopes_granted or [])
    to_consent = [s for s in desired_active if s not in granted]

    if to_consent:
        try:
            state = secrets.token_urlsafe(32)
            url = msal_graph.authorization_url(
                state=state,
                scopes=_scopes_for_msal(to_consent),
                prompt="consent",
            )
        except RuntimeError as exc:
            raise MsGraphServiceError(str(exc), status_code=503) from exc

        session.permanent = True
        session[SESSION_STATE_KEY] = state
        session[SESSION_SCOPES_KEY] = to_consent
        session[SESSION_DESIRED_ACTIVE_KEY] = desired_active
        session[SESSION_INCREMENTAL_KEY] = True

        integration.status = "connecting"
        integration.updated_at = _utcnow()
        db.session.commit()

        return {
            "consent_required": True,
            "redirect_url": url,
            "integration": serialize_integration(integration),
        }

    # All desired scopes already granted (or only removals) — local toggle only.
    _upsert_permissions(integration, desired_active)
    integration.updated_at = _utcnow()
    if integration.status == "connecting":
        integration.status = "connected"
    db.session.commit()
    db.session.refresh(integration)

    return {
        "consent_required": False,
        "integration": serialize_integration(integration),
    }


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
