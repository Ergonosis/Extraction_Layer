"""Verify issue #20 security foundation (headers, CSRF, rate limit, Redis).

Usage (from repo root):
  python scripts/verify_portal_security.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REDIS_CONTAINER = "extraction-portal-redis"


class CheckFailed(Exception):
    pass


def step(name: str) -> None:
    print(f"\n==> {name}")


def ok(msg: str) -> None:
    print(f"  PASS: {msg}")


def fail(msg: str) -> None:
    raise CheckFailed(msg)


def check_redis_container() -> None:
    step("Docker Redis container")
    ps = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"name=^{REDIS_CONTAINER}$",
            "--format",
            "{{.Names}}\t{{.Ports}}\t{{.Status}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    line = (ps.stdout or "").strip()
    if REDIS_CONTAINER not in line:
        fail(f"{REDIS_CONTAINER} is not running")
    if "6379" not in line:
        fail(f"expected host port 6379, got: {line}")
    ping = subprocess.run(
        ["docker", "exec", REDIS_CONTAINER, "redis-cli", "ping"],
        capture_output=True,
        text=True,
        check=False,
    )
    if "PONG" not in (ping.stdout or ""):
        fail("redis-cli ping failed")
    ok(line)


def check_config() -> None:
    step("Config REDIS_URL and session flags")
    from api.config import Config

    if "6379" not in Config.REDIS_URL:
        fail(f"REDIS_URL should target local Redis, got {Config.REDIS_URL}")
    if not Config.SESSION_COOKIE_HTTPONLY:
        fail("SESSION_COOKIE_HTTPONLY must be True")
    if Config.SESSION_COOKIE_SAMESITE != "Lax":
        fail("SESSION_COOKIE_SAMESITE must be Lax")
    if Config.PERMANENT_SESSION_LIFETIME.total_seconds() != 8 * 3600:
        fail("PERMANENT_SESSION_LIFETIME must be 8 hours")
    ok(f"REDIS_URL={Config.REDIS_URL}; Secure={Config.SESSION_COOKIE_SECURE}")


def check_headers_csrf_rate_limit() -> None:
    step("Security headers, CSRF, rate limit via test client")
    from api.app import create_app

    app = create_app()
    client = app.test_client()

    health = client.get("/api/health")
    if health.status_code != 200:
        fail(f"/api/health status {health.status_code}")
    headers = health.headers
    for name in (
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
    ):
        if name not in headers:
            fail(f"missing response header {name}")
    ok("security headers present on /api/health")

    denied = client.post("/api/auth/ping")
    if denied.status_code != 403:
        fail(f"POST without CSRF expected 403, got {denied.status_code}")
    ok("POST without CSRF returns 403")

    csrf = client.get("/api/auth/csrf-token")
    if csrf.status_code != 200:
        fail(f"csrf-token status {csrf.status_code}")
    token = csrf.get_json().get("csrf_token")
    if not token:
        fail("csrf_token missing from response")
    allowed = client.post("/api/auth/ping", headers={"X-CSRF-Token": token})
    if allowed.status_code != 200:
        fail(f"POST with CSRF expected 200, got {allowed.status_code}: {allowed.data}")
    ok("POST with valid CSRF returns 200")

    # Default limit is 30/min; burst past it on /api/health
    saw_429 = False
    for _ in range(40):
        resp = client.get("/api/health")
        if resp.status_code == 429:
            saw_429 = True
            break
    if not saw_429:
        fail("expected 429 after bursting requests")
    ok("rate limiter returned 429 under burst")


def check_redis_session_key() -> None:
    step("Session key written to Redis")
    from api.app import create_app

    app = create_app()
    client = app.test_client()
    client.get("/api/auth/csrf-token")

    keys = subprocess.run(
        ["docker", "exec", REDIS_CONTAINER, "redis-cli", "KEYS", "portal:session:*"],
        capture_output=True,
        text=True,
        check=False,
    )
    # flask-session may use different key layout; also check any keys
    if not (keys.stdout or "").strip():
        keys = subprocess.run(
            ["docker", "exec", REDIS_CONTAINER, "redis-cli", "DBSIZE"],
            capture_output=True,
            text=True,
            check=False,
        )
        size = (keys.stdout or "").strip()
        if size in {"", "0"}:
            fail("Redis DB appears empty after creating a session")
        ok(f"Redis DBSIZE={size}")
    else:
        ok(f"session keys present: {(keys.stdout or '').strip().splitlines()[:3]}")


def main() -> int:
    print("Portal security verification (issue #20)")
    failed = 0
    for fn in (
        check_redis_container,
        check_config,
        check_headers_csrf_rate_limit,
        check_redis_session_key,
    ):
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
