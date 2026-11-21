"""Resolve who should receive billing emails for an org."""

from __future__ import annotations

from src.api.extensions import db
from src.api.models import User
from src.billing.admins import bootstrap_admin_emails
from src.billing.models import PlatformAdmin
from src.billing.settings import platform_admin_notify_emails


def org_billing_emails(organization_id: int) -> list[str]:
    """v1: all users in the org (deduped, lowercased for uniqueness, original casing kept)."""
    users = (
        db.session.execute(
            db.select(User).where(User.organization_id == organization_id).order_by(User.created_at.asc())
        )
        .scalars()
        .all()
    )
    seen: set[str] = set()
    out: list[str] = []
    for user in users:
        email = (user.email or '').strip()
        key = email.lower()
        if not email or key in seen:
            continue
        seen.add(key)
        out.append(email)
    return out


def platform_admin_emails() -> list[str]:
    """Combine env bootstrap + platform_admins table emails."""
    seen: set[str] = set()
    out: list[str] = []
    for email in platform_admin_notify_emails() + list(bootstrap_admin_emails()):
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(email)
    rows = db.session.execute(db.select(PlatformAdmin)).scalars().all()
    for row in rows:
        email = (row.email or '').strip()
        key = email.lower()
        if not email or key in seen:
            continue
        seen.add(key)
        out.append(email)
    return out
