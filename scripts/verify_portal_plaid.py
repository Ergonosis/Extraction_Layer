"""Verify issue #24 Plaid connect / exchange / disconnect / status API.

Usage (from repo root):
  python scripts/verify_portal_plaid.py

Requires Postgres (5434) + Redis (6379). Plaid HTTP calls are mocked.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("MS_CLIENT_ID", "verify-client-id")
os.environ.setdefault("MS_CLIENT_SECRET", "verify-client-secret")
os.environ.setdefault("PLAID_CLIENT_ID", "verify-plaid-client")
os.environ.setdefault("PLAID_SECRET", "verify-plaid-secret")
os.environ.setdefault("PLAID_ENV", "sandbox")

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


def _auth_session(client, user_id: int, org_id: int) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["organization_id"] = org_id


def main() -> int:
    print("Portal Plaid verification (issue #24)")
    from api.app import create_app
    from api.crypto import decrypt_token
    from api.extensions import db
    from api.models import Integration, Organization, PlaidCredential, User

    app = create_app()
    client = app.test_client()

    step("Unauthenticated POST /api/plaid/connect")
    denied = client.post("/api/plaid/connect", headers={"X-CSRF-Token": "x"})
    if denied.status_code not in (401, 403):
        fail(f"expected 401/403, got {denied.status_code}")
    ok(f"blocked without session ({denied.status_code})")

    step("Seed user + org")
    tid = str(uuid.uuid4())
    oid = str(uuid.uuid4())
    with app.app_context():
        org = Organization(name="plaid-verify.org", ms_tenant_id=tid)
        db.session.add(org)
        db.session.flush()
        user = User(
            organization_id=org.id,
            email="plaid@verify.org",
            display_name="Plaid Verify",
            ms_oid=oid,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        org_id = org.id

    _auth_session(client, user_id, org_id)
    csrf = _csrf(client)

    step("CSRF required on POST /api/plaid/connect")
    no_csrf = client.post("/api/plaid/connect")
    if no_csrf.status_code != 403:
        fail(f"expected 403 without CSRF, got {no_csrf.status_code}")
    ok("CSRF rejected bare POST")

    step("Connect creates link_token and sets connecting")
    mock_client = MagicMock()
    mock_client.link_token_create.return_value.to_dict.return_value = {
        "link_token": "link-sandbox-verify",
        "expiration": "2099-01-01T00:00:00Z",
    }

    with patch("api.plaid_bp.service.get_plaid_client", return_value=mock_client):
        resp = client.post(
            "/api/plaid/connect",
            headers={"X-CSRF-Token": csrf},
        )
    if resp.status_code != 200:
        fail(f"connect failed: {resp.status_code} {resp.get_json()}")
    body = resp.get_json()
    if body.get("link_token") != "link-sandbox-verify":
        fail(f"unexpected link_token payload: {body}")
    if body.get("integration", {}).get("status") != "connecting":
        fail(f"expected connecting status: {body}")
    ok("link_token returned; status=connecting")

    step("Exchange rejects invalid public_token")
    bad = client.post(
        "/api/plaid/exchange",
        headers={"X-CSRF-Token": csrf},
        json={"public_token": "not-a-plaid-token"},
    )
    if bad.status_code != 400:
        fail(f"expected 400 for bad token, got {bad.status_code}")
    ok("invalid public_token rejected")

    step("Exchange stores Fernet ciphertext only")
    mock_client.item_public_token_exchange.return_value = {
        "access_token": "access-sandbox-plaintext-secret",
        "item_id": "item-verify-1",
    }
    mock_client.item_get.return_value.to_dict.return_value = {
        "item": {"institution_id": "ins_3"},
    }
    mock_client.institutions_get_by_id.return_value.to_dict.return_value = {
        "institution": {"name": "Chase"},
    }

    with patch("api.plaid_bp.service.get_plaid_client", return_value=mock_client):
        resp = client.post(
            "/api/plaid/exchange",
            headers={"X-CSRF-Token": csrf},
            json={"public_token": "public-sandbox-verify"},
        )
    if resp.status_code != 200:
        fail(f"exchange failed: {resp.status_code} {resp.get_json()}")
    body = resp.get_json()
    if body.get("integration", {}).get("status") != "connected":
        fail(f"expected connected: {body}")
    if body["integration"].get("connected_account") != "Chase":
        fail(f"expected Chase account label: {body}")

    with app.app_context():
        row = Integration.query.filter_by(user_id=user_id, provider="plaid").one()
        cred = PlaidCredential.query.filter_by(integration_id=row.id).one()
        raw = cred.access_token_enc
        if isinstance(raw, memoryview):
            raw = raw.tobytes()
        if b"access-sandbox-plaintext-secret" in raw:
            fail("plaintext access token found in DB blob")
        plain = decrypt_token(bytes(raw))
        if plain != "access-sandbox-plaintext-secret":
            fail("decrypt did not recover access token")
    ok("credential stored encrypted; decrypt round-trip OK")

    step("Status healthy stays connected")
    mock_client.item_get.return_value.to_dict.return_value = {
        "item": {"item_id": "item-verify-1", "institution_id": "ins_3"},
    }
    with patch("api.plaid_bp.service.get_plaid_client", return_value=mock_client):
        resp = client.get("/api/plaid/status")
    if resp.status_code != 200:
        fail(f"status failed: {resp.status_code}")
    if resp.get_json()["integration"]["status"] != "connected":
        fail(f"expected connected: {resp.get_json()}")
    ok("status=connected")

    step("Status surfaces reauth_required on ITEM_LOGIN_REQUIRED")
    from plaid.exceptions import ApiException

    reauth_exc = ApiException(status=400, reason="Bad Request")
    reauth_exc.body = '{"error_code": "ITEM_LOGIN_REQUIRED"}'

    with patch("api.plaid_bp.service.get_plaid_client", return_value=mock_client):
        mock_client.item_get.side_effect = reauth_exc
        resp = client.get("/api/plaid/status")
        mock_client.item_get.side_effect = None
    if resp.status_code != 200:
        fail(f"status failed: {resp.status_code}")
    if resp.get_json()["integration"]["status"] != "reauth_required":
        fail(f"expected reauth_required: {resp.get_json()}")
    ok("status=reauth_required")

    step("Disconnect revokes + deletes credentials")
    mock_client.item_remove.return_value = MagicMock()
    # Restore a connected credential first (status check set reauth)
    with app.app_context():
        row = Integration.query.filter_by(user_id=user_id, provider="plaid").one()
        if row.plaid_credential is None:
            fail("expected credential before disconnect")
        cred_id = row.plaid_credential.id

    with patch("api.plaid_bp.service.get_plaid_client", return_value=mock_client):
        resp = client.post(
            "/api/plaid/disconnect",
            headers={"X-CSRF-Token": csrf},
        )
    if resp.status_code != 200:
        fail(f"disconnect failed: {resp.status_code} {resp.get_json()}")
    body = resp.get_json()
    if body["integration"]["status"] != "not_connected":
        fail(f"expected not_connected: {body}")
    if mock_client.item_remove.call_count < 1:
        fail("expected Plaid item_remove call")

    with app.app_context():
        gone = db.session.get(PlaidCredential, cred_id)
        if gone is not None:
            fail("plaid_credentials row still present")
        row = Integration.query.filter_by(user_id=user_id, provider="plaid").one()
        if row.connected_account is not None or row.connected_at is not None:
            fail("connected_* fields not cleared")
    ok("item_remove called; credential deleted; status=not_connected")

    # Cleanup seed data
    with app.app_context():
        Integration.query.filter_by(user_id=user_id).delete()
        db.session.delete(db.session.get(User, user_id))
        db.session.delete(db.session.get(Organization, org_id))
        db.session.commit()

    print("\nAll Plaid checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
