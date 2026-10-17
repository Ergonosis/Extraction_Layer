"""Integrations dashboard routes."""

from __future__ import annotations

from flask import jsonify, session

from api.auth.decorators import login_required
from api.integrations import bp
from api.integrations.service import list_integrations
from api.rate_limit import auth_me_limit


@bp.get("/ping")
def ping():
    """Scaffold placeholder so the blueprint is reachable."""
    return jsonify({"blueprint": "integrations", "status": "ok"})


@bp.get("/")
@auth_me_limit
@login_required
def get_integrations():
    """Return Plaid + MS Graph status for the current user/org (no tokens)."""
    integrations = list_integrations(
        user_id=session["user_id"],
        organization_id=session["organization_id"],
    )
    return jsonify({"integrations": integrations})
