"""Webhook state machine tests against the mock adapter path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from src.billing.notify import clear_sent_emails, sent_emails
from src.billing.stripe_adapter import MockStripeAdapter, reset_stripe_adapter
from src.billing.webhooks import process_stripe_event


def _row(**overrides):
    row = MagicMock()
    row.organization_id = 42
    row.stripe_customer_id = 'cus_42'
    row.stripe_subscription_id = None
    row.past_due_since = None
    row.suspend_after = None
    row.entitlement = 'enabled'
    row.status = 'active'
    row.has_open_dispute = False
    row.dispute_opened_at = None
    row.default_payment_method_id = None
    row.pm_brand = None
    row.pm_last4 = None
    row.pm_exp_month = None
    row.pm_exp_year = None
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def test_process_stripe_event_dedupes():
    event = {'id': 'evt_1', 'type': 'invoice.paid', 'data': {'object': {'customer': 'cus_x'}}}
    with (
        patch('src.billing.webhooks.db') as mock_db,
        patch('src.billing.webhooks._billing_by_customer', return_value=None),
    ):
        mock_db.session.get.return_value = MagicMock()  # already processed
        result = process_stripe_event(event)
        assert result['duplicate'] is True


def test_invoice_payment_failed_sets_grace(monkeypatch):
    monkeypatch.setenv('BILLING_EMAIL_ENABLED', 'false')
    clear_sent_emails()
    row = _row(past_due_since=None, entitlement='enabled')
    event = {'id': 'evt_fail_1', 'type': 'invoice.payment_failed', 'data': {'object': {'customer': 'cus_42'}}}
    with (
        patch('src.billing.webhooks.db') as mock_db,
        patch('src.billing.webhooks._billing_by_customer', return_value=row),
        patch('src.billing.webhooks.grace_days', return_value=5),
        patch('src.billing.dunning.org_billing_emails', return_value=['billing@example.com']),
    ):
        mock_db.session.get.return_value = None
        result = process_stripe_event(event)
        assert result['handled'] is True
        assert row.status == 'past_due'
        assert row.suspend_after is not None
        assert row.entitlement == 'enabled'
        assert any('payment failed' in e['subject'].lower() for e in sent_emails())


def test_invoice_paid_clears_grace():
    past = datetime.now(UTC) - timedelta(days=1)
    row = _row(
        status='past_due',
        entitlement='enabled',
        past_due_since=past,
        suspend_after=past + timedelta(days=5),
        stripe_subscription_id='sub_old',
    )
    event = {
        'id': 'evt_paid_1',
        'type': 'invoice.paid',
        'data': {'object': {'customer': 'cus_42', 'subscription': 'sub_new'}},
    }
    with (
        patch('src.billing.webhooks.db') as mock_db,
        patch('src.billing.webhooks._billing_by_customer', return_value=row),
    ):
        mock_db.session.get.return_value = None
        result = process_stripe_event(event)
        assert result['handled'] is True
        assert row.status == 'active'
        assert row.entitlement == 'enabled'
        assert row.past_due_since is None
        assert row.suspend_after is None
        assert row.stripe_subscription_id == 'sub_new'


def test_dispute_created_suspends_and_emails_admins(monkeypatch):
    monkeypatch.setenv('BILLING_EMAIL_ENABLED', 'false')
    clear_sent_emails()
    row = _row(status='active', entitlement='enabled')
    event = {
        'id': 'evt_disp_1',
        'type': 'charge.dispute.created',
        'data': {'object': {'id': 'dp_1', 'customer': 'cus_42', 'charge': 'ch_1'}},
    }
    with (
        patch('src.billing.webhooks.db') as mock_db,
        patch('src.billing.webhooks._billing_by_customer', return_value=row),
        patch('src.billing.recipients.platform_admin_emails', return_value=['admin@ergonosis.com']),
    ):
        mock_db.session.get.return_value = None
        result = process_stripe_event(event)
        assert result['handled'] is True
        assert row.has_open_dispute is True
        assert row.status == 'suspended'
        assert row.entitlement == 'suspended'
        assert any('Dispute opened' in e['subject'] for e in sent_emails())


def test_checkout_completed_sets_default_pm():
    adapter = reset_stripe_adapter()
    assert isinstance(adapter, MockStripeAdapter)
    adapter.fixture_pms['pm_checkout'] = {'brand': 'visa', 'last4': '4242', 'exp_month': 12, 'exp_year': 2030}
    row = _row(stripe_customer_id='cus_42', stripe_subscription_id=None)
    event = {
        'id': 'evt_cs_1',
        'type': 'checkout.session.completed',
        'data': {
            'object': {
                'customer': 'cus_42',
                'subscription': 'sub_99',
                'payment_method': 'pm_checkout',
                'metadata': {'organization_id': '42'},
            }
        },
    }
    with patch('src.billing.webhooks.db') as mock_db, patch('src.billing.webhooks.get_org_billing', return_value=row):
        mock_db.session.get.return_value = None
        result = process_stripe_event(event)
        assert result['handled'] is True
        assert row.stripe_subscription_id == 'sub_99'
        assert row.status == 'active'
        assert row.default_payment_method_id == 'pm_checkout'
        assert row.pm_last4 == '4242'
        assert adapter.default_pm_calls == [
            {'customer_id': 'cus_42', 'payment_method_id': 'pm_checkout', 'subscription_id': 'sub_99'}
        ]


def test_dispute_closed_clears_flag_without_auto_resume():
    row = _row(has_open_dispute=True, status='suspended', entitlement='suspended')
    event = {
        'id': 'evt_disp_close_1',
        'type': 'charge.dispute.closed',
        'data': {'object': {'customer': 'cus_42', 'id': 'dp_1'}},
    }
    with (
        patch('src.billing.webhooks.db') as mock_db,
        patch('src.billing.webhooks._billing_by_customer', return_value=row),
    ):
        mock_db.session.get.return_value = None
        result = process_stripe_event(event)
        assert result['handled'] is True
        assert row.has_open_dispute is False
        assert row.entitlement == 'suspended'
