"""Stripe boundary — mock by default; live when STRIPE_ENABLED=true."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.billing.meters import Meter
from src.billing.settings import portal_base_url, stripe_enabled, stripe_meter_event_name, stripe_secret_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MeterEventRecord:
    organization_id: int
    meter: Meter
    quantity: int
    identifier: str


@dataclass(frozen=True)
class CheckoutSessionResult:
    session_id: str
    url: str
    mock: bool


@dataclass(frozen=True)
class PortalSessionResult:
    url: str
    mock: bool


class StripeAdapter(Protocol):
    """Narrow interface billing services use; swap mock ↔ live Stripe."""

    mock: bool

    def ensure_customer(
        self, *, organization_id: int, email: str | None, name: str | None, existing_customer_id: str | None
    ) -> str:
        """Return Stripe customer id (create if needed)."""
        ...

    def report_meter_event(
        self,
        *,
        organization_id: int,
        meter: Meter,
        quantity: int,
        identifier: str,
        stripe_customer_id: str | None = None,
    ) -> str:
        """Send (or pretend to send) a meter event. Returns a provider event id."""
        ...

    def create_checkout_session(
        self, *, organization_id: int, customer_id: str, line_items: list[dict[str, Any]], mode: str
    ) -> CheckoutSessionResult: ...

    def create_portal_session(self, *, customer_id: str) -> PortalSessionResult: ...

    def list_invoices(self, *, customer_id: str, limit: int = 20) -> list[dict[str, Any]]: ...

    def create_refund_for_invoice(self, *, invoice_id: str) -> dict[str, Any]: ...

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> Any: ...

    def resolve_payment_method_id(
        self,
        *,
        payment_method: Any = None,
        setup_intent: Any = None,
        payment_intent: Any = None,
        subscription: Any = None,
    ) -> str | None:
        """Resolve a pm_… id from Checkout / SetupIntent / Subscription payloads."""
        ...

    def get_payment_method_card(self, payment_method_id: str) -> dict[str, Any]:
        """Return brand/last4/exp fields for display."""
        ...

    def set_default_payment_method(
        self, *, customer_id: str, payment_method_id: str, subscription_id: str | None = None
    ) -> None:
        """Set invoice default on Customer and optional Subscription."""
        ...

    def preview_upcoming_invoice(
        self, *, customer_id: str, subscription_id: str | None = None
    ) -> dict[str, Any] | None:
        """Return upcoming invoice estimate including tax, or None if unavailable."""
        ...

    def list_disputes(self, *, customer_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return dispute summaries for a Stripe customer."""
        ...


