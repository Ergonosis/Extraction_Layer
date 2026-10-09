"""Issue #28 security hardening audit (cookies, CSRF, limits, leakage, validation).

Usage (from repo root):
  python scripts/verify_portal_security_audit.py

Requires Postgres + Redis. External IdP/Plaid calls are not required.
"""

from __future__ import annotations

import json
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
os.environ.setdefault("PLAID_CLIENT_ID", "verify-plaid-client")
os.environ.setdefault("PLAID_SECRET", "verify-plaid-secret")

from cryptography.fernet import Fernet

PRIMARY_KEY = Fernet.generate_key().decode()
PREVIOUS_KEY = Fernet.generate_key().decode()
os.environ["FERNET_KEY"] = PRIMARY_KEY
os.environ["FERNET_PREVIOUS_KEYS"] = PREVIOUS_KEY


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


def _assert_no_secrets(payload: object, *extra: str) -> None:
    blob = json.dumps(payload, default=str).lower()
    needles = [
        "access_token",
        "refresh_token",
        "client_secret",
        "fernet",
        "private_key",
        PRIMARY_KEY.lower(),
        PREVIOUS_KEY.lower(),
        *extra,
    ]
    for needle in needles:
        if needle and needle in blob:
            fail(f"response leaked secret material ({needle[:16]}…)")


