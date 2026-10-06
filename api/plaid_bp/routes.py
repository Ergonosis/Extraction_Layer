"""Plaid route stubs. Connect/exchange/disconnect come in a later issue."""

from flask import jsonify

from api.plaid_bp import bp


@bp.get("/ping")
def ping():
    """Scaffold placeholder so the blueprint is reachable."""
    return jsonify({"blueprint": "plaid", "status": "ok"})
