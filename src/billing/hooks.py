"""Thin hooks for feature modules — usage + entitlement without Stripe details."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from flask import Request, Response, session

from src.api.extensions import db
from src.billing.entitlement import assert_org_entitled
from src.billing.meters import Meter
from src.billing.models import OrganizationBilling
from src.billing.usage import report_usage

logger = logging.getLogger(__name__)

_API_METER_EXACT = frozenset({'/api/health', '/api/ready', '/api/billing/webhook', '/api/billing/jobs/dunning'})


def _meter_enabled(organization_id: int, meter: Meter) -> bool:
    row = (
        db.session.execute(db.select(OrganizationBilling).where(OrganizationBilling.organization_id == organization_id))
        .scalars()
        .one_or_none()
    )
    if row is None:
        return False
    if meter == Meter.EXPORTS:
        return bool(row.exports_enabled)
    if meter == Meter.API_CALLS:
        return bool(row.api_calls_enabled)
    return False


def require_entitled(organization_id: int) -> None:
    """Raise EntitlementError if paid actions must be blocked."""
    assert_org_entitled(organization_id)


def record_export_usage(organization_id: int, *, source: str) -> None:
    """Count one successful export when that meter is enabled for the org."""
    try:
        if not _meter_enabled(organization_id, Meter.EXPORTS):
            return
        day = datetime.now(UTC).strftime('%Y%m%d')
        key = f'{organization_id}:exports:{source}:{day}:{uuid.uuid4().hex}'
        report_usage(organization_id, Meter.EXPORTS, 1, idempotency_key=key)
    except Exception:
        logger.exception('billing.record_export_usage failed org=%s source=%s', organization_id, source)


def maybe_meter_api_request(request: Request, response: Response) -> None:
    """after_request: count authenticated API calls when api_calls meter is on."""
    try:
        path = request.path or ''
        if not path.startswith('/api/'):
            return
        if path in _API_METER_EXACT:
            return
        if path.startswith('/api/billing/webhook'):
            return

        organization_id = session.get('organization_id')
        if not organization_id:
            return

        # Only count completed authenticated traffic; skip unauthenticated noise.
        if response.status_code == 401:
            return

        if not _meter_enabled(int(organization_id), Meter.API_CALLS):
            return

        # Per-request unique key — retries of the same client call may double-count;
        # ledger uniqueness still protects exact replay of the same key.
        key = f'{organization_id}:api_calls:{datetime.now(UTC).strftime("%Y%m%d%H%M")}:{uuid.uuid4().hex}'
        report_usage(int(organization_id), Meter.API_CALLS, 1, idempotency_key=key)
    except Exception:
        logger.exception('billing.maybe_meter_api_request failed path=%s', getattr(request, 'path', ''))
