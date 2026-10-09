"""Verify issue #26 MS Graph permission selector + incremental consent.

Usage (from repo root):
  python scripts/verify_portal_msgraph_permissions.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("MS_CLIENT_ID", "verify-client-id")
os.environ.setdefault("MS_CLIENT_SECRET", "verify-client-secret")

from cryptography.fernet import Fernet

os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())


class CheckFailed(Exception):
    pass


def step(name: str) -> None:
    print(f"\n==> {name}")


def ok(msg: str) -> None:
    print(f"  PASS: {msg}")


def fail(msg: str) -> None:
    raise CheckFailed(msg)


def _csrf(client) -> str:
    resp = client.get("/api/auth/csrf-token")
    if resp.status_code != 200:
        fail(f"csrf-token failed: {resp.status_code}")
    return resp.get_json()["csrf_token"]


def main() -> int:
    print("Portal MS Graph permissions verification (issue #26)")
    from api.app import create_app
    from api.crypto import encrypt_token
    from api.extensions import db
    from api.models import (
        Integration,
        MsGraphCredential,
        MsGraphPermission,
        Organization,
        User,
    )

    app = create_app()
    client = app.test_client()

    step("Seed connected MS Graph user")
    tid = str(uuid.uuid4())
    oid = str(uuid.uuid4())
    with app.app_context():
        org = Organization(name="perms-verify.org", ms_tenant_id=tid)
        db.session.add(org)
        db.session.flush()
        user = User(
            organization_id=org.id,
            email="perms@verify.org",
            display_name="Perms Verify",
            ms_oid=oid,
        )
        db.session.add(user)
        db.session.flush()
        integration = Integration(
            user_id=user.id,
            organization_id=org.id,
            provider="msgraph",
            status="connected",
            connected_account="perms@verify.org",
        )
        db.session.add(integration)
        db.session.flush()
        cred = MsGraphCredential(
            integration_id=integration.id,
            access_token_enc=encrypt_token("access-seed"),
            refresh_token_enc=encrypt_token("refresh-seed"),
            scopes_granted=["User.Read"],
        )
        db.session.add(cred)
        for scope, active in (
            ("User.Read", True),
            ("Mail.Read", False),
            ("Calendars.Read", False),
            ("Files.Read", False),
        ):
            db.session.add(
                MsGraphPermission(
                    integration_id=integration.id,
                    scope=scope,
                    is_active=active,
                )
            )
        db.session.commit()
        user_id = user.id
        org_id = org.id
        integration_id = integration.id

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["organization_id"] = org_id

    step("GET /permissions/available merges is_active")
    resp = client.get("/api/msgraph/permissions/available")
    if resp.status_code != 200:
        fail(f"available failed: {resp.status_code}")
    body = resp.get_json()
    by_scope = {p["scope"]: p for p in body["permissions"]}
    if set(by_scope) != {"User.Read", "Mail.Read", "Calendars.Read", "Files.Read"}:
        fail(f"unexpected catalog: {by_scope.keys()}")
    if not by_scope["User.Read"]["is_active"]:
        fail("User.Read should be active")
    if by_scope["Mail.Read"]["is_active"]:
        fail("Mail.Read should be inactive")
    if not body.get("connected"):
        fail("expected connected=true")
    ok("allowlist + is_active merged")

    csrf = _csrf(client)

    step("PUT rejects unsupported scopes")
    bad = client.put(
        "/api/msgraph/permissions",
        headers={"X-CSRF-Token": csrf},
        json={"scopes": ["User.Read", "Mail.Send"]},
    )
    if bad.status_code != 400:
        fail(f"expected 400, got {bad.status_code}")
    ok("unsupported scopes rejected")

    step("PUT toggles already-granted scopes without consent")
    resp = client.put(
        "/api/msgraph/permissions",
        headers={"X-CSRF-Token": csrf},
        json={"scopes": []},
    )
    if resp.status_code != 200:
        fail(f"put failed: {resp.status_code} {resp.get_json()}")
    body = resp.get_json()
    if body.get("consent_required"):
        fail("empty toggle should not require consent")
    perms = {p["scope"]: p["is_active"] for p in body["integration"]["permissions"]}
    if any(perms.values()):
        fail(f"expected all inactive: {perms}")
    ok("deactivate all without redirect")

    # Re-enable User.Read (already granted)
    resp = client.put(
        "/api/msgraph/permissions",
        headers={"X-CSRF-Token": csrf},
        json={"scopes": ["User.Read"]},
    )
    if resp.status_code != 200 or resp.get_json().get("consent_required"):
        fail(f"re-enable User.Read failed: {resp.get_json()}")
    ok("re-activate granted scope without redirect")

    step("PUT new scopes returns consent_required + redirect_url")
    with patch(
        "api.msgraph_bp.msal_graph.authorization_url",
        return_value="https://login.microsoftonline.com/mock/incremental",
    ) as auth_mock:
        resp = client.put(
            "/api/msgraph/permissions",
            headers={"X-CSRF-Token": csrf},
            json={"scopes": ["User.Read", "Mail.Read"]},
        )
    if resp.status_code != 200:
        fail(f"incremental put failed: {resp.status_code} {resp.get_json()}")
    body = resp.get_json()
    if not body.get("consent_required"):
        fail(f"expected consent_required: {body}")
    if body.get("redirect_url") != "https://login.microsoftonline.com/mock/incremental":
        fail(f"bad redirect_url: {body}")
    if body["integration"]["status"] != "connecting":
        fail(f"expected connecting: {body}")
    # Only new scopes should be requested from MSAL
    call_kwargs = auth_mock.call_args.kwargs
    if "Mail.Read" not in call_kwargs.get("scopes", []):
        fail(f"expected Mail.Read in MSAL scopes: {call_kwargs}")
    if "User.Read" in call_kwargs.get("scopes", []):
        fail(f"User.Read already granted should not be re-requested: {call_kwargs}")
    ok("incremental consent redirect")

    with client.session_transaction() as sess:
        state = sess.get("msgraph_oauth_state")
        if not state:
            fail("missing oauth state after incremental put")
        if not sess.get("msgraph_incremental"):
            fail("incremental flag missing")

    step("Callback merges new scopes after incremental consent")
    mock_result = {
        "access_token": "access-after-incremental",
        "refresh_token": "refresh-after-incremental",
        "expires_in": 3600,
        "scope": "Mail.Read offline_access",
        "id_token_claims": {"email": "perms@verify.org"},
    }
    with patch(
        "api.msgraph_bp.msal_graph.exchange_auth_code",
        return_value=mock_result,
    ):
        resp = client.get(
            f"/api/msgraph/callback?code=inc-code&state={state}",
            follow_redirects=False,
        )
    if resp.status_code not in (302, 303):
        fail(f"callback expected redirect, got {resp.status_code}")

    with app.app_context():
        row = db.session.get(Integration, integration_id)
        if row.status != "connected":
            fail(f"expected connected, got {row.status}")
        granted = set(row.ms_graph_credential.scopes_granted or [])
        if "User.Read" not in granted or "Mail.Read" not in granted:
            fail(f"expected merged grants: {granted}")
        active = {
            p.scope: p.is_active
            for p in MsGraphPermission.query.filter_by(integration_id=row.id)
        }
        if not active.get("User.Read") or not active.get("Mail.Read"):
            fail(f"expected both active: {active}")
    ok("incremental callback merged scopes")

    # Cleanup
    with app.app_context():
        MsGraphPermission.query.filter_by(integration_id=integration_id).delete()
        MsGraphCredential.query.filter_by(integration_id=integration_id).delete()
        Integration.query.filter_by(user_id=user_id).delete()
        db.session.delete(db.session.get(User, user_id))
        db.session.delete(db.session.get(Organization, org_id))
        db.session.commit()

    print("\nAll MS Graph permission checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
