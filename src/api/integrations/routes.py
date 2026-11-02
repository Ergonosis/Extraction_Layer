"""Integrations dashboard routes."""

from __future__ import annotations

from flask import jsonify, session

from src.api.auth.decorators import login_required
from src.api.integrations import bp
from src.api.integrations.service import list_integrations
from src.api.rate_limit import auth_me_limit


@bp.get('/ping')
def ping():
    """Scaffold placeholder so the blueprint is reachable."""
    return jsonify({'blueprint': 'integrations', 'status': 'ok'})


@bp.get('/')
@auth_me_limit
@login_required
def get_integrations():
    """Return Plaid + MS Graph status for the current user/org (no tokens)."""
    integrations = list_integrations(user_id=session['user_id'], organization_id=session['organization_id'])
    return jsonify({'integrations': integrations})
