"""Billing application services (DB + Stripe adapter; no HTTP)."""

from __future__ import annotations

import logging
from typing import Any

from src.api.extensions import db
from src.api.models import Organization, User
from src.billing.models import BillingAdminEvent, OrganizationBilling, _utcnow
from src.billing.settings import stripe_enabled, stripe_publishable_key
from src.billing.stripe_adapter import get_stripe_adapter

logger = logging.getLogger(__name__)


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


def _plan_amounts_cents(row: OrganizationBilling) -> dict[str, int | None]:
    raw = row.terms_json if isinstance(row.terms_json, dict) else {}
    amounts = raw.get('amounts_cents') if isinstance(raw.get('amounts_cents'), dict) else {}
    out: dict[str, int | None] = {'flat': None, 'exports': None, 'api_calls': None}
    for key in out:
        val = amounts.get(key)
        if val is None or val == '':
            continue
        try:
            out[key] = int(val)
        except TypeError, ValueError:
            out[key] = None
    return out


def _usd_to_cents(raw: Any, *, field: str) -> int | None:
    """Parse a dollar amount from admin UI into integer cents."""
    if raw is None or raw == '':
        return None
    try:
        # Avoid float drift: round half-up via Decimal-ish string path.
        text = str(raw).strip().replace('$', '').replace(',', '')
        if not text:
            return None
        negative = text.startswith('-')
        if negative:
            text = text[1:]
        if '.' in text:
            dollars, frac = text.split('.', 1)
            frac = (frac + '00')[:2]
            cents = int(dollars or '0') * 100 + int(frac)
        else:
            cents = int(text) * 100
        if negative:
            cents = -cents
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field} must be a dollar amount like 100 or 2.50') from exc
    if cents < 0:
        raise ValueError(f'{field} must be >= 0')
    return cents


def _cents_to_usd_str(cents: int | None) -> str:
    if cents is None:
        return ''
    return f'{cents / 100:.2f}'


def _billing_public_dict(row: OrganizationBilling) -> dict[str, Any]:
    amounts = _plan_amounts_cents(row)
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
        'flat_amount_usd': _cents_to_usd_str(amounts['flat']),
        'exports_unit_amount_usd': _cents_to_usd_str(amounts['exports']),
        'api_calls_unit_amount_usd': _cents_to_usd_str(amounts['api_calls']),
    }


def _is_mock() -> bool:
    return bool(getattr(get_stripe_adapter(), 'mock', True)) or not stripe_enabled()


def _upcoming_invoice_payload(row: OrganizationBilling | None, *, mock: bool) -> dict[str, Any]:
    if mock or row is None or not row.stripe_customer_id or str(row.stripe_customer_id).startswith('mock_'):
        note = (
            'Billing is in mock mode. No live charges or tax.'
            if mock
            else 'No Stripe customer yet. Complete Checkout to enable invoice previews.'
        )
        return {'currency': 'usd', 'subtotal': None, 'tax': None, 'total': None, 'lines': [], 'note': note}
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
    # Local card/status are webhook-driven; heal when Checkout completed but listen missed.
    needs_pm_sync = not row.pm_last4 or not row.default_payment_method_id
    needs_status_heal = row.status == 'setup_required' and bool(row.pm_last4 or row.default_payment_method_id)
    if needs_pm_sync or needs_status_heal:
        from src.billing.payment_methods import sync_payment_method_from_stripe

        try:
            if sync_payment_method_from_stripe(row) or needs_status_heal:
                if row.status == 'setup_required' and (row.pm_last4 or row.default_payment_method_id):
                    row.status = 'active'
                    row.entitlement = 'enabled'
                db.session.commit()
        except Exception:
            logger.exception('customer_summary PM sync failed org=%s', organization_id)
            db.session.rollback()
            row = get_org_billing(organization_id) or row
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
    customer_id = row.stripe_customer_id if row else None
    if not customer_id or str(customer_id).startswith('mock_'):
        return {'invoices': [], 'mock': adapter.mock}
    try:
        invoices = adapter.list_invoices(customer_id=str(customer_id))
    except Exception:
        logger.exception('list_invoices failed org=%s customer=%s', organization_id, customer_id)
        return {'invoices': [], 'mock': adapter.mock, 'error': 'Could not load invoices from Stripe.'}
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
    customer_id = row.stripe_customer_id if row else None
    if not customer_id or str(customer_id).startswith('mock_'):
        raise ValueError('billing not set up for organization')
    adapter = get_stripe_adapter()
    result = adapter.create_portal_session(customer_id=str(customer_id))
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

    prev_amounts = _plan_amounts_cents(row)
    next_amounts = dict(prev_amounts)
    amount_keys = (
        ('flat_amount_usd', 'flat', 'Flat monthly fee'),
        ('exports_unit_amount_usd', 'exports', 'Exports unit price'),
        ('api_calls_unit_amount_usd', 'api_calls', 'API calls unit price'),
    )
    for payload_key, amount_key, label in amount_keys:
        if payload_key in payload:
            next_amounts[amount_key] = _usd_to_cents(payload[payload_key], field=label)

    adapter = get_stripe_adapter()
    org_name = org.name or f'Organization {organization_id}'

    def _sync_price(*, kind: str, enabled: bool, existing_price_id: str | None) -> str | None:
        cents = next_amounts.get(kind)
        if not enabled:
            return existing_price_id
        if cents is None:
            raise ValueError(f'Set a USD amount for {kind.replace("_", " ")} before enabling it')
        return adapter.ensure_plan_price(
            organization_id=organization_id,
            org_name=org_name,
            kind=kind,
            unit_amount_cents=int(cents),
            existing_price_id=existing_price_id,
            previous_unit_amount_cents=prev_amounts.get(kind),
        )

    row.stripe_flat_price_id = _sync_price(
        kind='flat', enabled=row.flat_enabled, existing_price_id=row.stripe_flat_price_id
    )
    row.stripe_exports_price_id = _sync_price(
        kind='exports', enabled=row.exports_enabled, existing_price_id=row.stripe_exports_price_id
    )
    row.stripe_api_calls_price_id = _sync_price(
        kind='api_calls', enabled=row.api_calls_enabled, existing_price_id=row.stripe_api_calls_price_id
    )

    terms = dict(row.terms_json) if isinstance(row.terms_json, dict) else {}
    terms['amounts_cents'] = {k: v for k, v in next_amounts.items() if v is not None}
    row.terms_json = terms

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
