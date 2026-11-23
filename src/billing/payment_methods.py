"""Apply Stripe default payment methods onto org billing rows."""

from __future__ import annotations

import logging
from typing import Any

from src.billing.models import OrganizationBilling
from src.billing.stripe_adapter import get_stripe_adapter

logger = logging.getLogger(__name__)


def apply_default_payment_method(
    row: OrganizationBilling,
    *,
    payment_method: Any = None,
    setup_intent: Any = None,
    payment_intent: Any = None,
    subscription: Any = None,
) -> bool:
    """Resolve pm id, persist locally, and set Stripe Customer/Subscription defaults.

    Returns True if a payment method was applied.
    """
    adapter = get_stripe_adapter()
    customer_id = row.stripe_customer_id
    if not customer_id:
        return False

    sub_id = row.stripe_subscription_id
    if subscription and isinstance(subscription, str):
        sub_id = subscription
    elif subscription and isinstance(subscription, dict) and subscription.get('id'):
        sub_id = str(subscription['id'])

    pm_id = adapter.resolve_payment_method_id(
        payment_method=payment_method,
        setup_intent=setup_intent,
        payment_intent=payment_intent,
        subscription=subscription if not isinstance(subscription, str) else None,
    )
    # If subscription was only an id string, still try resolve with it.
    if not pm_id and isinstance(subscription, str):
        pm_id = adapter.resolve_payment_method_id(subscription=subscription)

    if not pm_id:
        logger.info('billing.pm no payment method resolved org=%s customer=%s', row.organization_id, customer_id)
        return False

    row.default_payment_method_id = pm_id
    try:
        card = adapter.get_payment_method_card(pm_id)
        if card:
            row.pm_brand = card.get('brand') or row.pm_brand
            row.pm_last4 = card.get('last4') or row.pm_last4
            row.pm_exp_month = card.get('exp_month') or row.pm_exp_month
            row.pm_exp_year = card.get('exp_year') or row.pm_exp_year
    except Exception:
        logger.exception('billing.pm card display fetch failed pm=%s', pm_id)

    try:
        adapter.set_default_payment_method(customer_id=customer_id, payment_method_id=pm_id, subscription_id=sub_id)
    except Exception:
        logger.exception(
            'billing.pm Stripe default PM update failed org=%s customer=%s pm=%s',
            row.organization_id,
            customer_id,
            pm_id,
        )
        return False

    logger.info(
        'billing.pm default set org=%s customer=%s pm=%s sub=%s', row.organization_id, customer_id, pm_id, sub_id
    )
    return True


def sync_payment_method_from_stripe(row: OrganizationBilling) -> bool:
    """Backfill local card-on-file when Stripe has a PM but webhooks never updated us."""
    changed = False
    if not (row.pm_last4 and row.default_payment_method_id):
        customer_id = row.stripe_customer_id
        if not customer_id or str(customer_id).startswith('mock_'):
            return False
        adapter = get_stripe_adapter()
        if adapter.mock:
            return False
        try:
            pm_id = adapter.get_customer_default_or_latest_card_pm(str(customer_id))
        except Exception:
            logger.exception('billing.pm sync lookup failed org=%s', row.organization_id)
            return False
        if not pm_id:
            return False
        changed = apply_default_payment_method(row, payment_method=pm_id)

    # Card-only Checkout (setup mode) never creates a subscription; still leave setup_required.
    if (changed or row.pm_last4 or row.default_payment_method_id) and row.status == 'setup_required':
        row.status = 'active'
        row.entitlement = 'enabled'
        changed = True
    return changed
