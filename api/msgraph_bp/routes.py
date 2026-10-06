"""MS Graph route stubs. Connect/permissions come in a later issue."""

from flask import jsonify

from api.msgraph_bp import bp


@bp.get("/ping")
def ping():
    """Scaffold placeholder so the blueprint is reachable."""
    return jsonify({"blueprint": "msgraph", "status": "ok"})
