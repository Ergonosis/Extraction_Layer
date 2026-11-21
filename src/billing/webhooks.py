"""Stripe webhook side effects — idempotent by event id."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from src.api.extensions import db
from src.billing.models import OrganizationBilling, StripeWebhookEvent, _utcnow
from src.billing.settings import grace_days

logger = logging.getLogger(__name__)


def get_org_billing(organization_id: int) -> OrganizationBilling | None:
    return (
        db.session.execute(db.select(OrganizationBilling).where(OrganizationBilling.organization_id == organization_id))
        .scalars()
        .one_or_none()
    )


def _org_id_from_metadata(meta: Any) -> int | None:
    if not meta:
        return None
    raw = meta.get('organization_id') if hasattr(meta, 'get') else getattr(meta, 'organization_id', None)
    if raw is None and hasattr(meta, 'to_dict'):
        raw = meta.to_dict().get('organization_id')
    try:
        return int(raw) if raw is not None else None
    except TypeError, ValueError:
        return None


def _billing_by_customer(customer_id: str | None) -> OrganizationBilling | None:
    if not customer_id:
        return None
    return (
        db.session.execute(db.select(OrganizationBilling).where(OrganizationBilling.stripe_customer_id == customer_id))
        .scalars()
        .one_or_none()
    )


def _obj_get(obj: Any, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def process_stripe_event(event: Any) -> dict[str, Any]:
    """Apply one Stripe event. Returns a small result dict for the HTTP layer."""
    event_id = str(_obj_get(event, 'id') or '')
    event_type = str(_obj_get(event, 'type') or '')
    if not event_id:
        raise ValueError('event missing id')

    existing = db.session.get(StripeWebhookEvent, event_id)
    if existing is not None:
        return {'duplicate': True, 'event_id': event_id, 'type': event_type}

    data_object = _obj_get(_obj_get(event, 'data'), 'object')
    handled = _dispatch(event_type, data_object)

    db.session.add(StripeWebhookEvent(event_id=event_id, event_type=event_type, processed_at=_utcnow()))
    db.session.commit()
    return {'duplicate': False, 'event_id': event_id, 'type': event_type, 'handled': handled}


def _dispatch(event_type: str, obj: Any) -> bool:
    if event_type == 'checkout.session.completed':
        return _on_checkout_completed(obj)
    if event_type == 'setup_intent.succeeded':
        return _on_setup_intent_succeeded(obj)
    if event_type in {'invoice.paid', 'invoice.payment_succeeded'}:
        return _on_invoice_paid(obj)
    if event_type == 'invoice.payment_failed':
        return _on_invoice_payment_failed(obj)
    if event_type.startswith('customer.subscription.'):
        return _on_subscription(obj)
    if event_type in {'payment_method.attached', 'payment_method.automatically_updated'}:
        return _on_payment_method(obj)
    if event_type == 'charge.dispute.created':
        return _on_dispute_created(obj)
    if event_type == 'charge.dispute.closed':
        return _on_dispute_closed(obj)
    if event_type == 'radar.early_fraud_warning.created':
        logger.warning('Stripe early fraud warning: %s', _obj_get(obj, 'id'))
        return True
    if event_type == 'charge.refunded':
        logger.info('Stripe charge refunded: %s', _obj_get(obj, 'id'))
        return True
    return False


def _on_checkout_completed(obj: Any) -> bool:
    from src.billing.payment_methods import apply_default_payment_method

    org_id = _org_id_from_metadata(_obj_get(obj, 'metadata')) or _org_id_from_metadata(
        {'organization_id': _obj_get(obj, 'client_reference_id')}
    )
    customer_id = _obj_get(obj, 'customer')
    subscription_id = _obj_get(obj, 'subscription')
    setup_intent = _obj_get(obj, 'setup_intent')
    payment_intent = _obj_get(obj, 'payment_intent')
    row = get_org_billing(org_id) if org_id else _billing_by_customer(customer_id)
    if row is None:
        logger.warning('checkout.session.completed with no matching org billing')
        return False
    if customer_id:
        row.stripe_customer_id = str(customer_id)
    if subscription_id:
        row.stripe_subscription_id = str(subscription_id)
        row.status = 'active'
        row.entitlement = 'enabled'
    apply_default_payment_method(
        row,
        payment_method=_obj_get(obj, 'payment_method'),
        setup_intent=setup_intent,
        payment_intent=payment_intent,
        subscription=subscription_id,
    )
    db.session.commit()
    return True


def _on_setup_intent_succeeded(obj: Any) -> bool:
    from src.billing.payment_methods import apply_default_payment_method

    customer_id = _obj_get(obj, 'customer')
    row = _billing_by_customer(str(customer_id) if customer_id else None)
    if row is None:
        return False
    apply_default_payment_method(row, payment_method=_obj_get(obj, 'payment_method'), setup_intent=obj)
    db.session.commit()
    return True


def _on_invoice_paid(obj: Any) -> bool:
    customer_id = _obj_get(obj, 'customer')
    row = _billing_by_customer(str(customer_id) if customer_id else None)
    if row is None:
        return False
    row.status = 'active'
    row.entitlement = 'enabled'
    row.past_due_since = None
    row.suspend_after = None
    sub = _obj_get(obj, 'subscription')
    if sub:
        row.stripe_subscription_id = str(sub)
    db.session.commit()
    return True


def _on_invoice_payment_failed(obj: Any) -> bool:
    customer_id = _obj_get(obj, 'customer')
    row = _billing_by_customer(str(customer_id) if customer_id else None)
    if row is None:
        return False
    now = _utcnow()
    row.status = 'past_due'
    if row.past_due_since is None:
        row.past_due_since = now
    row.suspend_after = now + timedelta(days=grace_days())
    # Keep entitlement enabled during grace.
    if row.entitlement != 'suspended':
        row.entitlement = 'enabled'
    db.session.commit()
    try:
        from src.billing.dunning import notify_past_due_immediate

        notify_past_due_immediate(row)
    except Exception:
        logger.exception('payment_failed email failed org=%s', row.organization_id)
    return True


def _on_subscription(obj: Any) -> bool:
    from src.billing.payment_methods import apply_default_payment_method

    customer_id = _obj_get(obj, 'customer')
    row = _billing_by_customer(str(customer_id) if customer_id else None)
    if row is None:
        return False
    sub_id = _obj_get(obj, 'id')
    if sub_id:
        row.stripe_subscription_id = str(sub_id)
    status = str(_obj_get(obj, 'status') or '')
    if status in {'active', 'trialing'}:
        row.status = 'active'
        row.entitlement = 'enabled'
    elif status == 'past_due':
        row.status = 'past_due'
    elif status in {'canceled', 'unpaid', 'incomplete_expired'}:
        row.status = 'canceled' if status == 'canceled' else 'suspended'
        if status != 'past_due':
            row.entitlement = 'suspended'
    apply_default_payment_method(row, subscription=obj)
    db.session.commit()
    return True


def _on_payment_method(obj: Any) -> bool:
    from src.billing.payment_methods import apply_default_payment_method

    customer_id = _obj_get(obj, 'customer')
    row = _billing_by_customer(str(customer_id) if customer_id else None)
    if row is None:
        return False
    apply_default_payment_method(row, payment_method=obj)
    db.session.commit()
    return True


def _on_dispute_created(obj: Any) -> bool:
    # Dispute is on a charge; charge has customer.
    charge = _obj_get(obj, 'charge')
    customer_id = _obj_get(obj, 'customer')
    row = _billing_by_customer(str(customer_id) if customer_id else None)
    if row is None and charge:
        logger.warning('dispute.created without customer mapping charge=%s', charge)
        return False
    if row is None:
        return False
    row.has_open_dispute = True
    row.dispute_opened_at = _utcnow()
    row.status = 'suspended'
    row.entitlement = 'suspended'
    db.session.commit()
    try:
        from src.billing.notify import send_billing_email
        from src.billing.recipients import platform_admin_emails
        from src.billing.settings import portal_base_url

        admins = platform_admin_emails()
        if admins:
            send_billing_email(
                to=admins,
                subject=f'Dispute opened — org {row.organization_id} suspended',
                body=(
                    f'A Stripe dispute was opened for organization_id={row.organization_id}.\n'
                    f'Portal entitlement is suspended.\n'
                    f'Review in Admin Billing: {portal_base_url()}/admin/billing\n'
                    f'Dispute/charge ref: {_obj_get(obj, "id")} / {charge}\n'
                ),
            )
    except Exception:
        logger.exception('dispute admin email failed org=%s', row.organization_id)
    return True


def _on_dispute_closed(obj: Any) -> bool:
    customer_id = _obj_get(obj, 'customer')
    row = _billing_by_customer(str(customer_id) if customer_id else None)
    if row is None:
        return False
    row.has_open_dispute = False
    # Do not auto-resume; admin must resume after review.
    db.session.commit()
    return True
