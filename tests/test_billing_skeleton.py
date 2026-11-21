"""Smoke tests for the billing package port + mock Stripe adapter."""

from __future__ import annotations

import pytest

from src.billing import EntitlementError, Meter, assert_org_entitled
from src.billing.models import BillingUsageLedger, OrganizationBilling, PlatformAdmin
from src.billing.stripe_adapter import MockStripeAdapter, reset_stripe_adapter


@pytest.fixture(autouse=True)
def _fresh_mock_adapter():
    reset_stripe_adapter()
    yield
    reset_stripe_adapter()


def test_assert_org_entitled_rejects_invalid_org():
    with pytest.raises(EntitlementError):
        assert_org_entitled(0)


def test_billing_models_are_importable():
    assert OrganizationBilling.__tablename__ == 'organization_billing'
    assert BillingUsageLedger.__tablename__ == 'billing_usage_ledger'
    assert PlatformAdmin.__tablename__ == 'platform_admins'


def test_mock_adapter_idempotent_without_db():
    adapter = reset_stripe_adapter()
    assert isinstance(adapter, MockStripeAdapter)
    adapter.report_meter_event(organization_id=1, meter=Meter.EXPORTS, quantity=1, identifier='k1')
    adapter.report_meter_event(organization_id=1, meter=Meter.EXPORTS, quantity=1, identifier='k1')
    assert len(adapter.events) == 1


def test_stripe_disabled_builds_mock(monkeypatch):
    from src.billing.stripe_adapter import build_stripe_adapter, reload_stripe_adapter

    monkeypatch.setenv('STRIPE_ENABLED', 'false')
    adapter = reload_stripe_adapter()
    assert adapter.mock is True
    assert isinstance(build_stripe_adapter(), MockStripeAdapter)
