"""SSO business logic: token exchange, claims, org/user upsert (no Flask HTTP)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from api.auth import msal_client
from api.extensions import db
from api.models import Organization, User

ExchangeFn = Callable[[str], dict]


class AuthError(Exception):
    """Domain failure from SSO completion; routes map this to HTTP."""

    def __init__(self, error: str, detail: str, *, status_code: int = 401):
        super().__init__(detail)
        self.error = error
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class LoginResult:
    user_id: int
    organization_id: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def org_name_from_claims(email: str, tid: str) -> str:
    if email and "@" in email:
        return email.split("@", 1)[1]
    return tid


def _claims_from_msal_result(result: dict) -> tuple[str, str, str, str]:
    """Return (oid, tid, email, name). Discards access/refresh tokens by design."""
    if "error" in result or "id_token_claims" not in result:
        detail = (
            result.get("error_description")
            or result.get("error")
            or "token exchange failed"
        )
        raise AuthError("Authentication failed", str(detail), status_code=401)

    claims = result["id_token_claims"]
    oid = claims.get("oid")
    tid = claims.get("tid")
    email = claims.get("email") or claims.get("preferred_username") or ""
    name = claims.get("name") or email or "User"

    if not oid or not tid:
        raise AuthError(
            "Authentication failed",
            "Missing oid or tid in id_token claims",
            status_code=401,
        )
    return str(oid), str(tid), str(email), str(name)


def upsert_org_and_user(*, oid: str, tid: str, email: str, name: str) -> LoginResult:
    """Create or update organization + user rows; commit and return ids."""
    org = Organization.query.filter_by(ms_tenant_id=tid).one_or_none()
    if org is None:
        org = Organization(name=org_name_from_claims(email, tid), ms_tenant_id=tid)
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
    return LoginResult(user_id=user.id, organization_id=org.id)


def complete_sso_login(
    code: str,
    *,
    tenant_allowlist: Sequence[str] | None = None,
    exchange_auth_code: ExchangeFn | None = None,
) -> LoginResult:
    """Exchange auth code, enforce allowlist, upsert identity. No session/HTTP."""
    exchange = exchange_auth_code or msal_client.exchange_auth_code
    try:
        result = exchange(code)
    except RuntimeError as exc:
        raise AuthError("Authentication failed", str(exc), status_code=401) from exc

    oid, tid, email, name = _claims_from_msal_result(result or {})

    allowlist = list(tenant_allowlist or [])
    if allowlist and tid not in allowlist:
        raise AuthError(
            "Tenant not allowed",
            "This Microsoft tenant is not permitted to sign in",
            status_code=403,
        )

    return upsert_org_and_user(oid=oid, tid=tid, email=email, name=name)
