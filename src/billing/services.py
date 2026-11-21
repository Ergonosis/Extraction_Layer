"""Billing application services (DB + Stripe adapter; no HTTP)."""

from __future__ import annotations

from typing import Any

from src.api.extensions import db
from src.api.models import Organization, User
from src.billing.models import BillingAdminEvent, OrganizationBilling, _utcnow
from src.billing.settings import stripe_enabled, stripe_publishable_key
from src.billing.stripe_adapter import get_stripe_adapter


def get_org_billing(organization_id: int) -> OrganizationBilling | None:
    return (
        db.session.execute(db.select(OrganizationBilling).where(OrganizationBilling.organization_id == organization_id))
        .scalars()
        .one_or_none()
    )


def get_or_create_org_billing(organization_id: int) -> OrganizationBilling:
    row = get_org_billing(organization_id)
    if row is not None:
        return row
    org = db.session.get(Organization, organization_id)
    if org is None:
        raise ValueError(f'organization {organization_id} not found')
    row = OrganizationBilling(organization_id=organization_id)
    db.session.add(row)
    db.session.commit()
    return row


def _billing_public_dict(row: OrganizationBilling) -> dict[str, Any]:
    return {
        'organization_id': row.organization_id,
        'status': row.status,
        'entitlement': row.entitlement,
        'flat_enabled': row.flat_enabled,
        'exports_enabled': row.exports_enabled,
        'api_calls_enabled': row.api_calls_enabled,
        'included_exports': row.included_exports,
        'included_api_calls': row.included_api_calls,
        'terms_markdown': row.terms_markdown,
        'past_due_since': row.past_due_since.isoformat() if row.past_due_since else None,
        'suspend_after': row.suspend_after.isoformat() if row.suspend_after else None,
        'has_open_dispute': row.has_open_dispute,
        'pm_brand': row.pm_brand,
        'pm_last4': row.pm_last4,
        'stripe_customer_id': row.stripe_customer_id,
        'stripe_subscription_id': row.stripe_subscription_id,
        'stripe_flat_price_id': row.stripe_flat_price_id,
        'stripe_exports_price_id': row.stripe_exports_price_id,
        'stripe_api_calls_price_id': row.stripe_api_calls_price_id,
    }


def _is_mock() -> bool:
    return bool(getattr(get_stripe_adapter(), 'mock', True)) or not stripe_enabled()


def _upcoming_invoice_payload(row: OrganizationBilling | None, *, mock: bool) -> dict[str, Any]:
    if mock or row is None or not row.stripe_customer_id or str(row.stripe_customer_id).startswith('mock_'):
        return {
            'currency': 'usd',
            'subtotal': None,
            'tax': None,
            'total': None,
            'lines': [],
            'note': 'Billing is in mock mode. No live charges or tax.',
        }
    adapter = get_stripe_adapter()
    preview = adapter.preview_upcoming_invoice(
        customer_id=row.stripe_customer_id, subscription_id=row.stripe_subscription_id
    )
    if not preview:
        return {
            'currency': 'usd',
            'subtotal': None,
            'tax': None,
            'total': None,
            'lines': [],
            'note': 'Upcoming invoice preview unavailable yet (complete Checkout or wait for meter aggregation).',
        }
    return preview


def customer_summary(organization_id: int) -> dict[str, Any]:
    mock = _is_mock()
    row = get_org_billing(organization_id)
    if row is None:
        return {
            'organization_id': organization_id,
            'status': 'setup_required',
            'entitlement': 'enabled',
            'flat_enabled': False,
            'exports_enabled': False,
            'api_calls_enabled': False,
            'included_exports': 0,
            'included_api_calls': 0,
            'terms_markdown': None,
            'stripe_customer_id': None,
            'usage': {'exports': 0, 'api_calls': 0},
            'upcoming_invoice': _upcoming_invoice_payload(None, mock=mock),
            'stripe_enabled': stripe_enabled(),
            'publishable_key': stripe_publishable_key() if stripe_enabled() else None,
            'mock': mock,
        }
    usage = usage_totals(organization_id)
    return {
        **_billing_public_dict(row),
        'usage': usage,
        'upcoming_invoice': _upcoming_invoice_payload(row, mock=mock),
        'stripe_enabled': stripe_enabled(),
        'publishable_key': stripe_publishable_key() if stripe_enabled() else None,
        'mock': mock,
    }


