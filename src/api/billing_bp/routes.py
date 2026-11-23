"""Customer-facing billing routes + Stripe webhook + dunning job."""

from __future__ import annotations

import logging
import os

from flask import jsonify, request, session

from src.api.auth.decorators import login_required
from src.api.billing_bp import bp
from src.api.rate_limit import auth_me_limit
from src.billing import services
from src.billing.dunning import run_dunning_pass
from src.billing.meter_retry import run_meter_retry_pass
from src.billing.settings import stripe_enabled
from src.billing.stripe_adapter import get_stripe_adapter
from src.billing.webhooks import process_stripe_event

logger = logging.getLogger(__name__)


@bp.get('/summary')
@auth_me_limit
@login_required
def get_summary():
    data = services.customer_summary(session['organization_id'])
    return jsonify(data)


@bp.get('/usage')
@auth_me_limit
@login_required
def get_usage():
    return jsonify({'organization_id': session['organization_id'], **services.usage_totals(session['organization_id'])})


@bp.get('/invoices')
@auth_me_limit
@login_required
def get_invoices():
    return jsonify(services.list_invoices(session['organization_id']))


@bp.post('/setup-session')
@auth_me_limit
@login_required
def post_setup_session():
    try:
        data = services.create_setup_session(session['organization_id'], actor_user_id=session.get('user_id'))
    except Exception as exc:
        logger.exception('setup-session failed')
        return jsonify({'error': 'Bad request', 'detail': str(exc)}), 400
    return jsonify(data)


@bp.post('/portal-session')
@auth_me_limit
@login_required
def post_portal_session():
    try:
        data = services.create_portal_session(session['organization_id'])
    except ValueError as exc:
        return jsonify({'error': 'Bad request', 'detail': str(exc)}), 400
    except Exception as exc:
        logger.exception('portal-session failed')
        return jsonify({'error': 'Bad request', 'detail': str(exc)}), 400
    return jsonify(data)


@bp.post('/webhook')
def stripe_webhook():
    """Verify Stripe signature when enabled; accept mock JSON when disabled."""
    payload = request.get_data()
    sig = request.headers.get('Stripe-Signature', '')
    adapter = get_stripe_adapter()

    try:
        if stripe_enabled() and not adapter.mock:
            event = adapter.construct_webhook_event(payload, sig)
        else:
            # Local/dev: unsigned JSON body (or empty) for fixture testing.
            event = adapter.construct_webhook_event(payload or b'{}', sig or 'mock')
    except Exception as exc:
        logger.warning('Stripe webhook verify failed: %s', exc)
        return jsonify({'error': 'Invalid payload'}), 400

    try:
        result = process_stripe_event(event)
    except Exception:
        logger.exception('Stripe webhook handler failed')
        return jsonify({'error': 'Webhook handler error'}), 500
    return jsonify({'received': True, **result}), 200


def _require_job_secret():
    expected = (os.getenv('BILLING_JOB_SECRET') or '').strip()
    provided = (request.headers.get('X-Billing-Job-Secret') or '').strip()
    if not expected or provided != expected:
        return jsonify({'error': 'Unauthorized'}), 401
    return None


@bp.post('/jobs/dunning')
def dunning_job():
    """Daily entitlement/reminder job (scheduler secret). Stripe owns charging."""
    denied = _require_job_secret()
    if denied is not None:
        return denied
    result = run_dunning_pass()
    return jsonify({'ok': True, **result, 'stripe_enabled': stripe_enabled()})


@bp.post('/jobs/meter-retry')
def meter_retry_job():
    """Retry pending/failed Stripe meter events from the usage ledger outbox."""
    denied = _require_job_secret()
    if denied is not None:
        return denied
    limit = 50
    body = request.get_json(silent=True) or {}
    if 'limit' in body:
        try:
            limit = max(1, min(200, int(body['limit'])))
        except (TypeError, ValueError):  # fmt: skip
            return jsonify({'error': 'Bad request', 'detail': 'limit must be an integer'}), 400
    result = run_meter_retry_pass(limit=limit)
    return jsonify({'ok': True, **result, 'stripe_enabled': stripe_enabled()})
