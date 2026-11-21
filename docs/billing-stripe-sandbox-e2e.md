# Stripe sandbox E2E (Test Clocks)

Optional walkthrough for issue #64 billing. **CI does not require this** — unit tests use the mock adapter (`STRIPE_ENABLED=false`).

## What you need

1. Stripe account (test mode)
2. Products / Prices / Billing Meters + Stripe Tax (head office + at least one US registration)
3. Customer Portal + Smart Retries configured in Dashboard
4. Root `.env`:

```env
STRIPE_ENABLED=true
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...   # from `stripe listen` or Dashboard endpoint
STRIPE_SANDBOX_PRICE_ID=price_... # recurring test price
```

Use **only** `sk_test_` keys with the sandbox script (it refuses live keys).

## Automated Test Clock script

From repo root:

```bash
uv run python -m scripts.billing_stripe_sandbox_e2e
uv run python -m scripts.billing_stripe_sandbox_e2e --advance-days 32
uv run python -m scripts.billing_stripe_sandbox_e2e --fail-card
```

The script:

1. Creates a **Test Clock** and a customer frozen on that clock
2. Attaches Visa `4242` (or a declining card with `--fail-card`)
3. Creates a subscription on `STRIPE_SANDBOX_PRICE_ID` with `automatic_tax`
4. Advances the clock (~one billing period) and prints invoices (subtotal / tax / total)

It does **not** hit Portal DB or webhooks by itself — use that next for end-to-end Portal state.

## Portal + webhooks

1. Run migrations (`004_billing_schema`, `005_billing_hardening`) on local Postgres
2. Start the API + portal SPA
3. Forward events:

```bash
stripe listen --forward-to localhost:<api-port>/api/billing/webhooks/stripe
```

4. Map the sandbox Stripe customer to an org in **Admin Billing** (`stripe_customer_id`, price ids, meters)
5. Exercise:

| Scenario              | How                                                                | Expect                                                                   |
| --------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| Checkout / default PM | Customer Checkout or script PM + `checkout.session.completed`      | Card last4 on Billing; Customer default PM in Stripe                     |
| Renewal + tax         | Advance Test Clock                                                 | Invoice with tax; `invoice.paid` → entitlement active                    |
| Failed pay + grace    | `--fail-card` or Dashboard fail                                    | `past_due`, grace, reminder email (log if `BILLING_EMAIL_ENABLED=false`) |
| Dunning suspend       | Wait / set `suspend_after` past + `POST /api/billing/jobs/dunning` | entitlement suspended                                                    |
| Dispute               | Dashboard create test dispute                                      | immediate suspend + admin email; Admin Billing disputes list             |
| Meter outbox          | Force Stripe error then `POST /api/billing/jobs/meter-retry`       | pending → sent                                                           |

Job auth header: `X-Billing-Job-Secret: $BILLING_JOB_SECRET` (same as Cloud Scheduler).

## Pytest (always in CI)

No Stripe account required:

```bash
uv run pytest tests/test_billing_*.py -q
```

Covers webhook grace / paid / dispute / checkout default PM, dunning emails + suspend, meter retry backoff, upcoming-invoice preview payload.

## Cleanup

Delete the Test Clock in Dashboard → **Billing → Test clocks** (cascades clock customers/subscriptions). Do not leave sandbox customers linked to production orgs.
