"""Integrations route stubs. Dashboard endpoints come in a later issue."""

from flask import jsonify

from api.integrations import bp


@bp.get("/ping")
def ping():
    """Scaffold placeholder so the blueprint is reachable."""
    return jsonify({"blueprint": "integrations", "status": "ok"})