@dataclass
class MockStripeAdapter:
    """In-memory stand-in: no network, no keys."""

    mock: bool = True
    events: list[MeterEventRecord] = field(default_factory=list)
    default_pm_calls: list[dict[str, str | None]] = field(default_factory=list)
    _seq: int = 0
    # Optional fixtures for resolve/retrieve in tests
    fixture_pms: dict[str, dict[str, Any]] = field(default_factory=dict)
    fixture_setup_intents: dict[str, str] = field(default_factory=dict)
    fixture_payment_intents: dict[str, str] = field(default_factory=dict)
    fixture_subscriptions: dict[str, str] = field(default_factory=dict)

    def ensure_customer(
        self, *, organization_id: int, email: str | None, name: str | None, existing_customer_id: str | None
    ) -> str:
        _ = email, name
        return existing_customer_id or f'mock_cus_{organization_id}'

    def report_meter_event(
        self,
        *,
        organization_id: int,
        meter: Meter,
        quantity: int,
        identifier: str,
        stripe_customer_id: str | None = None,
    ) -> str:
        _ = stripe_customer_id
        for existing in self.events:
            if existing.identifier == identifier:
                return f'mock_evt_dup_{identifier}'

        self._seq += 1
        event_id = f'mock_evt_{self._seq}'
        self.events.append(
            MeterEventRecord(organization_id=organization_id, meter=meter, quantity=quantity, identifier=identifier)
        )
        logger.info(
            'MockStripeAdapter meter_event id=%s org=%s meter=%s qty=%s', event_id, organization_id, meter, quantity
        )
        return event_id

    def create_checkout_session(
        self, *, organization_id: int, customer_id: str, line_items: list[dict[str, Any]], mode: str
    ) -> CheckoutSessionResult:
        _ = line_items, mode, customer_id
        session_id = f'mock_cs_{organization_id}'
        return CheckoutSessionResult(
            session_id=session_id, url=f'https://checkout.stripe.com/mock/setup/{session_id}', mock=True
        )

    def create_portal_session(self, *, customer_id: str) -> PortalSessionResult:
        return PortalSessionResult(url=f'https://billing.stripe.com/mock/portal/{customer_id}', mock=True)

    def list_invoices(self, *, customer_id: str, limit: int = 20) -> list[dict[str, Any]]:
        _ = customer_id, limit
        return []

    def create_refund_for_invoice(self, *, invoice_id: str) -> dict[str, Any]:
        return {'id': f'mock_re_{invoice_id}', 'status': 'succeeded', 'mock': True}

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> Any:
        import json

        _ = sig_header
        data = json.loads(payload.decode('utf-8') or '{}')
        return data

    def resolve_payment_method_id(
        self,
        *,
        payment_method: Any = None,
        setup_intent: Any = None,
        payment_intent: Any = None,
        subscription: Any = None,
    ) -> str | None:
        if isinstance(payment_method, str) and payment_method.startswith('pm_'):
            return payment_method
        if isinstance(payment_method, dict) and payment_method.get('id'):
            return str(payment_method['id'])

        for key, store in (
            (setup_intent, self.fixture_setup_intents),
            (payment_intent, self.fixture_payment_intents),
            (subscription, self.fixture_subscriptions),
        ):
            if isinstance(key, str) and key in store:
                return store[key]
            if isinstance(key, dict):
                pm = key.get('payment_method') or key.get('default_payment_method')
                if isinstance(pm, str) and pm.startswith('pm_'):
                    return pm
                if isinstance(pm, dict) and pm.get('id'):
                    return str(pm['id'])
        return None

    def get_payment_method_card(self, payment_method_id: str) -> dict[str, Any]:
        return dict(self.fixture_pms.get(payment_method_id) or {})

    def set_default_payment_method(
        self, *, customer_id: str, payment_method_id: str, subscription_id: str | None = None
    ) -> None:
        self.default_pm_calls.append(
            {'customer_id': customer_id, 'payment_method_id': payment_method_id, 'subscription_id': subscription_id}
        )
        logger.info(
            'MockStripeAdapter set_default_pm customer=%s pm=%s sub=%s', customer_id, payment_method_id, subscription_id
        )

    def preview_upcoming_invoice(
        self, *, customer_id: str, subscription_id: str | None = None
    ) -> dict[str, Any] | None:
        _ = customer_id, subscription_id
        return None

    def list_disputes(self, *, customer_id: str, limit: int = 20) -> list[dict[str, Any]]:
        _ = customer_id, limit
        return []


