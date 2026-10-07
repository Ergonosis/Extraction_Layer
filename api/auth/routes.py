"""Auth route stubs. Full SSO implementation comes in a later issue."""

from flask import jsonify, session

from api.auth import bp
from api.middleware import ensure_csrf_token
from api.rate_limit import mutation_limit


@bp.get("/ping")
def ping():
    """Scaffold placeholder so the blueprint is reachable."""
    return jsonify({"blueprint": "auth", "status": "ok"})


@bp.get("/csrf-token")
def csrf_token():
    """Issue (or return) the CSRF token for the SPA double-submit header."""
    session.permanent = True
    token = ensure_csrf_token()
    return jsonify({"csrf_token": token})


@bp.post("/ping")
@mutation_limit
def ping_mutation():
    """Mutation stub for CSRF / rate-limit checks (SSO routes come later)."""
    return jsonify({"blueprint": "auth", "status": "ok", "method": "POST"})
