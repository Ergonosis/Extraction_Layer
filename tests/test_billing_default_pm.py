"""Default payment method application (mock adapter)."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.billing.payment_methods import apply_default_payment_method
from src.billing.stripe_adapter import MockStripeAdapter, reset_stripe_adapter, set_stripe_adapter


def test_apply_default_payment_method_sets_stripe_and_row():
    adapter = reset_stripe_adapter()
    assert isinstance(adapter, MockStripeAdapter)
    adapter.fixture_pms['pm_123'] = {'brand': 'visa', 'last4': '4242', 'exp_month': 12, 'exp_year': 2030}

    row = MagicMock()
    row.organization_id = 7
    row.stripe_customer_id = 'cus_7'
    row.stripe_subscription_id = 'sub_7'
    row.pm_brand = None
    row.pm_last4 = None
    row.pm_exp_month = None
    row.pm_exp_year = None

    ok = apply_default_payment_method(row, payment_method='pm_123')
    assert ok is True
    assert row.default_payment_method_id == 'pm_123'
    assert row.pm_last4 == '4242'
    assert adapter.default_pm_calls == [
        {'customer_id': 'cus_7', 'payment_method_id': 'pm_123', 'subscription_id': 'sub_7'}
    ]


def test_apply_default_payment_method_from_setup_intent_fixture():
    adapter = MockStripeAdapter()
    adapter.fixture_setup_intents['seti_1'] = 'pm_from_si'
    set_stripe_adapter(adapter)

    row = MagicMock()
    row.organization_id = 1
    row.stripe_customer_id = 'cus_1'
    row.stripe_subscription_id = None
    row.pm_brand = None
    row.pm_last4 = None
    row.pm_exp_month = None
    row.pm_exp_year = None

    ok = apply_default_payment_method(row, setup_intent='seti_1')
    assert ok is True
    assert row.default_payment_method_id == 'pm_from_si'
    assert adapter.default_pm_calls[0]['payment_method_id'] == 'pm_from_si'