@dataclass
class LiveStripeAdapter:
    """Real Stripe API using secret key (test or live keys depending on Dashboard)."""

    mock: bool = False

    def _stripe(self):
        import stripe

        key = stripe_secret_key()
        if not key:
            raise RuntimeError('STRIPE_SECRET_KEY is required when STRIPE_ENABLED=true')
        stripe.api_key = key
        return stripe

    def ensure_customer(
        self, *, organization_id: int, email: str | None, name: str | None, existing_customer_id: str | None
    ) -> str:
        stripe = self._stripe()
        if existing_customer_id and not existing_customer_id.startswith('mock_'):
            return existing_customer_id
        customer = stripe.Customer.create(
            email=email or None, name=name or None, metadata={'organization_id': str(organization_id)}
        )
        return str(customer['id'])

    def report_meter_event(
        self,
        *,
        organization_id: int,
        meter: Meter,
        quantity: int,
        identifier: str,
        stripe_customer_id: str | None = None,
    ) -> str:
        if not stripe_customer_id or stripe_customer_id.startswith('mock_'):
            raise RuntimeError(f'Cannot report Stripe meter event without a real customer for org {organization_id}')
        stripe = self._stripe()
        event_name = stripe_meter_event_name(str(meter))
        event = stripe.billing.MeterEvent.create(
            event_name=event_name,
            payload={'stripe_customer_id': stripe_customer_id, 'value': str(quantity)},
            identifier=identifier,
        )
        # MeterEvent create returns the event; id field may be identifier-based.
        return str(getattr(event, 'identifier', None) or identifier)

    def create_checkout_session(
        self, *, organization_id: int, customer_id: str, line_items: list[dict[str, Any]], mode: str
    ) -> CheckoutSessionResult:
        stripe = self._stripe()
        base = portal_base_url()
        params: dict[str, Any] = {
            'customer': customer_id,
            'mode': mode,
            'success_url': f'{base}/billing?checkout=success',
            'cancel_url': f'{base}/billing?checkout=cancel',
            'client_reference_id': str(organization_id),
            'metadata': {'organization_id': str(organization_id)},
            'automatic_tax': {'enabled': True},
            'customer_update': {'address': 'auto', 'name': 'auto'},
            'tax_id_collection': {'enabled': True},
        }
        if mode == 'setup':
            params['payment_method_types'] = ['card']
        else:
            params['line_items'] = line_items
            params['payment_method_types'] = ['card']
        session = stripe.checkout.Session.create(**params)
        url = session.get('url') if isinstance(session, dict) else session.url
        sid = session.get('id') if isinstance(session, dict) else session.id
        if not url:
            raise RuntimeError('Stripe Checkout Session missing url')
        return CheckoutSessionResult(session_id=str(sid), url=str(url), mock=False)

    def create_portal_session(self, *, customer_id: str) -> PortalSessionResult:
        stripe = self._stripe()
        base = portal_base_url()
        portal = stripe.billing_portal.Session.create(customer=customer_id, return_url=f'{base}/billing')
        url = portal.get('url') if isinstance(portal, dict) else portal.url
        return PortalSessionResult(url=str(url), mock=False)

    def list_invoices(self, *, customer_id: str, limit: int = 20) -> list[dict[str, Any]]:
        stripe = self._stripe()
        invoices = stripe.Invoice.list(customer=customer_id, limit=limit)
        data = invoices.get('data') if isinstance(invoices, dict) else invoices.data
        out: list[dict[str, Any]] = []
        for inv in data or []:
            out.append(
                {
                    'id': inv.get('id') if isinstance(inv, dict) else inv.id,
                    'status': inv.get('status') if isinstance(inv, dict) else inv.status,
                    'total': inv.get('total') if isinstance(inv, dict) else inv.total,
                    'currency': inv.get('currency') if isinstance(inv, dict) else inv.currency,
                    'hosted_invoice_url': (
                        inv.get('hosted_invoice_url')
                        if isinstance(inv, dict)
                        else getattr(inv, 'hosted_invoice_url', None)
                    ),
                    'tax': inv.get('tax') if isinstance(inv, dict) else getattr(inv, 'tax', None),
                }
            )
        return out

    def create_refund_for_invoice(self, *, invoice_id: str) -> dict[str, Any]:
        stripe = self._stripe()
        invoice = stripe.Invoice.retrieve(invoice_id, expand=['payment_intent', 'charge'])
        charge_id = None
        if isinstance(invoice, dict):
            charge_id = invoice.get('charge')
            pi = invoice.get('payment_intent')
        else:
            charge_id = invoice.charge
            pi = invoice.payment_intent
        if not charge_id and pi:
            if isinstance(pi, str):
                pi_obj = stripe.PaymentIntent.retrieve(pi)
                charge_id = pi_obj.get('latest_charge') if isinstance(pi_obj, dict) else pi_obj.latest_charge
            else:
                charge_id = pi.get('latest_charge') if isinstance(pi, dict) else getattr(pi, 'latest_charge', None)
        if not charge_id:
            raise RuntimeError(f'No charge found for invoice {invoice_id}')
        refund = stripe.Refund.create(charge=charge_id)
        rid = refund.get('id') if isinstance(refund, dict) else refund.id
        status = refund.get('status') if isinstance(refund, dict) else refund.status
        return {'id': str(rid), 'status': str(status), 'mock': False}

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> Any:
        from src.billing.settings import stripe_webhook_secret

        stripe = self._stripe()
        secret = stripe_webhook_secret()
        if not secret:
            raise RuntimeError('STRIPE_WEBHOOK_SECRET is required when STRIPE_ENABLED=true')
        return stripe.Webhook.construct_event(payload, sig_header, secret)

    def resolve_payment_method_id(
        self,
        *,
        payment_method: Any = None,
        setup_intent: Any = None,
        payment_intent: Any = None,
        subscription: Any = None,
    ) -> str | None:
        stripe = self._stripe()

        def _as_pm_id(value: Any) -> str | None:
            if isinstance(value, str) and value.startswith('pm_'):
                return value
            if isinstance(value, dict) and value.get('id'):
                return str(value['id'])
            if value is not None and hasattr(value, 'id'):
                vid = getattr(value, 'id', None)
                if isinstance(vid, str) and vid.startswith('pm_'):
                    return vid
            return None

        direct = _as_pm_id(payment_method)
        if direct:
            return direct

        if setup_intent:
            si = setup_intent
            if isinstance(setup_intent, str):
                si = stripe.SetupIntent.retrieve(setup_intent)
            pm = si.get('payment_method') if isinstance(si, dict) else getattr(si, 'payment_method', None)
            found = _as_pm_id(pm)
            if found:
                return found

        if payment_intent:
            pi = payment_intent
            if isinstance(payment_intent, str):
                pi = stripe.PaymentIntent.retrieve(payment_intent)
            pm = pi.get('payment_method') if isinstance(pi, dict) else getattr(pi, 'payment_method', None)
            found = _as_pm_id(pm)
            if found:
                return found

        if subscription:
            sub = subscription
            if isinstance(subscription, str):
                sub = stripe.Subscription.retrieve(subscription)
            pm = (
                sub.get('default_payment_method')
                if isinstance(sub, dict)
                else getattr(sub, 'default_payment_method', None)
            )
            found = _as_pm_id(pm)
            if found:
                return found

        return None

    def get_payment_method_card(self, payment_method_id: str) -> dict[str, Any]:
        stripe = self._stripe()
        pm = stripe.PaymentMethod.retrieve(payment_method_id)
        card = pm.get('card') if isinstance(pm, dict) else getattr(pm, 'card', None) or {}
        if not isinstance(card, dict):
            card = {
                'brand': getattr(card, 'brand', None),
                'last4': getattr(card, 'last4', None),
                'exp_month': getattr(card, 'exp_month', None),
                'exp_year': getattr(card, 'exp_year', None),
            }
        return {
            'brand': card.get('brand'),
            'last4': card.get('last4'),
            'exp_month': card.get('exp_month'),
            'exp_year': card.get('exp_year'),
        }

    def set_default_payment_method(
        self, *, customer_id: str, payment_method_id: str, subscription_id: str | None = None
    ) -> None:
        stripe = self._stripe()
        stripe.Customer.modify(customer_id, invoice_settings={'default_payment_method': payment_method_id})
        if subscription_id and not str(subscription_id).startswith('mock_'):
            stripe.Subscription.modify(subscription_id, default_payment_method=payment_method_id)

    def preview_upcoming_invoice(
        self, *, customer_id: str, subscription_id: str | None = None
    ) -> dict[str, Any] | None:
        stripe = self._stripe()
        params: dict[str, Any] = {'customer': customer_id, 'automatic_tax': {'enabled': True}}
        if subscription_id and not str(subscription_id).startswith('mock_'):
            params['subscription'] = subscription_id
        try:
            # Prefer Invoice.create_preview (current API); fall back to upcoming.
            if hasattr(stripe.Invoice, 'create_preview'):
                inv = stripe.Invoice.create_preview(**params)
            else:
                inv = stripe.Invoice.upcoming(**params)
        except Exception as exc:
            logger.warning('Stripe upcoming invoice preview failed: %s', exc)
            return None

        def g(obj: Any, key: str, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        currency = g(inv, 'currency') or 'usd'
        subtotal = g(inv, 'subtotal')
        total = g(inv, 'total')
        tax = g(inv, 'tax')
        if tax is None:
            # Sum tax amounts when present on modern invoice objects.
            total_taxes = g(inv, 'total_taxes') or []
            if total_taxes:
                tax = sum(int(g(t, 'amount') or 0) for t in total_taxes)
            else:
                amounts = g(inv, 'total_tax_amounts') or []
                tax = sum(int(g(t, 'amount') or 0) for t in amounts) if amounts else None

        lines_out: list[dict[str, Any]] = []
        lines = g(inv, 'lines') or {}
        line_data = g(lines, 'data') if not isinstance(lines, list) else lines
        for line in line_data or []:
            lines_out.append(
                {'description': g(line, 'description'), 'amount': g(line, 'amount'), 'quantity': g(line, 'quantity')}
            )

        return {
            'currency': currency,
            'subtotal': subtotal,
            'tax': tax,
            'total': total,
            'lines': lines_out,
            'note': None,
        }

    def list_disputes(self, *, customer_id: str, limit: int = 20) -> list[dict[str, Any]]:
        stripe = self._stripe()

        def g(obj: Any, key: str, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # Dispute.list has no customer filter; expand charge and filter client-side.
        try:
            page = stripe.Dispute.list(limit=min(max(limit, 1), 100), expand=['data.charge'])
        except Exception as exc:
            logger.warning('Stripe Dispute.list failed: %s', exc)
            return []

        data = g(page, 'data') or []
        out: list[dict[str, Any]] = []
        for disp in data:
            charge = g(disp, 'charge')
            charge_customer = None
            charge_id = None
            if isinstance(charge, str):
                charge_id = charge
                try:
                    ch = stripe.Charge.retrieve(charge)
                    charge_customer = g(ch, 'customer')
                except Exception:
                    charge_customer = None
            elif charge is not None:
                charge_id = g(charge, 'id')
                charge_customer = g(charge, 'customer')

            if str(charge_customer or '') != str(customer_id):
                continue

            disp_id = str(g(disp, 'id') or '')
            created = g(disp, 'created')
            evidence_details = g(disp, 'evidence_details') or {}
            due_by = (
                g(evidence_details, 'due_by')
                if isinstance(evidence_details, dict)
                else getattr(evidence_details, 'due_by', None)
            )
            out.append(
                {
                    'id': disp_id,
                    'amount': g(disp, 'amount'),
                    'currency': g(disp, 'currency'),
                    'reason': g(disp, 'reason'),
                    'status': g(disp, 'status'),
                    'created': created,
                    'evidence_due_by': due_by,
                    'charge_id': charge_id,
                    'dashboard_url': f'https://dashboard.stripe.com/disputes/{disp_id}' if disp_id else None,
                }
            )
            if len(out) >= limit:
                break
        return out


_adapter: StripeAdapter | None = None


def build_stripe_adapter() -> StripeAdapter:
    if stripe_enabled():
        logger.info('Stripe adapter: LIVE (STRIPE_ENABLED=true)')
        return LiveStripeAdapter()
    logger.info('Stripe adapter: MOCK (STRIPE_ENABLED=false)')
    return MockStripeAdapter()


def get_stripe_adapter() -> StripeAdapter:
    """Return the process-wide adapter (mock unless STRIPE_ENABLED)."""
    global _adapter
    if _adapter is None:
        _adapter = build_stripe_adapter()
    return _adapter


def set_stripe_adapter(adapter: StripeAdapter | None) -> None:
    """Tests/bootstrap may inject a fresh mock or live adapter."""
    global _adapter
    _adapter = adapter


def reset_stripe_adapter() -> MockStripeAdapter:
    """Replace with a clean mock (useful in tests)."""
    mock = MockStripeAdapter()
    set_stripe_adapter(mock)
    return mock


def reload_stripe_adapter() -> StripeAdapter:
    """Rebuild from current env (after toggling STRIPE_ENABLED in tests)."""
    adapter = build_stripe_adapter()
    set_stripe_adapter(adapter)
    return adapter
