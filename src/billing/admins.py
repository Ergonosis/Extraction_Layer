"""Platform admin allowlist — Ergonosis staff for Admin Billing."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.api.extensions import db
from src.billing.models import PlatformAdmin

if TYPE_CHECKING:
    from src.api.models import User


def _split_csv(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(',') if part.strip()}


def bootstrap_admin_emails() -> set[str]:
    """Emails from PLATFORM_ADMIN_EMAILS (comma-separated) for first-time bootstrap."""
    return _split_csv(os.getenv('PLATFORM_ADMIN_EMAILS'))


def bootstrap_admin_oids() -> set[str]:
    """Entra oids from PLATFORM_ADMIN_MS_OIDS (comma-separated)."""
    # OIDs are case-insensitive GUIDs; normalize to lower for comparison.
    return _split_csv(os.getenv('PLATFORM_ADMIN_MS_OIDS'))


def is_platform_admin(*, ms_oid: str | None = None, email: str | None = None) -> bool:
    """True if oid/email matches env bootstrap list or platform_admins table."""
    oid = (ms_oid or '').strip().lower()
    mail = (email or '').strip().lower()

    if oid and oid in bootstrap_admin_oids():
        return True
    if mail and mail in bootstrap_admin_emails():
        return True

    if not oid and not mail:
        return False

    q = db.select(PlatformAdmin)
    row = db.session.execute(q).scalars().all()
    for admin in row:
        if oid and admin.ms_oid and admin.ms_oid.strip().lower() == oid:
            return True
        if mail and admin.email and admin.email.strip().lower() == mail:
            return True
    return False


def user_is_platform_admin(user: User) -> bool:
    """Check a Portal User row against the allowlist."""
    return is_platform_admin(ms_oid=user.ms_oid, email=user.email)