def usage_totals(organization_id: int) -> dict[str, int]:
    from sqlalchemy import func

    from src.billing.models import BillingUsageLedger

    rows = db.session.execute(
        db.select(BillingUsageLedger.meter, func.coalesce(func.sum(BillingUsageLedger.quantity), 0))
        .where(BillingUsageLedger.organization_id == organization_id)
        .group_by(BillingUsageLedger.meter)
    ).all()
    totals = {'exports': 0, 'api_calls': 0}
    for meter, total in rows:
        if meter in totals:
            totals[meter] = int(total)
    return totals


def list_invoices(organization_id: int) -> dict[str, Any]:
    row = get_org_billing(organization_id)
    adapter = get_stripe_adapter()
    if row is None or not row.stripe_customer_id:
        return {'invoices': [], 'mock': adapter.mock}
    invoices = adapter.list_invoices(customer_id=row.stripe_customer_id)
    return {'invoices': invoices, 'mock': adapter.mock}


def _checkout_line_items(row: OrganizationBilling) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if row.flat_enabled and row.stripe_flat_price_id:
        items.append({'price': row.stripe_flat_price_id, 'quantity': 1})
    if row.exports_enabled and row.stripe_exports_price_id:
        items.append({'price': row.stripe_exports_price_id})
    if row.api_calls_enabled and row.stripe_api_calls_price_id:
        items.append({'price': row.stripe_api_calls_price_id})
    return items


def create_setup_session(organization_id: int, *, actor_user_id: int | None = None) -> dict[str, Any]:
    row = get_or_create_org_billing(organization_id)
    adapter = get_stripe_adapter()

    email = None
    name = None
    if actor_user_id:
        user = db.session.get(User, actor_user_id)
        if user:
            email = user.email
            name = user.display_name
    org = db.session.get(Organization, organization_id)
    if org and not name:
        name = org.name

    customer_id = adapter.ensure_customer(
        organization_id=organization_id, email=email, name=name, existing_customer_id=row.stripe_customer_id
    )
    row.stripe_customer_id = customer_id
    db.session.commit()

    line_items = _checkout_line_items(row)
    mode = 'subscription' if line_items else 'setup'
    result = adapter.create_checkout_session(
        organization_id=organization_id, customer_id=customer_id, line_items=line_items, mode=mode
    )
    return {'session_id': result.session_id, 'url': result.url, 'mock': result.mock, 'mode': mode}


def create_portal_session(organization_id: int) -> dict[str, Any]:
    row = get_org_billing(organization_id)
    if row is None or not row.stripe_customer_id:
        raise ValueError('billing not set up for organization')
    adapter = get_stripe_adapter()
    result = adapter.create_portal_session(customer_id=row.stripe_customer_id)
    return {'url': result.url, 'mock': result.mock}


def admin_list_orgs() -> list[dict[str, Any]]:
    orgs = db.session.execute(db.select(Organization).order_by(Organization.id)).scalars().all()
    out: list[dict[str, Any]] = []
    for org in orgs:
        billing = get_org_billing(org.id)
        out.append(
            {
                'organization_id': org.id,
                'name': org.name,
                'ms_tenant_id': org.ms_tenant_id,
                'billing_status': billing.status if billing else 'setup_required',
                'entitlement': billing.entitlement if billing else 'enabled',
            }
        )
    return out


def admin_get_org(organization_id: int) -> dict[str, Any]:
    org = db.session.get(Organization, organization_id)
    if org is None:
        raise LookupError('organization not found')
    row = get_org_billing(organization_id)
    return {
        'organization_id': org.id,
        'name': org.name,
        'ms_tenant_id': org.ms_tenant_id,
        'billing': _billing_public_dict(row) if row else None,
        'usage': usage_totals(organization_id),
        'stripe_enabled': stripe_enabled(),
        'mock': _is_mock(),
    }


