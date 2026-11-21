"""Decorators for billing HTTP routes."""

from __future__ import annotations

from functools import wraps

from flask import jsonify, session

from src.api.auth.session_utils import destroy_session
from src.api.extensions import db
from src.api.models import User
from src.billing.admins import user_is_platform_admin


def platform_admin_required(view):
    """Require a logged-in user who is on the platform admin allowlist.

    Returns 401 if not logged in, 403 if logged in but not an admin.
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = session.get('user_id')
        organization_id = session.get('organization_id')
        if not user_id or not organization_id:
            return jsonify({'error': 'Authentication required'}), 401

        user = db.session.get(User, user_id)
        if user is None or user.organization_id != organization_id:
            destroy_session()
            return jsonify({'error': 'Authentication required'}), 401

        if not user_is_platform_admin(user):
            return jsonify({'error': 'Forbidden', 'detail': 'Platform admin required'}), 403

        return view(*args, **kwargs)

    return wrapped