def main() -> int:
    print("Portal security audit (issue #28)")
    from api.app import create_app, _assert_production_secrets
    from api.config import Config
    from api.extensions import db
    from api.models import Organization, User

    step("Cookie / session config")
    if not Config.SESSION_COOKIE_HTTPONLY:
        fail("SESSION_COOKIE_HTTPONLY must be True")
    if Config.SESSION_COOKIE_SAMESITE != "Lax":
        fail("SESSION_COOKIE_SAMESITE must be Lax")
    if Config.PERMANENT_SESSION_LIFETIME.total_seconds() != 8 * 3600:
        fail("session lifetime must be 8 hours")
    ok("HttpOnly + SameSite=Lax + 8h lifetime")

    step("Production boot refuses weak secrets")

    class FakeApp:
        def __init__(self, cfg):
            self.config = cfg

    try:
        _assert_production_secrets(
            FakeApp(
                {
                    "FLASK_ENV": "production",
                    "SECRET_KEY": "dev-only-change-me",
                    "FERNET_KEY": "",
                    "USE_GCP_SECRETS": False,
                    "SESSION_COOKIE_SECURE": False,
                }
            )
        )
        fail("expected production assert to raise")
    except RuntimeError:
        ok("production secrets guard raises on defaults")

    app = create_app()

    @app.get("/api/__audit_boom")
    def _boom():
        raise RuntimeError("SECRET_PATH_C:/keys/fernet.sql")

    client = app.test_client()

    step("Security headers + CORS + CSP (issue #33)")
    health = client.get("/api/health")
    for name, expect in (
        ("Strict-Transport-Security", "max-age="),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ):
        value = health.headers.get(name, "")
        if expect not in value:
            fail(f"header {name} missing/unexpected: {value}")
    # Non-production default is report-only CSP.
    csp_ro = health.headers.get("Content-Security-Policy-Report-Only", "")
    csp_en = health.headers.get("Content-Security-Policy", "")
    if "default-src" not in csp_ro and "default-src" not in csp_en:
        fail(f"expected CSP header, got report-only={csp_ro!r} enforce={csp_en!r}")
    if "localhost:5175" not in ",".join(Config.CORS_ORIGINS):
        fail(f"CORS_ORIGINS should include portal origin, got {Config.CORS_ORIGINS}")
    ok("headers + CORS + CSP look correct")

    step("Audit helper strips secret-like keys")
    from api.audit import audit as emit_audit
    import logging

    class _Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records: list[str] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.records.append(record.getMessage())

    capture = _Capture()
    audit_logger = logging.getLogger("portal.audit")
    audit_logger.addHandler(capture)
    prev_level = audit_logger.level
    audit_logger.setLevel(logging.INFO)
    try:
        emit_audit(
            "test.event",
            user_id=1,
            organization_id=2,
            access_token="should-not-appear",
            ok_field="visible",
        )
    finally:
        audit_logger.removeHandler(capture)
        audit_logger.setLevel(prev_level)
    if not capture.records:
        fail("expected an audit log line")
    line = capture.records[-1]
    if "should-not-appear" in line or "access_token" in line:
        fail(f"audit leaked secret material: {line}")
    if '"ok_field":"visible"' not in line and '"ok_field": "visible"' not in line:
        # separators=(",", ":") → no spaces
        if '"ok_field":"visible"' not in line:
            fail(f"audit missing safe field: {line}")
    ok("audit JSON omits blocked keys")

    step("CSRF: mutations require token; GET does not")
    denied = client.post("/api/auth/ping")
    if denied.status_code != 403:
        fail(f"POST without CSRF expected 403, got {denied.status_code}")
    get_ok = client.get("/api/auth/ping")
    if get_ok.status_code != 200:
        fail(f"GET /auth/ping expected 200, got {get_ok.status_code}")
    csrf = _csrf(client)
    allowed = client.post("/api/auth/ping", headers={"X-CSRF-Token": csrf})
    if allowed.status_code != 200:
        fail(f"POST with CSRF expected 200, got {allowed.status_code}")
    ok("CSRF enforced on POST; GET open")

    step("Unhandled errors do not leak exception text")
    boom = client.get("/api/__audit_boom")
    if boom.status_code != 500:
        fail(f"expected 500, got {boom.status_code}")
    body = boom.get_json() or {}
    blob = json.dumps(body).lower()
    if "secret_path" in blob or "fernet" in blob or "traceback" in blob or "c:/" in blob:
        fail(f"500 response leaked details: {body}")
    if body.get("error") != "Internal server error":
        fail(f"unexpected 500 payload: {body}")
    ok("generic 500 JSON without leakage")
    step("Fernet MultiFernet decrypts previous key ciphertext")
    with app.app_context():
        from api import crypto as crypto_mod

        blob = Fernet(PREVIOUS_KEY.encode()).encrypt(b"rotate-me")
        got = crypto_mod.decrypt_token(blob)
        if got != "rotate-me":
            fail("MultiFernet failed to decrypt previous-key ciphertext")
        new_blob = crypto_mod.encrypt_token("fresh")
        if crypto_mod.decrypt_token(new_blob) != "fresh":
            fail("primary encrypt/decrypt failed")
        try:
            Fernet(PREVIOUS_KEY.encode()).decrypt(new_blob)
            fail("previous key should not decrypt primary ciphertext")
        except Exception:
            pass
    ok("key rotation decrypt window works")

    step("Unexpected JSON fields rejected with 400")
    with app.app_context():
        org = Organization(name="audit.org", ms_tenant_id=str(uuid.uuid4()))
        db.session.add(org)
        db.session.flush()
        user = User(
            organization_id=org.id,
            email="audit@verify.org",
            display_name="Audit",
            ms_oid=str(uuid.uuid4()),
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        org_id = org.id

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["organization_id"] = org_id
    csrf = _csrf(client)
    bad = client.post(
        "/api/plaid/exchange",
        json={"public_token": "public-sandbox-x", "evil": True},
        headers={"X-CSRF-Token": csrf},
    )
    if bad.status_code != 400:
        fail(f"unexpected fields expected 400, got {bad.status_code}: {bad.get_json()}")
    if "Unexpected fields" not in (bad.get_json() or {}).get("error", ""):
        fail(f"unexpected error body: {bad.get_json()}")
    ok("unknown fields rejected")

    step("OAuth state is single-use (SSO callback)")
    with client.session_transaction() as sess:
        sess["oauth_state"] = "once-only-state"
    with patch(
        "api.auth.routes.complete_sso_login",
        side_effect=Exception("exchange should not matter"),
    ):
        first = client.get("/api/auth/callback?code=abc&state=once-only-state")
    with client.session_transaction() as sess:
        if sess.get("oauth_state") == "once-only-state":
            fail("oauth_state was not consumed on callback")
    if first.status_code not in (400, 401, 500):
        fail(f"unexpected callback status {first.status_code}")
    ok("oauth_state consumed after first callback")
    step("Logout destroys server session identity")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["organization_id"] = org_id
    csrf = _csrf(client)
    logged = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    if logged.status_code != 200:
        fail(f"logout expected 200, got {logged.status_code}")
    me = client.get("/api/auth/me")
    if me.status_code != 401:
        fail(f"/me after logout expected 401, got {me.status_code}")
    ok("logout clears auth; /me returns 401")

    step("Auth/me and integration payloads omit tokens")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["organization_id"] = org_id
    me = client.get("/api/auth/me")
    if me.status_code != 200:
        fail(f"/me expected 200, got {me.status_code}")
    _assert_no_secrets(me.get_json())
    listing = client.get("/api/integrations/")
    if listing.status_code != 200:
        # path may be /api/integrations without trailing slash
        listing = client.get("/api/integrations")
    if listing.status_code != 200:
        fail(f"integrations expected 200, got {listing.status_code}")
    _assert_no_secrets(listing.get_json())
    ok("me + integrations have no token fields")

    step("Rate limit still returns 429 under burst")
    saw_429 = False
    for _ in range(45):
        if client.get("/api/health").status_code == 429:
            saw_429 = True
            break
    if not saw_429:
        fail("expected 429 under burst")
    ok("rate limiter returns 429")

    print("\nAll issue #28 / #33 security audit checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
