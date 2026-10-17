"""Verify issue #27 portal export wiring (Plaid + MS Graph).

Usage (from repo root):
  python scripts/verify_portal_exports.py

Requires Postgres (5434) + Redis (6379). External Plaid/Graph HTTP is mocked.
"""

from __future__ import annotations

import json
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


def _assert_no_secrets(payload: object) -> None:
    blob = json.dumps(payload, default=str).lower()
    for needle in (
        "access-secret",
        "refresh-secret",
        "access_token",
        "refresh_token",
        "access-seed",
        "refresh-seed",
    ):
        if needle in blob:
            fail(f"response leaked secret material containing {needle!r}")


def main() -> int:
    print("Portal export verification (issue #27)")
    from api.app import create_app
    from api.crypto import encrypt_token
    from api.extensions import db
    from api.models import (
        Integration,
        MsGraphCredential,
        MsGraphPermission,
        Organization,
        PlaidCredential,
        User,
    )
    from api.plaid_bp.extractor import load_fetch_and_store
    from api.msgraph_bp.graph_data import load_graph_client_class

    load_fetch_and_store.cache_clear()
    load_graph_client_class.cache_clear()

    app = create_app()
    client = app.test_client()

    step("Seed connected Plaid + MS Graph user")
    tid = str(uuid.uuid4())
    oid = str(uuid.uuid4())
    with app.app_context():
        org = Organization(name="export-verify.org", ms_tenant_id=tid)
        db.session.add(org)
        db.session.flush()
        user = User(
            organization_id=org.id,
            email="export@verify.org",
            display_name="Export Verify",
            ms_oid=oid,
        )
        db.session.add(user)
        db.session.flush()

        plaid_row = Integration(
            user_id=user.id,
            organization_id=org.id,
            provider="plaid",
            status="connected",
            connected_account="Verify Bank",
        )
        db.session.add(plaid_row)
        db.session.flush()
        db.session.add(
            PlaidCredential(
                integration_id=plaid_row.id,
                access_token_enc=encrypt_token("access-secret-plaid"),
                item_id="item-verify-1",
                institution_name="Verify Bank",
            )
        )

        graph_row = Integration(
            user_id=user.id,
            organization_id=org.id,
            provider="msgraph",
            status="connected",
            connected_account="export@verify.org",
        )
        db.session.add(graph_row)
        db.session.flush()
        db.session.add(
            MsGraphCredential(
                integration_id=graph_row.id,
                access_token_enc=encrypt_token("access-secret-graph"),
                refresh_token_enc=encrypt_token("refresh-secret-graph"),
                scopes_granted=["User.Read", "Mail.Read", "Calendars.Read"],
            )
        )
        for scope, active in (
            ("User.Read", True),
            ("Mail.Read", False),
            ("Calendars.Read", False),
            ("Files.Read", False),
        ):
            db.session.add(
                MsGraphPermission(
                    integration_id=graph_row.id,
                    scope=scope,
                    is_active=active,
                )
            )
        db.session.commit()
        user_id = user.id
        org_id = org.id
        graph_integration_id = graph_row.id

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["organization_id"] = org_id
    csrf = _csrf(client)

    step("POST /api/plaid/export calls legacy fetch_and_store")
    with patch("api.plaid_bp.service.get_plaid_client", return_value=MagicMock()):
        with patch(
            "api.plaid_bp.service.load_fetch_and_store",
            return_value=MagicMock(return_value="records/verify_export.json"),
        ) as loader:
            resp = client.post(
                "/api/plaid/export",
                json={"window_days": 7},
                headers={"X-CSRF-Token": csrf},
            )
    if resp.status_code != 200:
        fail(f"plaid export expected 200, got {resp.status_code}: {resp.get_json()}")
    data = resp.get_json()
    _assert_no_secrets(data)
    if data.get("file") != "records/verify_export.json":
        fail(f"unexpected file payload: {data}")
    if data.get("item_id") != "item-verify-1":
        fail(f"unexpected item_id: {data}")
    call_kwargs = loader.return_value.call_args.kwargs
    if "access-secret-plaid" in json.dumps(call_kwargs, default=str):
        # token is positional arg — check positional
        pass
    args = loader.return_value.call_args.args
    if len(args) < 2 or args[1] != "access-secret-plaid":
        fail("fetch_and_store was not called with decrypted access token")
    ok("Plaid export wired to fetch_and_store")

    step("MS Graph export: profile allowed; mail/calendar skipped by is_active")
    mock_client = MagicMock()
    mock_client.fetch_profile.return_value = {
        "display_name": "Export Verify",
        "mail": "export@verify.org",
    }
    with patch(
        "api.msgraph_bp.service.client_from_access_token",
        return_value=mock_client,
    ):
        resp = client.post(
            "/api/msgraph/export",
            json={
                "include_profile": True,
                "include_mail": True,
                "include_calendar": True,
                "start_datetime": "2026-01-01T00:00:00Z",
                "end_datetime": "2026-01-31T23:59:59Z",
            },
            headers={"X-CSRF-Token": csrf},
        )
    if resp.status_code != 200:
        fail(f"msgraph export expected 200, got {resp.status_code}: {resp.get_json()}")
    data = resp.get_json()
    _assert_no_secrets(data)
    if not data.get("profile"):
        fail("expected profile payload")
    if data.get("mail_count") != 0 or data.get("calendar_count") != 0:
        fail(f"expected skipped mail/calendar counts 0: {data}")
    skipped_scopes = {row["scope"] for row in data.get("skipped", [])}
    if skipped_scopes != {"Mail.Read", "Calendars.Read"}:
        fail(f"unexpected skipped scopes: {skipped_scopes}")
    mock_client.fetch_messages.assert_not_called()
    mock_client.fetch_events.assert_not_called()
    ok("permission gate skipped inactive mail/calendar")

    step("Activate Mail.Read + Calendars.Read then export all three")
    with app.app_context():
        for row in MsGraphPermission.query.filter_by(
            integration_id=graph_integration_id
        ).all():
            if row.scope in ("Mail.Read", "Calendars.Read", "User.Read"):
                row.is_active = True
        db.session.commit()

    mock_client = MagicMock()
    mock_client.fetch_profile.return_value = {"display_name": "Export Verify"}
    mock_client.fetch_messages.return_value = [{"subject": "hi"}]
    mock_client.fetch_events.return_value = [{"subject": "standup"}]
    with patch(
        "api.msgraph_bp.service.client_from_access_token",
        return_value=mock_client,
    ) as from_token:
        resp = client.post(
            "/api/msgraph/export",
            json={
                "include_profile": True,
                "include_mail": True,
                "include_calendar": True,
                "start_datetime": "2026-01-01T00:00:00Z",
                "end_datetime": "2026-01-31T23:59:59Z",
                "max_pages": 1,
            },
            headers={"X-CSRF-Token": csrf},
        )
    if resp.status_code != 200:
        fail(f"full export expected 200, got {resp.status_code}: {resp.get_json()}")
    data = resp.get_json()
    _assert_no_secrets(data)
    if data.get("mail_count") != 1 or data.get("calendar_count") != 1:
        fail(f"expected one mail and one event: {data}")
    if data.get("skipped"):
        fail(f"expected no skipped scopes: {data}")
    if from_token.call_args.args[0] != "access-secret-graph":
        fail("Graph client did not receive decrypted access token")
    mock_client.fetch_messages.assert_called_once()
    mock_client.fetch_events.assert_called_once()
    ok("profile + mail + calendar exported when active")

    step("403 when wish list has no enabled scopes")
    with app.app_context():
        for row in MsGraphPermission.query.filter_by(
            integration_id=graph_integration_id
        ).all():
            row.is_active = False
        db.session.commit()
    resp = client.post(
        "/api/msgraph/export",
        json={
            "include_profile": True,
            "include_mail": False,
            "include_calendar": False,
        },
        headers={"X-CSRF-Token": csrf},
    )
    if resp.status_code != 403:
        fail(f"expected 403 when nothing active, got {resp.status_code}")
    ok("blocked when permissions inactive")

    step("Reject end_datetime not after start_datetime")
    with app.app_context():
        for row in MsGraphPermission.query.filter_by(
            integration_id=graph_integration_id
        ).all():
            if row.scope == "Mail.Read":
                row.is_active = True
        db.session.commit()
    resp = client.post(
        "/api/msgraph/export",
        json={
            "include_profile": False,
            "include_mail": True,
            "include_calendar": False,
            "start_datetime": "2026-02-01T00:00:00Z",
            "end_datetime": "2026-01-01T00:00:00Z",
        },
        headers={"X-CSRF-Token": csrf},
    )
    if resp.status_code != 400:
        fail(f"expected 400 for inverted range, got {resp.status_code}: {resp.get_json()}")
    detail = (resp.get_json() or {}).get("error", "")
    if "after start_datetime" not in detail:
        fail(f"unexpected error message: {detail}")
    ok("inverted datetime range rejected")

    print("\nAll portal export checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
