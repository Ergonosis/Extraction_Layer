"""Meter outbox retry with mock Stripe adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from src.billing.meter_retry import run_meter_retry_pass
from src.billing.meters import Meter
from src.billing.stripe_adapter import MockStripeAdapter, reset_stripe_adapter, set_stripe_adapter


def _pending_row(**overrides):
    row = MagicMock()
    row.id = 1
    row.organization_id = 9
    row.meter = Meter.EXPORTS.value
    row.quantity = 2
    row.idempotency_key = 'retry-key-1'
    row.stripe_send_status = 'pending'
    row.stripe_send_attempts = 1
    row.next_attempt_at = datetime.now(UTC) - timedelta(minutes=1)
    row.stripe_meter_event_id = None
    row.last_send_error = 'boom'
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def test_meter_retry_sends_pending_row():
    adapter = reset_stripe_adapter()
    assert isinstance(adapter, MockStripeAdapter)

    row = _pending_row()
    billing = MagicMock()
    billing.stripe_customer_id = 'cus_9'

    ledger_result = MagicMock()
    ledger_result.scalars.return_value.all.return_value = [row]
    billing_result = MagicMock()
    billing_result.scalars.return_value.one_or_none.return_value = billing

    with patch('src.billing.meter_retry.db') as mock_db:
        mock_db.session.execute.side_effect = [ledger_result, billing_result]
        out = run_meter_retry_pass(limit=10)

    assert out['sent'] == 1
    assert out['failed'] == 0
    assert row.stripe_send_status == 'sent'
    assert row.stripe_meter_event_id is not None
    assert len(adapter.events) == 1
    mock_db.session.commit.assert_called()


def test_meter_retry_backoff_then_succeeds_on_second_pass():
    """Failed send stays pending with next_attempt_at; next pass marks sent."""

    class FlakyAdapter(MockStripeAdapter):
        def __init__(self):
            super().__init__()
            self.fail_once = True

        def report_meter_event(self, **kwargs):
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError('stripe down')
            return super().report_meter_event(**kwargs)

    adapter = FlakyAdapter()
    set_stripe_adapter(adapter)

    row = _pending_row(stripe_send_attempts=0, last_send_error=None)
    billing = MagicMock()
    billing.stripe_customer_id = 'cus_9'

    def _execute_pair(ledger_rows):
        ledger_result = MagicMock()
        ledger_result.scalars.return_value.all.return_value = ledger_rows
        billing_result = MagicMock()
        billing_result.scalars.return_value.one_or_none.return_value = billing
        return [ledger_result, billing_result]

    with patch('src.billing.meter_retry.db') as mock_db:
        mock_db.session.execute.side_effect = _execute_pair([row])
        first = run_meter_retry_pass(limit=10)

    assert first['failed'] == 1
    assert first['sent'] == 0
    assert row.stripe_send_status == 'pending'
    assert row.stripe_send_attempts == 1
    assert row.next_attempt_at is not None
    assert row.last_send_error

    # Due again
    row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)

    with patch('src.billing.meter_retry.db') as mock_db:
        mock_db.session.execute.side_effect = _execute_pair([row])
        second = run_meter_retry_pass(limit=10)

    assert second['sent'] == 1
    assert second['failed'] == 0
    assert row.stripe_send_status == 'sent'
    assert row.next_attempt_at is None
    assert len(adapter.events) == 1


def test_meter_retry_skips_max_attempts():
    reset_stripe_adapter()
    row = _pending_row(stripe_send_attempts=8, stripe_send_status='pending')
    ledger_result = MagicMock()
    ledger_result.scalars.return_value.all.return_value = [row]

    with patch('src.billing.meter_retry.db') as mock_db:
        mock_db.session.execute.side_effect = [ledger_result]
        out = run_meter_retry_pass(limit=10)

    assert out['skipped_max_attempts'] == 1
    assert out['sent'] == 0
    assert row.stripe_send_status == 'failed'
