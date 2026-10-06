"""Auth route stubs. Full SSO implementation comes in a later issue."""

from flask import jsonify

from api.auth import bp


@bp.get("/ping")
def ping():
    """Scaffold placeholder so the blueprint is reachable."""
    return jsonify({"blueprint": "auth", "status": "ok"})
