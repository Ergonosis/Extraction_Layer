"""Portal access gate based on billing health."""

from __future__ import annotations

from src.api.extensions import db
from src.billing.models import OrganizationBilling


class EntitlementError(Exception):
    """Raised when an org is not allowed to use paid Portal features."""

    def __init__(self, organization_id: int, reason: str = 'suspended') -> None:
        self.organization_id = organization_id
        self.reason = reason
        super().__init__(f'organization {organization_id} entitlement: {reason}')


def assert_org_entitled(organization_id: int) -> None:
    """Raise EntitlementError if the org must not use paid actions.

    No billing row yet → treated as entitled (setup not finished).
    Row with entitlement=suspended → blocked.
    """
    if organization_id <= 0:
        raise EntitlementError(organization_id, reason='invalid_organization')

    row = (
        db.session.execute(db.select(OrganizationBilling).where(OrganizationBilling.organization_id == organization_id))
        .scalars()
        .one_or_none()
    )
    if row is None:
        return
    if row.entitlement == 'suspended':
        raise EntitlementError(organization_id, reason='suspended')
    return
