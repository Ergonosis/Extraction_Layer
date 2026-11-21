"""Billing bounded context — usage reporting and org entitlement.

Feature modules (Plaid, Graph, API middleware) should import only from this
package surface. They must not talk to Stripe or billing tables directly.
"""

from __future__ import annotations

from src.billing.admins import is_platform_admin, user_is_platform_admin
from src.billing.decorators import platform_admin_required
from src.billing.entitlement import EntitlementError, assert_org_entitled
from src.billing.meters import Meter
from src.billing.usage import report_usage

__all__ = [
    'EntitlementError',
    'Meter',
    'assert_org_entitled',
    'is_platform_admin',
    'platform_admin_required',
    'report_usage',
    'user_is_platform_admin',
]
