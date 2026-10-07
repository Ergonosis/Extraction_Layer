"""Verify issue #23 integrations dashboard API.

Usage (from repo root):
  python scripts/verify_portal_integrations.py

Requires Postgres (5434) + Redis (6379).
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("MS_CLIENT_ID", "verify-client-id")
os.environ.setdefault("MS_CLIENT_SECRET", "verify-client-secret")


class CheckFailed(Exception):
    pass


def step(name: str) -> None:
    print(f"\n==> {name}")


def ok(msg: str) -> None:
    print(f"  PASS: {msg}")


def fail(msg: str) -> None:
    raise CheckFailed(msg)


def main() -> int:
    print("Portal integrations verification (issue #23)")
    from api.app import create_app
    from api.extensions import db
    from api.models import Integration, Organization, User

    app = create_app()
    client = app.test_client()

    step("Unauthenticated GET /api/integrations")
    denied = client.get("/api/integrations/")
    if denied.status_code != 401:
        # some setups may be /api/integrations without trailing slash
        denied = client.get("/api/integrations")
    if denied.status_code != 401:
        fail(f"expected 401, got {denied.status_code}")
    ok("returns 401 without session")

    step("Authenticated list auto-creates provider rows")
    tid = str(uuid.uuid4())
    oid = str(uuid.uuid4())
    with app.app_context():
        org = Organization(name="verify.org", ms_tenant_id=tid)
        db.session.add(org)
        db.session.flush()
        user = User(
            organization_id=org.id,
            email="verify@verify.org",
            display_name="Verify User",
            ms_oid=oid,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        org_id = org.id

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["organization_id"] = org_id

    resp = client.get("/api/integrations/")
    if resp.status_code != 200:
        resp = client.get("/api/integrations")
    if resp.status_code != 200:
        fail(f"expected 200, got {resp.status_code}: {resp.data}")
    body = resp.get_json()
    rows = body.get("integrations") or []
    if len(rows) != 2:
        fail(f"expected 2 integrations, got {rows}")
    providers = {r["provider"] for r in rows}
    if providers != {"plaid", "msgraph"}:
        fail(f"unexpected providers: {providers}")
    for row in rows:
        if row.get("status") != "not_connected":
            fail(f"expected not_connected, got {row}")
        if "access_token" in str(row).lower() or "secret" in str(row).lower():
            fail(f"response must not include secrets: {row}")
        if row["provider"] == "msgraph":
            perms = row.get("permissions") or []
            if len(perms) < 1:
                fail("msgraph should include permission catalog labels")
            if any("token" in p for p in perms):
                fail("permissions leaked token-like fields")
    ok("returns plaid + msgraph as not_connected without secrets")

    with app.app_context():
        count = Integration.query.filter_by(user_id=user_id, organization_id=org_id).count()
        if count != 2:
            fail(f"expected 2 DB rows, got {count}")
        # second call should not duplicate
    resp2 = client.get("/api/integrations/")
    if resp2.status_code != 200:
        resp2 = client.get("/api/integrations")
    with app.app_context():
        count2 = Integration.query.filter_by(user_id=user_id, organization_id=org_id).count()
        if count2 != 2:
            fail(f"duplicate rows created: {count2}")
        Integration.query.filter_by(user_id=user_id).delete()
        User.query.filter_by(id=user_id).delete()
        Organization.query.filter_by(id=org_id).delete()
        db.session.commit()
    ok("idempotent ensure + cleaned verification rows")

    print("\nRESULT: all checks passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        print(f"  FAIL: {exc}")
        print("\nRESULT: failed")
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: unexpected error: {exc}")
        print("\nRESULT: failed")
        raise SystemExit(1) from exc
