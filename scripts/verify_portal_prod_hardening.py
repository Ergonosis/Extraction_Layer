"""Issue #33 production hardening checks (CSP, audit, docs markers; no WAF).

Usage (from repo root):
  python scripts/verify_portal_prod_hardening.py

Requires Postgres + Redis. Does not call Cloud Armor APIs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class CheckFailed(Exception):
    pass


def step(name: str) -> None:
    print(f"\n==> {name}")


def ok(msg: str) -> None:
    print(f"  PASS: {msg}")


def fail(msg: str) -> None:
    raise CheckFailed(msg)


def main() -> int:
    print("Portal production hardening (issue #33, WAF deferred)")

    from api.app import create_app
    from api.csp import DEFAULT_CSP, resolve_csp_mode

    step("CSP mode defaults")
    if resolve_csp_mode("", flask_env="production") != "enforce":
        fail("production default CSP mode should be enforce")
    if resolve_csp_mode("", flask_env="development") != "report-only":
        fail("development default CSP mode should be report-only")
    if "plaid.com" not in DEFAULT_CSP or "microsoftonline.com" not in DEFAULT_CSP:
        fail("default CSP should allow Plaid and Microsoft hosts")
    ok("CSP defaults look correct")

    step("App emits CSP report-only in development")
    app = create_app()
    client = app.test_client()
    health = client.get("/api/health")
    csp = health.headers.get("Content-Security-Policy-Report-Only", "")
    if "default-src 'self'" not in csp:
        fail(f"missing report-only CSP: {csp!r}")
    ok("Content-Security-Policy-Report-Only present")

    step("SECURITY.md records defer-WAF + alert guidance")
    security = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    for needle in (
        "Cloud Armor / WAF — deferred",
        "auth.login.failure",
        "Content-Security-Policy",
        "portal.audit",
        "/cloudsql/",
    ):
        if needle not in security:
            fail(f"SECURITY.md missing {needle!r}")
    ok("SECURITY.md hardening section present")

    step("deploy-gcp.md checklist mentions #33 networking")
    deploy_doc = (REPO_ROOT / "docs" / "deploy-gcp.md").read_text(encoding="utf-8")
    if "Production networking checklist (issue #33)" not in deploy_doc:
        fail("docs/deploy-gcp.md missing #33 checklist")
    if "WAF deferred" not in deploy_doc and "WAF deferred" not in security:
        fail("expected WAF deferred note")
    ok("deploy docs updated")

    print("\nAll issue #33 hardening checks passed (WAF deferred).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
