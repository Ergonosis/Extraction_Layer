"""Shared-schema multi-organization helpers (issue #30)."""

from __future__ import annotations

from api.extensions import db
from api.models import User


class TenancyError(Exception):
    """Caller passed a user_id that does not belong to organization_id."""

    def __init__(self, detail: str = "Organization mismatch"):
        super().__init__(detail)
        self.detail = detail


def require_matching_org(*, user_id: int, organization_id: int) -> User:
    """Return the user only if they belong to the given organization.

    Defense in depth for service entrypoints: HTTP routes already enforce this
    via ``login_required``, but services must not trust mismatched ids.
    """
    user = db.session.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        raise TenancyError(
            "User does not belong to the requested organization",
        )
    return user