def admin_upsert_org_plan(
    organization_id: int, *, actor_user_id: int | None, payload: dict[str, Any]
) -> dict[str, Any]:
    org = db.session.get(Organization, organization_id)
    if org is None:
        raise LookupError('organization not found')

    row = get_or_create_org_billing(organization_id)
    if 'flat_enabled' in payload:
        row.flat_enabled = bool(payload['flat_enabled'])
    if 'exports_enabled' in payload:
        row.exports_enabled = bool(payload['exports_enabled'])
    if 'api_calls_enabled' in payload:
        row.api_calls_enabled = bool(payload['api_calls_enabled'])
    if 'included_exports' in payload:
        row.included_exports = int(payload['included_exports'])
    if 'included_api_calls' in payload:
        row.included_api_calls = int(payload['included_api_calls'])
    if 'terms_markdown' in payload:
        row.terms_markdown = payload['terms_markdown']
    if 'stripe_flat_price_id' in payload:
        row.stripe_flat_price_id = payload['stripe_flat_price_id'] or None
    if 'stripe_exports_price_id' in payload:
        row.stripe_exports_price_id = payload['stripe_exports_price_id'] or None
    if 'stripe_api_calls_price_id' in payload:
        row.stripe_api_calls_price_id = payload['stripe_api_calls_price_id'] or None

    if (
        row.status == 'setup_required'
        and (row.flat_enabled or row.exports_enabled or row.api_calls_enabled)
        and _is_mock()
    ):
        # Mock path: invent ids so local UI can proceed without Stripe.
        if not row.stripe_customer_id:
            row.stripe_customer_id = f'mock_cus_{organization_id}'
        if not row.stripe_subscription_id:
            row.stripe_subscription_id = f'mock_sub_{organization_id}'
        row.status = 'active'
        # Live path: leave setup_required until Checkout completes via webhook.

    db.session.add(
        BillingAdminEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action='plan.upsert',
            detail_json={k: payload.get(k) for k in payload},
            created_at=_utcnow(),
        )
    )
    db.session.commit()
    return admin_get_org(organization_id)


def admin_resume(organization_id: int, *, actor_user_id: int | None) -> dict[str, Any]:
    row = get_org_billing(organization_id)
    if row is None:
        raise LookupError('billing not found')
    row.entitlement = 'enabled'
    row.has_open_dispute = False
    if row.status in {'suspended', 'past_due'}:
        row.status = 'active'
        row.past_due_since = None
        row.suspend_after = None
    db.session.add(
        BillingAdminEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action='entitlement.resume',
            detail_json={},
            created_at=_utcnow(),
        )
    )
    db.session.commit()
    return admin_get_org(organization_id)


def admin_refund(organization_id: int, *, actor_user_id: int | None, invoice_id: str | None = None) -> dict[str, Any]:
    row = get_org_billing(organization_id)
    if row is None:
        raise LookupError('billing not found')
    if not invoice_id:
        raise ValueError('invoice_id is required')

    adapter = get_stripe_adapter()
    result = adapter.create_refund_for_invoice(invoice_id=invoice_id)
    db.session.add(
        BillingAdminEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action='refund',
            detail_json={'invoice_id': invoice_id, **result},
            created_at=_utcnow(),
        )
    )
    db.session.commit()
    return {'ok': True, **result, 'invoice_id': invoice_id}


def admin_disputes(organization_id: int) -> dict[str, Any]:
    row = get_org_billing(organization_id)
    if row is None:
        raise LookupError('billing not found')
    adapter = get_stripe_adapter()
    disputes: list[dict[str, Any]] = []
    if row.stripe_customer_id and not str(row.stripe_customer_id).startswith('mock_'):
        disputes = adapter.list_disputes(customer_id=row.stripe_customer_id)
    return {
        'organization_id': organization_id,
        'has_open_dispute': row.has_open_dispute,
        'dispute_opened_at': row.dispute_opened_at.isoformat() if row.dispute_opened_at else None,
        'disputes': disputes,
        'mock': adapter.mock,
    }
