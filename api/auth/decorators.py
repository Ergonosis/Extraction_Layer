"""Auth decorators for protected portal routes."""

from __future__ import annotations

from functools import wraps

from flask import jsonify, session

from api.auth.session_utils import destroy_session
from api.extensions import db
from api.models import User


def login_required(view):
    """Require session user_id + organization_id that match a real user row."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        organization_id = session.get("organization_id")
        if not user_id or not organization_id:
            return jsonify({"error": "Authentication required"}), 401

        user = db.session.get(User, user_id)
        if user is None or user.organization_id != organization_id:
            destroy_session()
            return jsonify({"error": "Authentication required"}), 401

        return view(*args, **kwargs)

    return wrapped
