"""Issue #30 multi-organization tenancy checks.

Usage (from repo root):
  python scripts/verify_portal_tenancy.py

Requires Postgres (+ Redis if sessions are Redis-backed). No real Entra login.
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
    print("Portal multi-organization tenancy (issue #30)")

    from api.app import create_app
    from api.auth.service import complete_sso_login
    from api.config import Config
    from api.extensions import db
    from api.integrations.service import ensure_provider_rows, list_integrations
    from api.models import Integration, Organization, User
    from api.tenancy import TenancyError, require_matching_org

    step("Config: Redis URL + multi-tenant SSO authority")
    if not (Config.REDIS_URL or "").strip():
        fail("REDIS_URL must be set for multi-instance sessions")
    authority = (Config.MS_AUTHORITY or "").rstrip("/")
    if not authority.endswith("/organizations"):
        fail(
            "MS_AUTHORITY should use /organizations for multi-tenant SSO, "
            f"got {Config.MS_AUTHORITY!r}"
        )
    ok(f"REDIS_URL set; MS_AUTHORITY={authority}")

    app = create_app()
    client = app.test_client()

    with app.app_context():
        tid_a = str(uuid.uuid4())
        tid_b = str(uuid.uuid4())
        oid_a = str(uuid.uuid4())
        oid_b = str(uuid.uuid4())

        org_a = Organization(name="tenancy-a.example", ms_tenant_id=tid_a)
        org_b = Organization(name="tenancy-b.example", ms_tenant_id=tid_b)
        db.session.add_all([org_a, org_b])
        db.session.flush()

        user_a = User(
            organization_id=org_a.id,
            email="a@tenancy-a.example",
            display_name="User A",
            ms_oid=oid_a,
        )
        user_b = User(
            organization_id=org_b.id,
            email="b@tenancy-b.example",
            display_name="User B",
            ms_oid=oid_b,
        )
        db.session.add_all([user_a, user_b])
        db.session.commit()

        org_a_id, org_b_id = org_a.id, org_b.id
        user_a_id, user_b_id = user_a.id, user_b.id

        step("Schema: org-scoped unique keys")
        if Organization.query.filter_by(ms_tenant_id=tid_a).count() != 1:
            fail("organizations.ms_tenant_id uniqueness broken")
        try:
            db.session.add(
                Organization(name="dup", ms_tenant_id=tid_a),
            )
            db.session.flush()
            fail("duplicate ms_tenant_id should violate unique constraint")
        except Exception:
            db.session.rollback()
            # Re-bind ids after rollback
            org_a = db.session.get(Organization, org_a_id)
            org_b = db.session.get(Organization, org_b_id)
            user_a = db.session.get(User, user_a_id)
            user_b = db.session.get(User, user_b_id)
            if not all([org_a, org_b, user_a, user_b]):
                fail("failed to re-load fixture rows after rollback")
            ok("organizations.ms_tenant_id is unique")

        step("require_matching_org rejects cross-org user ids")
        require_matching_org(user_id=user_a_id, organization_id=org_a_id)
        try:
            require_matching_org(user_id=user_a_id, organization_id=org_b_id)
            fail("expected TenancyError for mismatched org")
        except TenancyError:
            ok("mismatched user/org raises TenancyError")

        step("Integrations are isolated per user+org")
        rows_a = ensure_provider_rows(user_id=user_a_id, organization_id=org_a_id)
        rows_b = ensure_provider_rows(user_id=user_b_id, organization_id=org_b_id)
        if len(rows_a) != 2 or len(rows_b) != 2:
            fail("expected plaid + msgraph rows for each user")
        ids_a = {r.id for r in rows_a}
        ids_b = {r.id for r in rows_b}
        if ids_a & ids_b:
            fail("integration row ids leaked across organizations")

        listed_a = list_integrations(user_id=user_a_id, organization_id=org_a_id)
        listed_b = list_integrations(user_id=user_b_id, organization_id=org_b_id)
        if {row["provider"] for row in listed_a} != {"plaid", "msgraph"}:
            fail(f"unexpected providers for A: {listed_a}")
        if {row["provider"] for row in listed_b} != {"plaid", "msgraph"}:
            fail(f"unexpected providers for B: {listed_b}")

        # Stamp org A plaid as connected; org B must stay not_connected.
        plaid_a = next(r for r in rows_a if r.provider == "plaid")
        plaid_a.status = "connected"
        plaid_a.connected_account = "bank-a"
        db.session.commit()

        again_b = list_integrations(user_id=user_b_id, organization_id=org_b_id)
        plaid_b_status = next(r["status"] for r in again_b if r["provider"] == "plaid")
        if plaid_b_status == "connected":
            fail("org B saw org A connected status")
        ok("list_integrations does not mix org A and org B data")

        try:
            ensure_provider_rows(user_id=user_a_id, organization_id=org_b_id)
            fail("ensure_provider_rows should reject cross-org ids")
        except TenancyError:
            ok("ensure_provider_rows fails closed on org mismatch")

        step("SSO maps tid -> organization; allowlist rejects foreign tid")
        foreign_tid = str(uuid.uuid4())
        foreign_oid = str(uuid.uuid4())

        def _fake_exchange(_code: str) -> dict:
            return {
                "id_token_claims": {
                    "oid": foreign_oid,
                    "tid": foreign_tid,
                    "email": "newbie@foreign.example",
                    "name": "Newbie",
                }
            }

        allowed = complete_sso_login(
            "fake-code",
            tenant_allowlist=[],
            exchange_auth_code=_fake_exchange,
        )
        org = Organization.query.filter_by(ms_tenant_id=foreign_tid).one_or_none()
        if org is None or allowed.organization_id != org.id:
            fail("SSO did not create/join org from tid")
        ok("SSO creates organization from Entra tid")

        from api.auth.service import AuthError

        try:
            complete_sso_login(
                "fake-code-2",
                tenant_allowlist=[tid_a],
                exchange_auth_code=_fake_exchange,
            )
            fail("allowlist should reject foreign tid")
        except AuthError as exc:
            if exc.status_code != 403:
                fail(f"expected AuthError 403, got {exc.status_code}")
            ok("MS_TENANT_ALLOWLIST rejects non-listed tenants")

        step("HTTP session org mismatch is rejected")
        with client.session_transaction() as sess:
            sess["user_id"] = user_a_id
            sess["organization_id"] = org_b_id  # wrong on purpose
        me = client.get("/api/auth/me")
        if me.status_code != 401:
            fail(f"mismatched session /me expected 401, got {me.status_code}")
        ok("login_required destroys mismatched user/org sessions")

        # Cleanup fixture rows we created (best-effort; leave SSO foreign org).
        Integration.query.filter(
            Integration.user_id.in_([user_a_id, user_b_id])
        ).delete(synchronize_session=False)
        User.query.filter(User.id.in_([user_a_id, user_b_id])).delete(
            synchronize_session=False
        )
        Organization.query.filter(
            Organization.id.in_([org_a_id, org_b_id])
        ).delete(synchronize_session=False)
        db.session.commit()

    print("\nAll issue #30 tenancy checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
