"""Record billable usage through the billing port."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from src.api.extensions import db
from src.billing.meters import Meter
from src.billing.models import BillingUsageLedger, OrganizationBilling, _utcnow
from src.billing.stripe_adapter import get_stripe_adapter

logger = logging.getLogger(__name__)


def report_usage(organization_id: int, meter: Meter | str, quantity: int = 1, *, idempotency_key: str) -> None:
    """Write the usage ledger, then enqueue a Stripe (or mock) meter event."""
    if organization_id <= 0:
        raise ValueError('organization_id must be a positive integer')
    if quantity <= 0:
        raise ValueError('quantity must be positive')
    if not idempotency_key or not str(idempotency_key).strip():
        raise ValueError('idempotency_key is required')

    meter_name = Meter(meter) if not isinstance(meter, Meter) else meter
    key = str(idempotency_key).strip()

    existing = (
        db.session.execute(db.select(BillingUsageLedger).where(BillingUsageLedger.idempotency_key == key))
        .scalars()
        .one_or_none()
    )
    if existing is not None:
        return

    row = BillingUsageLedger(
        organization_id=organization_id,
        meter=str(meter_name),
        quantity=quantity,
        idempotency_key=key,
        stripe_send_status='pending',
        stripe_send_attempts=0,
    )
    try:
        with db.session.begin_nested():
            db.session.add(row)
            db.session.flush()
    except IntegrityError:
        return

    billing = (
        db.session.execute(db.select(OrganizationBilling).where(OrganizationBilling.organization_id == organization_id))
        .scalars()
        .one_or_none()
    )
    customer_id = billing.stripe_customer_id if billing else None

    adapter = get_stripe_adapter()
    try:
        event_id = adapter.report_meter_event(
            organization_id=organization_id,
            meter=meter_name,
            quantity=quantity,
            identifier=key,
            stripe_customer_id=customer_id,
        )
    except Exception as exc:
        logger.exception('Stripe meter event failed org=%s meter=%s key=%s', organization_id, meter_name, key)
        row.stripe_send_status = 'pending'
        row.stripe_send_attempts = 1
        row.last_send_error = str(exc)[:2000]
        row.next_attempt_at = _utcnow() + timedelta(minutes=1)
        db.session.commit()
        return

    row.stripe_meter_event_id = event_id
    row.stripe_send_status = 'sent'
    row.stripe_send_attempts = 1
    row.last_send_error = None
    row.next_attempt_at = None
    db.session.commit()
    logger.debug(
        'billing.report_usage org=%s meter=%s qty=%s key=%s event=%s',
        organization_id,
        meter_name,
        quantity,
        key,
        event_id,
    )
