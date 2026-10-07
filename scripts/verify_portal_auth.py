"""Verify issue #21 Microsoft SSO backend (mocked MSAL + real DB/Redis).

Usage (from repo root):
  python scripts/verify_portal_auth.py

Requires: extraction-portal-postgres (5434), extraction-portal-redis (6379).
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Dummy Entra app credentials for local verification (MSAL is mocked)
os.environ.setdefault("MS_CLIENT_ID", "verify-client-id")
os.environ.setdefault("MS_CLIENT_SECRET", "verify-client-secret")

REDIS_CONTAINER = "extraction-portal-redis"
POSTGRES_CONTAINER = "extraction-portal-postgres"


class CheckFailed(Exception):
    pass


def step(name: str) -> None:
    print(f"\n==> {name}")


def ok(msg: str) -> None:
    print(f"  PASS: {msg}")


def fail(msg: str) -> None:
    raise CheckFailed(msg)


def check_infra() -> None:
    step("Docker Postgres + Redis")
    for name, port in (
        (POSTGRES_CONTAINER, "5434"),
        (REDIS_CONTAINER, "6379"),
    ):
        ps = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"name=^{name}$",
                "--format",
                "{{.Names}}\t{{.Ports}}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        line = (ps.stdout or "").strip()
        if name not in line:
            fail(f"{name} is not running")
        if port not in line:
            fail(f"expected host port {port} for {name}, got: {line}")
        ok(line)


def _sid_from_client(client) -> str | None:
    with client.session_transaction() as sess:
        return getattr(sess, "sid", None) or sess.get("_sid")


def check_auth_flow() -> None:
    step("SSO login/callback/me/logout (mocked MSAL)")
    from api.app import create_app
    from api.extensions import db
    from api.models import Organization, User

    tid_a = str(uuid.uuid4())
    tid_b = str(uuid.uuid4())
    oid_1 = str(uuid.uuid4())

    app = create_app()
    client = app.test_client()

    # /me without session
    me0 = client.get("/api/auth/me")
    if me0.status_code != 401:
        fail(f"/me without session expected 401, got {me0.status_code}")
    ok("/me returns 401 when logged out")

    # /login starts flow
    with patch(
        "api.auth.msal_client.authorization_url",
        return_value="https://login.microsoftonline.com/mock/authorize",
    ):
        login = client.get("/api/auth/login?redirect=/connections")
    if login.status_code != 302:
        fail(f"/login expected 302, got {login.status_code}: {login.data}")
    if "login.microsoftonline.com" not in (login.headers.get("Location") or ""):
        fail(f"/login Location unexpected: {login.headers.get('Location')}")
    ok("/login redirects to Microsoft")

    with client.session_transaction() as sess:
        state = sess.get("oauth_state")
        if not state:
            fail("oauth_state missing from session after /login")
        old_sid = getattr(sess, "sid", None)

    def _claims(tid: str, oid: str, email: str, name: str):
        return {
            "id_token_claims": {
                "oid": oid,
                "tid": tid,
                "email": email,
                "name": name,
            },
            "access_token": "MUST_NOT_BE_STORED",
        }

    # First login — org A
    with patch(
        "api.auth.msal_client.exchange_auth_code",
        return_value=_claims(tid_a, oid_1, "alice@acme.test", "Alice"),
    ):
        cb = client.get(f"/api/auth/callback?code=fake&state={state}")
    if cb.status_code != 302:
        fail(f"/callback expected 302, got {cb.status_code}: {cb.data}")
    loc = cb.headers.get("Location") or ""
    if "/connections" not in loc:
        fail(f"post-login redirect unexpected: {loc}")
    ok(f"/callback redirects to portal ({loc})")

    with client.session_transaction() as sess:
        new_sid = getattr(sess, "sid", None)
        if not sess.get("user_id") or not sess.get("organization_id"):
            fail("session missing user_id/organization_id after callback")
        if "access_token" in sess or "MUST_NOT_BE_STORED" in str(dict(sess)):
            fail("SSO access token must not be stored in session")
        if old_sid and new_sid and old_sid == new_sid:
            fail("session sid did not change after login (fixation)")
        user_id = sess["user_id"]
        org_id = sess["organization_id"]
    ok("session regenerated; user_id + organization_id set; no SSO token stored")

    me = client.get("/api/auth/me")
    if me.status_code != 200:
        fail(f"/me expected 200, got {me.status_code}: {me.data}")
    body = me.get_json()
    if body.get("email") != "alice@acme.test":
        fail(f"/me email unexpected: {body}")
    if not body.get("organization") or body["organization"].get("ms_tenant_id") != tid_a:
        fail(f"/me organization unexpected: {body}")
    ok("/me returns user + organization")

    with app.app_context():
        org_count_a = Organization.query.filter_by(ms_tenant_id=tid_a).count()
        user_count = User.query.filter_by(organization_id=org_id, ms_oid=oid_1).count()
        if org_count_a != 1 or user_count != 1:
            fail(f"expected one org A and one user, got orgs={org_count_a} users={user_count}")

    # Same person / same tenant again — reuse user row
    csrf = client.get("/api/auth/csrf-token").get_json()["csrf_token"]
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})

    with patch(
        "api.auth.msal_client.authorization_url",
        return_value="https://login.microsoftonline.com/mock/authorize",
    ):
        client.get("/api/auth/login")
    with client.session_transaction() as sess:
        state2 = sess["oauth_state"]

    with patch(
        "api.auth.msal_client.exchange_auth_code",
        return_value=_claims(tid_a, oid_1, "alice@acme.test", "Alice Updated"),
    ):
        client.get(f"/api/auth/callback?code=fake2&state={state2}")

    with app.app_context():
        users = User.query.filter_by(ms_oid=oid_1).all()
        if len(users) != 1:
            fail(f"expected single user row for oid, got {len(users)}")
        if users[0].display_name != "Alice Updated":
            fail("expected display_name update on re-login")
        orgs = Organization.query.filter_by(ms_tenant_id=tid_a).count()
        if orgs != 1:
            fail(f"expected one org for tid_a, got {orgs}")
    ok("same tenant + oid reuses one user row")

    # Different tenant → different organization
    csrf = client.get("/api/auth/csrf-token").get_json()["csrf_token"]
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    with patch(
        "api.auth.msal_client.authorization_url",
        return_value="https://login.microsoftonline.com/mock/authorize",
    ):
        client.get("/api/auth/login")
    with client.session_transaction() as sess:
        state3 = sess["oauth_state"]
    with patch(
        "api.auth.msal_client.exchange_auth_code",
        return_value=_claims(tid_b, oid_1, "alice@other.test", "Alice Other"),
    ):
        client.get(f"/api/auth/callback?code=fake3&state={state3}")

    with app.app_context():
        org_b = Organization.query.filter_by(ms_tenant_id=tid_b).one_or_none()
        if org_b is None:
            fail("org for tid_b was not created")
        users_for_oid = User.query.filter_by(ms_oid=oid_1).count()
        if users_for_oid != 2:
            fail(f"expected two user rows (one per org) for same oid, got {users_for_oid}")
    ok("different Entra tenant creates a different organization")

    # Logout clears session
    csrf = client.get("/api/auth/csrf-token").get_json()["csrf_token"]
    out = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    if out.status_code != 200 or out.get_json().get("status") != "logged_out":
        fail(f"logout unexpected: {out.status_code} {out.data}")
    me2 = client.get("/api/auth/me")
    if me2.status_code != 401:
        fail(f"/me after logout expected 401, got {me2.status_code}")
    ok("logout clears session")

    # Invalid state
    with patch(
        "api.auth.msal_client.authorization_url",
        return_value="https://login.microsoftonline.com/mock/authorize",
    ):
        client.get("/api/auth/login")
    bad = client.get("/api/auth/callback?code=x&state=wrong")
    if bad.status_code != 400:
        fail(f"bad state expected 400, got {bad.status_code}")
    ok("invalid OAuth state returns 400")

    # Cleanup verification rows (best-effort)
    with app.app_context():
        for tid in (tid_a, tid_b):
            org = Organization.query.filter_by(ms_tenant_id=tid).one_or_none()
            if org:
                User.query.filter_by(organization_id=org.id).delete()
                db.session.delete(org)
        db.session.commit()
    ok(f"cleaned verification orgs (prior user_id={user_id})")


def main() -> int:
    print("Portal auth verification (issue #21)")
    failed = 0
    for fn in (check_infra, check_auth_flow):
        try:
            fn()
        except CheckFailed as exc:
            print(f"  FAIL: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL: unexpected error: {exc}")
            failed += 1
    print()
    if failed:
        print(f"RESULT: {failed} check(s) failed")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
