"""Daily entitlement grace job — reminder emails + suspend; Stripe owns charging."""

from __future__ import annotations

import logging
from datetime import timedelta

from src.api.extensions import db
from src.billing.models import OrganizationBilling, _utcnow
from src.billing.notify import send_billing_email
from src.billing.recipients import org_billing_emails
from src.billing.settings import portal_base_url

logger = logging.getLogger(__name__)

KIND_REMINDER = 'past_due_reminder'
KIND_SUSPENDED = 'access_suspended'


def _days_left(row: OrganizationBilling) -> int | None:
    if not row.suspend_after:
        return None
    delta = row.suspend_after - _utcnow()
    return max(0, int(delta.total_seconds() // 86400))


def _should_send_reminder(row: OrganizationBilling, *, kind: str, min_hours: int = 20) -> bool:
    return not (
        row.last_dunning_email_kind == kind
        and row.last_dunning_email_at
        and _utcnow() - row.last_dunning_email_at < timedelta(hours=min_hours)
    )


def _mark_emailed(row: OrganizationBilling, kind: str) -> None:
    row.last_dunning_email_at = _utcnow()
    row.last_dunning_email_kind = kind


def _send_org_email(organization_id: int, *, subject: str, body: str) -> bool:
    recipients = org_billing_emails(organization_id)
    if not recipients:
        logger.warning('dunning: no emails for org=%s', organization_id)
        return False
    return send_billing_email(to=recipients, subject=subject, body=body)


def notify_past_due_immediate(row: OrganizationBilling) -> None:
    """Called from webhook on invoice.payment_failed (once per failure event)."""
    days = _days_left(row)
    portal = portal_base_url()
    subject = 'Action needed: payment failed for Ergonosis Portal'
    body = (
        'We could not collect your latest Ergonosis Portal payment.\n\n'
        f'Please update your card within {days if days is not None else "a few"} day(s) '
        'to keep full access:\n'
        f'  {portal}/billing\n\n'
        'If you recently updated your card, you can ignore this message once payment succeeds.\n'
    )
    if _send_org_email(row.organization_id, subject=subject, body=body):
        _mark_emailed(row, KIND_REMINDER)
        db.session.commit()


def run_dunning_pass() -> dict:
    """Suspend orgs whose past_due grace elapsed; email reminders while in grace."""
    now = _utcnow()
    rows = (
        db.session.execute(db.select(OrganizationBilling).where(OrganizationBilling.status == 'past_due'))
        .scalars()
        .all()
    )
    reminded = 0
    suspended = 0
    portal = portal_base_url()

    for row in rows:
        if row.suspend_after and row.suspend_after <= now:
            if row.entitlement != 'suspended':
                row.entitlement = 'suspended'
                row.status = 'suspended'
                suspended += 1
                logger.info('billing.dunning suspended org=%s after grace', row.organization_id)
                if _should_send_reminder(row, kind=KIND_SUSPENDED, min_hours=12):
                    subject = 'Ergonosis Portal access suspended — payment overdue'
                    body = (
                        'Your Ergonosis Portal access to paid features has been suspended '
                        'because payment is still overdue.\n\n'
                        f'Update your payment method here:\n  {portal}/billing\n\n'
                        'After payment succeeds, an Ergonosis admin may need to confirm access.\n'
                    )
                    if _send_org_email(row.organization_id, subject=subject, body=body):
                        _mark_emailed(row, KIND_SUSPENDED)
            continue

        if not _should_send_reminder(row, kind=KIND_REMINDER):
            continue

        days = _days_left(row)
        subject = 'Reminder: Ergonosis Portal payment still past due'
        body = (
            'Friendly reminder: your Ergonosis Portal payment is past due.\n\n'
            f'Days remaining before access may be limited: {days if days is not None else "unknown"}.\n'
            f'Update your card:\n  {portal}/billing\n'
        )
        if _send_org_email(row.organization_id, subject=subject, body=body):
            _mark_emailed(row, KIND_REMINDER)
            reminded += 1
            logger.info('billing.dunning reminder org=%s suspend_after=%s', row.organization_id, row.suspend_after)

    db.session.commit()
    return {'reminded': reminded, 'suspended': suspended, 'checked': len(rows)}
