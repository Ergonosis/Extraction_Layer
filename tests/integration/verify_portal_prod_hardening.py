"""Issue #33 production hardening checks (CSP, audit, docs markers; no WAF).

Usage (from repo root):
  uv run python -m tests.integration.verify_portal_prod_hardening

Requires Postgres + Redis. Does not call Cloud Armor APIs.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class CheckFailed(Exception):
    pass


def step(name: str) -> None:
    print(f'\n==> {name}')


def ok(msg: str) -> None:
    print(f'  PASS: {msg}')


def fail(msg: str) -> None:
    raise CheckFailed(msg)


def main() -> int:
    print('Portal production hardening (issue #33, WAF deferred)')

    from src.api.app import create_app
    from src.api.csp import DEFAULT_CSP, resolve_csp_mode

    step('CSP mode defaults')
    if resolve_csp_mode('', flask_env='production') != 'enforce':
        fail('production default CSP mode should be enforce')
    if resolve_csp_mode('', flask_env='development') != 'report-only':
        fail('development default CSP mode should be report-only')
    if 'plaid.com' not in DEFAULT_CSP or 'microsoftonline.com' not in DEFAULT_CSP:
        fail('default CSP should allow Plaid and Microsoft hosts')
    ok('CSP defaults look correct')

    step('App emits CSP report-only in development')
    app = create_app()
    client = app.test_client()
    health = client.get('/api/health')
    csp = health.headers.get('Content-Security-Policy-Report-Only', '')
    if "default-src 'self'" not in csp:
        fail(f'missing report-only CSP: {csp!r}')
    ok('Content-Security-Policy-Report-Only present')

    step('SECURITY.md records defer-WAF + alert guidance')
    security = (REPO_ROOT / 'SECURITY.md').read_text(encoding='utf-8')
    for needle in (
        'Cloud Armor / WAF — deferred',
        'auth.login.failure',
        'Content-Security-Policy',
        'portal.audit',
        '/cloudsql/',
    ):
        if needle not in security:
            fail(f'SECURITY.md missing {needle!r}')
    ok('SECURITY.md hardening section present')

    step('GCP launch runbook preserves production networking gates')
    deploy_doc = (REPO_ROOT / 'docs' / 'gcp-launch-runbook.md').read_text(encoding='utf-8')
    for needle in ('Cloud SQL', 'Redis', 'Secret Manager', '后续生产化顺序'):
        if needle not in deploy_doc:
            fail(f'docs/gcp-launch-runbook.md missing {needle!r}')
    ok('deploy docs updated')

    print('\nAll issue #33 hardening checks passed (WAF deferred).')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        print(f'\nFAIL: {exc}', file=sys.stderr)
        raise SystemExit(1)
