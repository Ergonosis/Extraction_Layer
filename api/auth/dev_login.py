"""Local-only SSO bypass helpers. Must never run in production."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import current_app

from api.extensions import db
from api.models import Organization, User

DEV_TENANT_ID = "00000000-0000-0000-0000-0000000000de"
DEV_OID = "00000000-0000-0000-0000-0000000000de"
DEV_EMAIL = "dev@localhost"
DEV_NAME = "Local Dev User"
DEV_ORG_NAME = "Local Dev Org"


def is_dev_login_allowed() -> bool:
    if not current_app.config.get("ENABLE_DEV_LOGIN"):
        return False
    env = (current_app.config.get("FLASK_ENV") or "").strip().lower()
    return env != "production"


def upsert_dev_identity() -> tuple[User, Organization]:
    """Create or reuse the fixed local-dev org/user rows."""
    org = Organization.query.filter_by(ms_tenant_id=DEV_TENANT_ID).one_or_none()
    if org is None:
        org = Organization(name=DEV_ORG_NAME, ms_tenant_id=DEV_TENANT_ID)
        db.session.add(org)
        db.session.flush()

    user = User.query.filter_by(organization_id=org.id, ms_oid=DEV_OID).one_or_none()
    if user is None:
        user = User(
            organization_id=org.id,
            email=DEV_EMAIL,
            display_name=DEV_NAME,
            ms_oid=DEV_OID,
            last_login=datetime.now(timezone.utc),
        )
        db.session.add(user)
    else:
        user.last_login = datetime.now(timezone.utc)
        user.email = DEV_EMAIL
        user.display_name = DEV_NAME

    db.session.commit()
    return user, org
