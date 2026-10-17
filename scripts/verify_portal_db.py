"""Verify portal DB wiring for issue #19 (models, migration, crypto, config).

Usage (from repo root):
  python scripts/verify_portal_db.py

Expects Docker container extraction-portal-postgres on host port 5434.
Does not touch Dirt Directory (ports 5432/5433).
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONTAINER = "extraction-portal-postgres"
EXPECTED_PORT = "5434"
FORBIDDEN_PORTS = ("5432", "5433")
EXPECTED_TABLES = {
    "organizations",
    "users",
    "integrations",
    "plaid_credentials",
    "ms_graph_credentials",
    "ms_graph_permissions",
    "alembic_version",
}


class CheckFailed(Exception):
    pass


def step(name: str) -> None:
    print(f"\n==> {name}")


def ok(msg: str) -> None:
    print(f"  PASS: {msg}")


def fail(msg: str) -> None:
    raise CheckFailed(msg)


def run_docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def check_container() -> None:
    step("Docker container extraction-portal-postgres")
    ps = run_docker(
        "ps",
        "--filter",
        f"name=^{CONTAINER}$",
        "--format",
        "{{.Names}}\t{{.Ports}}\t{{.Status}}",
    )
    if ps.returncode != 0:
        fail(f"docker ps failed: {ps.stderr.strip()}")
    line = ps.stdout.strip()
    if not line or CONTAINER not in line:
        fail(f"container '{CONTAINER}' is not running")
    if f"{EXPECTED_PORT}->5432" not in line.replace(" ", ""):
        # Ports format: 0.0.0.0:5434->5432/tcp
        if f":{EXPECTED_PORT}->" not in line:
            fail(f"expected host port {EXPECTED_PORT} in ports, got: {line}")
    for bad in FORBIDDEN_PORTS:
        # Ensure this container is not mapped to forbidden host ports
        if f":{bad}->" in line:
            fail(f"container must not use host port {bad}: {line}")
    ok(line)


def check_config() -> None:
    step("Config DATABASE_URL")
    from api.config import Config

    url = Config.DATABASE_URL
    if f":{EXPECTED_PORT}/" not in url and f":{EXPECTED_PORT}" not in url:
        fail(f"DATABASE_URL must use port {EXPECTED_PORT}, got: {url}")
    for bad in FORBIDDEN_PORTS:
        if f":{bad}/" in url or url.endswith(f":{bad}"):
            fail(f"DATABASE_URL must not use port {bad}, got: {url}")
    if Config.SQLALCHEMY_DATABASE_URI != url:
        fail("SQLALCHEMY_DATABASE_URI does not match DATABASE_URL")
    ok(url)


def check_tables() -> None:
    step("Postgres tables via docker exec")
    result = run_docker(
        "exec",
        CONTAINER,
        "psql",
        "-U",
        "portal",
        "-d",
        "portal",
        "-Atc",
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1;",
    )
    if result.returncode != 0:
        fail(f"psql failed: {result.stderr.strip()}")
    tables = {t.strip() for t in result.stdout.splitlines() if t.strip()}
    missing = EXPECTED_TABLES - tables
    if missing:
        fail(f"missing tables: {sorted(missing)}; found: {sorted(tables)}")
    ok(f"{len(EXPECTED_TABLES)} expected tables present")


def check_crypto() -> None:
    step("Fernet encrypt/decrypt round-trip")
    from cryptography.fernet import Fernet

    from api.app import create_app
    from api.crypto import decrypt_token, encrypt_token

    app = create_app()
    app.config["FERNET_KEY"] = Fernet.generate_key().decode()
    with app.app_context():
        blob = encrypt_token("verify-portal-db-token")
        if not isinstance(blob, (bytes, bytearray)):
            fail("encrypt_token must return bytes")
        plain = decrypt_token(blob)
        if plain != "verify-portal-db-token":
            fail(f"decrypt mismatch: {plain!r}")
    ok("round-trip succeeded")


def check_orm() -> None:
    step("ORM insert/delete against live DB")
    from api.app import create_app
    from api.extensions import db
    from api.models import Organization

    app = create_app()
    tenant = str(uuid.uuid4())
    with app.app_context():
        org = Organization(name="verify-portal-db", ms_tenant_id=tenant)
        db.session.add(org)
        db.session.commit()
        org_id = org.id
        found = Organization.query.filter_by(ms_tenant_id=tenant).one()
        if found.id != org_id:
            fail("query did not return inserted organization")
        db.session.delete(found)
        db.session.commit()
        still = Organization.query.filter_by(ms_tenant_id=tenant).first()
        if still is not None:
            fail("organization was not deleted")
    ok(f"inserted and deleted organization id={org_id}")


def check_app_factory() -> None:
    step("Flask app factory + health route registered")
    from api.app import create_app

    app = create_app()
    rules = {str(r) for r in app.url_map.iter_rules()}
    if "/api/health" not in rules:
        fail(f"/api/health missing; rules={sorted(rules)}")
    ok("create_app() ok; /api/health registered")


def main() -> int:
    print("Portal DB verification (issue #19)")
    print(f"Repo: {REPO_ROOT}")
    checks = [
        check_container,
        check_config,
        check_tables,
        check_crypto,
        check_orm,
        check_app_factory,
    ]
    failed = 0
    for fn in checks:
        try:
            fn()
        except CheckFailed as exc:
            print(f"  FAIL: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001 - report unexpected errors clearly
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
