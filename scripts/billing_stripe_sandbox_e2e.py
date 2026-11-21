"""Optional Stripe Test Clock sandbox walkthrough (manual / secret-gated).

Does NOT run in normal CI. Requires a Stripe test-mode secret key and catalog price.

Prerequisites:
  - Stripe account in test mode
  - STRIPE_ENABLED=true
  - STRIPE_SECRET_KEY=sk_test_...
  - STRIPE_SANDBOX_PRICE_ID=price_...  (recurring price with tax_behavior set)
  - Stripe Tax enabled in Dashboard (test mode) for tax lines to appear

Usage (repo root):
  uv run python -m scripts.billing_stripe_sandbox_e2e
  uv run python -m scripts.billing_stripe_sandbox_e2e --advance-days 32
  uv run python -m scripts.billing_stripe_sandbox_e2e --fail-card

See docs/billing-stripe-sandbox-e2e.md for the full runbook.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
os.chdir(REPO_ROOT)


def _require_test_mode() -> str:
    enabled = (os.getenv('STRIPE_ENABLED') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
    key = (os.getenv('STRIPE_SECRET_KEY') or '').strip()
    if not enabled:
        raise SystemExit('Set STRIPE_ENABLED=true to run this sandbox script.')
    if not key.startswith('sk_test_'):
        raise SystemExit('STRIPE_SECRET_KEY must be a sk_test_… key (refusing live keys).')
    return key


def _stripe(key: str):
    import stripe

    stripe.api_key = key
    return stripe


def _wait_clock(stripe, clock_id: str, *, timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        clock = stripe.test_helpers.TestClock.retrieve(clock_id)
        status = clock.get('status') if isinstance(clock, dict) else getattr(clock, 'status', None)
        if status == 'ready':
            return
        if status == 'internal_failure':
            raise SystemExit(f'Test clock {clock_id} failed: {clock}')
        time.sleep(2)
    raise SystemExit(f'Timed out waiting for test clock {clock_id}')


def main() -> int:
    parser = argparse.ArgumentParser(description='Stripe Test Clock sandbox E2E for Portal billing')
    parser.add_argument('--advance-days', type=int, default=32, help='Days to advance the clock after subscribe')
    parser.add_argument(
        '--fail-card',
        action='store_true',
        help='Attach declining test card 4000000000000341 instead of 4242 (triggers payment_failed)',
    )
    parser.add_argument('--email', default='sandbox-billing@example.com')
    args = parser.parse_args()

    # Load .env if present (same pattern as other scripts)
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / '.env')
    except ImportError:
        pass

    key = _require_test_mode()
    price_id = (os.getenv('STRIPE_SANDBOX_PRICE_ID') or '').strip()
    if not price_id:
        raise SystemExit('Set STRIPE_SANDBOX_PRICE_ID=price_… (recurring test price from Dashboard Products).')

    stripe = _stripe(key)
    frozen = int(time.time())
    print(f'Creating Test Clock (frozen_time={frozen})…')
    clock = stripe.test_helpers.TestClock.create(frozen_time=frozen, name='portal-billing-e2e')
    clock_id = clock['id']
    print(f'  clock={clock_id}')

    print('Creating customer on Test Clock…')
    customer = stripe.Customer.create(
        email=args.email,
        name='Portal Billing Sandbox',
        test_clock=clock_id,
        metadata={'organization_id': 'sandbox', 'source': 'billing_stripe_sandbox_e2e'},
    )
    customer_id = customer['id']
    print(f'  customer={customer_id}')

    print(f'Attaching payment method ({"decline" if args.fail_card else "4242"})…')
    card_token = 'tok_chargeDeclined' if args.fail_card else 'tok_visa'
    pm = stripe.PaymentMethod.create(type='card', card={'token': card_token})
    stripe.PaymentMethod.attach(pm['id'], customer=customer_id)
    stripe.Customer.modify(customer_id, invoice_settings={'default_payment_method': pm['id']})
    print(f'  payment_method={pm["id"]}')

    print(f'Creating subscription price={price_id} (automatic_tax)…')
    try:
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{'price': price_id}],
            default_payment_method=pm['id'],
            automatic_tax={'enabled': True},
            payment_behavior='default_incomplete' if args.fail_card else 'error_if_incomplete',
            expand=['latest_invoice.payment_intent'],
        )
    except Exception as exc:
        # Tax may require a customer address — set a US address and retry once.
        print(f'  first subscribe attempt failed ({exc}); setting US address and retrying…')
        stripe.Customer.modify(
            customer_id,
            address={
                'line1': '1 Market St',
                'city': 'San Francisco',
                'state': 'CA',
                'postal_code': '94105',
                'country': 'US',
            },
        )
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{'price': price_id}],
            default_payment_method=pm['id'],
            automatic_tax={'enabled': True},
            payment_behavior='default_incomplete' if args.fail_card else 'error_if_incomplete',
            expand=['latest_invoice'],
        )

    sub_id = subscription['id']
    print(f'  subscription={sub_id} status={subscription.get("status")}')
    latest = subscription.get('latest_invoice')
    if isinstance(latest, dict):
        print(
            f'  latest_invoice={latest.get("id")} '
            f'total={latest.get("total")} tax={latest.get("tax")} '
            f'status={latest.get("status")}'
        )

    if args.advance_days > 0:
        target = frozen + args.advance_days * 86400
        print(f'Advancing Test Clock +{args.advance_days}d → {target}…')
        stripe.test_helpers.TestClock.advance(clock_id, frozen_time=target)
        _wait_clock(stripe, clock_id)
        print('  clock ready')

        invoices = stripe.Invoice.list(customer=customer_id, limit=5)
        print(f'Invoices after advance ({len(invoices.data)}):')
        for inv in invoices.data:
            print(
                f'  - {inv["id"]} status={inv.get("status")} '
                f'subtotal={inv.get("subtotal")} tax={inv.get("tax")} total={inv.get("total")}'
            )

    print('\nDone. Next manual checks:')
    print('  1) stripe listen --forward-to localhost:5000/api/billing/webhooks/stripe')
    print('  2) Trigger invoice.payment_failed / charge.dispute.created from Dashboard or CLI')
    print('  3) Confirm Portal Billing / Admin Billing + dunning emails (log sink if email off)')
    print(f'  4) Clean up: delete Test Clock {clock_id} in Dashboard → Billing → Test clocks')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('Interrupted', file=sys.stderr)
        raise SystemExit(130)
