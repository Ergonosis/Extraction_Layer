"""Verify issue #25 MS Graph connect / disconnect / status API.

Usage (from repo root):
  python scripts/verify_portal_msgraph.py

Requires Postgres (5434) + Redis (6379). MSAL calls are mocked.
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
    print("Portal MS Graph verification (issue #25)")
    from api.app import create_app
    from api.crypto import decrypt_token
    from api.extensions import db
    from api.models import Integration, MsGraphCredential, MsGraphPermission, Organization, User

    app = create_app()
    client = app.test_client()

    step("Unauthenticated POST /api/msgraph/connect")
    denied = client.post("/api/msgraph/connect", headers={"X-CSRF-Token": "x"})
    if denied.status_code not in (401, 403):
        fail(f"expected 401/403, got {denied.status_code}")
    ok(f"blocked without session ({denied.status_code})")

    step("Seed user + org")
    tid = str(uuid.uuid4())
    oid = str(uuid.uuid4())
    with app.app_context():
        org = Organization(name="msgraph-verify.org", ms_tenant_id=tid)
        db.session.add(org)
        db.session.flush()
        user = User(
            organization_id=org.id,
            email="msgraph@verify.org",
            display_name="MS Graph Verify",
            ms_oid=oid,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        org_id = org.id

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["organization_id"] = org_id

    csrf = _csrf(client)

    step("Reject unsupported scopes")
    bad = client.post(
        "/api/msgraph/connect",
        headers={"X-CSRF-Token": csrf},
        json={"scopes": ["User.Read", "Mail.ReadWrite"]},
    )
    if bad.status_code != 400:
        fail(f"expected 400 for bad scopes, got {bad.status_code} {bad.get_json()}")
    ok("unsupported scopes rejected")

    step("Connect returns authorize_url and sets connecting")
    with patch(
        "api.msgraph_bp.msal_graph.authorization_url",
        return_value="https://login.microsoftonline.com/mock/authorize",
    ):
        resp = client.post(
            "/api/msgraph/connect",
            headers={"X-CSRF-Token": csrf},
            json={"scopes": ["User.Read", "Mail.Read"]},
        )
    if resp.status_code != 200:
        fail(f"connect failed: {resp.status_code} {resp.get_json()}")
    body = resp.get_json()
    if "authorize_url" not in body:
        fail(f"missing authorize_url: {body}")
    if body.get("integration", {}).get("status") != "connecting":
        fail(f"expected connecting: {body}")
    if set(body.get("scopes") or []) != {"User.Read", "Mail.Read"}:
        fail(f"unexpected scopes: {body}")
    ok("authorize_url + connecting")

    with client.session_transaction() as sess:
        state = sess.get("msgraph_oauth_state")
        if not state:
            fail("oauth state missing from session")

    step("Callback stores Fernet ciphertext only")
    mock_result = {
        "access_token": "access-graph-plaintext-secret",
        "refresh_token": "refresh-graph-plaintext-secret",
        "expires_in": 3600,
        "scope": "User.Read Mail.Read offline_access",
        "id_token_claims": {
            "email": "user@contoso.com",
            "preferred_username": "user@contoso.com",
        },
    }
    with patch(
        "api.msgraph_bp.msal_graph.exchange_auth_code",
        return_value=mock_result,
    ):
        resp = client.get(
            f"/api/msgraph/callback?code=mock-code&state={state}",
            follow_redirects=False,
        )
    if resp.status_code not in (302, 303):
        fail(f"callback expected redirect, got {resp.status_code} {resp.get_data(as_text=True)[:200]}")

    with app.app_context():
        row = Integration.query.filter_by(user_id=user_id, provider="msgraph").one()
        if row.status != "connected":
            fail(f"expected connected, got {row.status}")
        if row.connected_account != "user@contoso.com":
            fail(f"unexpected account: {row.connected_account}")
        cred = MsGraphCredential.query.filter_by(integration_id=row.id).one()
        raw_a = bytes(cred.access_token_enc)
        raw_r = bytes(cred.refresh_token_enc)
        if b"access-graph-plaintext-secret" in raw_a or b"refresh-graph-plaintext-secret" in raw_r:
            fail("plaintext tokens found in DB")
        if decrypt_token(raw_a) != "access-graph-plaintext-secret":
            fail("access token decrypt mismatch")
        if decrypt_token(raw_r) != "refresh-graph-plaintext-secret":
            fail("refresh token decrypt mismatch")
        perms = {
            p.scope: p.is_active
            for p in MsGraphPermission.query.filter_by(integration_id=row.id).all()
        }
        if not perms.get("User.Read") or not perms.get("Mail.Read"):
            fail(f"expected active User.Read/Mail.Read: {perms}")
        if perms.get("Calendars.Read") or perms.get("Files.Read"):
            fail(f"unexpected active calendar/files: {perms}")
    ok("encrypted credentials + permission rows")

    step("Status refresh re-encrypts tokens")
    csrf = _csrf(client)
    refresh_result = {
        "access_token": "access-graph-rotated",
        "refresh_token": "refresh-graph-rotated",
        "expires_in": 3600,
        "scope": "User.Read Mail.Read offline_access",
    }
    with patch(
        "api.msgraph_bp.msal_graph.refresh_access_token",
        return_value=refresh_result,
    ):
        resp = client.get("/api/msgraph/status")
    if resp.status_code != 200:
        fail(f"status failed: {resp.status_code}")
    if resp.get_json()["integration"]["status"] != "connected":
        fail(f"expected connected: {resp.get_json()}")
    with app.app_context():
        row = Integration.query.filter_by(user_id=user_id, provider="msgraph").one()
        cred = row.ms_graph_credential
        if decrypt_token(bytes(cred.access_token_enc)) != "access-graph-rotated":
            fail("access token not rotated")
    ok("status refreshed tokens")

    step("Status surfaces reauth_required on refresh failure")
    with patch(
        "api.msgraph_bp.msal_graph.refresh_access_token",
        return_value={"error": "invalid_grant", "error_description": "expired"},
    ):
        resp = client.get("/api/msgraph/status")
    if resp.status_code != 200:
        fail(f"status failed: {resp.status_code}")
    if resp.get_json()["integration"]["status"] != "reauth_required":
        fail(f"expected reauth_required: {resp.get_json()}")
    ok("status=reauth_required")

    step("Disconnect deletes credentials without needing decrypt")
    csrf = _csrf(client)
    resp = client.post(
        "/api/msgraph/disconnect",
        headers={"X-CSRF-Token": csrf},
    )
    if resp.status_code != 200:
        fail(f"disconnect failed: {resp.status_code} {resp.get_json()}")
    if resp.get_json()["integration"]["status"] != "not_connected":
        fail(f"expected not_connected: {resp.get_json()}")
    with app.app_context():
        row = Integration.query.filter_by(user_id=user_id, provider="msgraph").one()
        if row.ms_graph_credential is not None:
            fail("credential still present")
        left = MsGraphPermission.query.filter_by(integration_id=row.id).count()
        if left != 0:
            fail(f"permissions still present: {left}")
    ok("credentials + permissions cleared")

    with app.app_context():
        Integration.query.filter_by(user_id=user_id).delete()
        db.session.delete(db.session.get(User, user_id))
        db.session.delete(db.session.get(Organization, org_id))
        db.session.commit()

    print("\nAll MS Graph checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
