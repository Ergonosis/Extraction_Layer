"""Retry Stripe meter events that failed after ledger write."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import or_, select

from src.api.extensions import db
from src.billing.meters import Meter
from src.billing.models import BillingUsageLedger, OrganizationBilling, _utcnow
from src.billing.stripe_adapter import get_stripe_adapter

logger = logging.getLogger(__name__)

# Backoff after attempt N failure (attempt already incremented).
_BACKOFF_MINUTES = (1, 5, 30, 120)
_MAX_ATTEMPTS = 8


def _next_delay_minutes(attempts: int) -> int:
    idx = min(max(attempts - 1, 0), len(_BACKOFF_MINUTES) - 1)
    return _BACKOFF_MINUTES[idx]


def run_meter_retry_pass(*, limit: int = 50) -> dict:
    """Send due outbox rows to Stripe. Returns counts."""
    now = _utcnow()
    rows = (
        db.session.execute(
            select(BillingUsageLedger)
            .where(
                BillingUsageLedger.stripe_send_status.in_(('pending', 'failed')),
                or_(BillingUsageLedger.next_attempt_at.is_(None), BillingUsageLedger.next_attempt_at <= now),
            )
            .order_by(BillingUsageLedger.id.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    sent = 0
    failed = 0
    skipped = 0
    adapter = get_stripe_adapter()

    for row in rows:
        if row.stripe_send_attempts >= _MAX_ATTEMPTS:
            row.stripe_send_status = 'failed'
            skipped += 1
            continue

        billing = (
            db.session.execute(
                select(OrganizationBilling).where(OrganizationBilling.organization_id == row.organization_id)
            )
            .scalars()
            .one_or_none()
        )
        customer_id = billing.stripe_customer_id if billing else None

        try:
            event_id = adapter.report_meter_event(
                organization_id=row.organization_id,
                meter=Meter(row.meter),
                quantity=row.quantity,
                identifier=row.idempotency_key,
                stripe_customer_id=customer_id,
            )
            row.stripe_meter_event_id = event_id
            row.stripe_send_status = 'sent'
            row.stripe_send_attempts = int(row.stripe_send_attempts or 0) + 1
            row.last_send_error = None
            row.next_attempt_at = None
            sent += 1
        except Exception as exc:
            attempts = int(row.stripe_send_attempts or 0) + 1
            row.stripe_send_attempts = attempts
            row.last_send_error = str(exc)[:2000]
            if attempts >= _MAX_ATTEMPTS:
                row.stripe_send_status = 'failed'
                row.next_attempt_at = None
            else:
                row.stripe_send_status = 'pending'
                row.next_attempt_at = now + timedelta(minutes=_next_delay_minutes(attempts))
            failed += 1
            logger.warning('meter_retry failed ledger_id=%s attempts=%s err=%s', row.id, attempts, exc)

    db.session.commit()
    return {'checked': len(rows), 'sent': sent, 'failed': failed, 'skipped_max_attempts': skipped}
