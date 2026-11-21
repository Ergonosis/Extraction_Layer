"""Upcoming invoice preview payload (tax estimate path)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.billing.services import _upcoming_invoice_payload


def test_upcoming_invoice_mock_mode_returns_note():
    row = MagicMock()
    row.stripe_customer_id = 'cus_live'
    row.stripe_subscription_id = 'sub_1'
    payload = _upcoming_invoice_payload(row, mock=True)
    assert payload['subtotal'] is None
    assert payload['tax'] is None
    assert 'mock' in (payload.get('note') or '').lower()


def test_upcoming_invoice_live_adapter_preview():
    row = MagicMock()
    row.stripe_customer_id = 'cus_live_1'
    row.stripe_subscription_id = 'sub_1'

    preview = {
        'currency': 'usd',
        'subtotal': 1000,
        'tax': 80,
        'total': 1080,
        'lines': [{'description': 'Flat', 'amount': 1000}],
        'note': None,
    }
    adapter = MagicMock()
    adapter.preview_upcoming_invoice.return_value = preview

    with patch('src.billing.services.get_stripe_adapter', return_value=adapter):
        payload = _upcoming_invoice_payload(row, mock=False)

    assert payload == preview
    adapter.preview_upcoming_invoice.assert_called_once_with(customer_id='cus_live_1', subscription_id='sub_1')


def test_upcoming_invoice_unavailable_when_preview_empty():
    row = MagicMock()
    row.stripe_customer_id = 'cus_live_2'
    row.stripe_subscription_id = None
    adapter = MagicMock()
    adapter.preview_upcoming_invoice.return_value = None

    with patch('src.billing.services.get_stripe_adapter', return_value=adapter):
        payload = _upcoming_invoice_payload(row, mock=False)

    assert payload['total'] is None
    assert 'unavailable' in (payload.get('note') or '').lower()
