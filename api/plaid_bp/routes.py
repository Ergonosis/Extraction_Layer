"""Plaid Link lifecycle routes (connect / exchange / disconnect / status)."""

from __future__ import annotations

from flask import jsonify, request, session

from api.auth.decorators import login_required
from api.plaid_bp import bp
from api.plaid_bp.service import (
    PlaidServiceError,
    check_status,
    create_link_token,
    disconnect,
    exchange_public_token,
)
from api.rate_limit import (
    mutation_limit,
    plaid_status_limit,
    strict_mutation_limit,
)


@bp.get("/ping")
def ping():
    """Scaffold placeholder so the blueprint is reachable."""
    return jsonify({"blueprint": "plaid", "status": "ok"})


def _error_response(exc: PlaidServiceError):
    return jsonify({"error": exc.message}), exc.status_code


@bp.post("/connect")
@mutation_limit
@login_required
def connect():
    """Create a Plaid Link token; set integration status to connecting."""
    try:
        payload = create_link_token(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
        )
    except PlaidServiceError as exc:
        return _error_response(exc)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    return jsonify(payload)


@bp.post("/exchange")
@strict_mutation_limit
@login_required
def exchange():
    """Exchange public_token for access_token; store Fernet ciphertext only."""
    body = request.get_json(silent=True) or {}
    try:
        payload = exchange_public_token(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
            public_token=body.get("public_token"),
        )
    except PlaidServiceError as exc:
        return _error_response(exc)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    return jsonify(payload)


@bp.post("/disconnect")
@strict_mutation_limit
@login_required
def disconnect_route():
    """Revoke Item at Plaid and delete local encrypted credentials."""
    try:
        payload = disconnect(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
        )
    except PlaidServiceError as exc:
        return _error_response(exc)
    return jsonify(payload)


@bp.get("/status")
@plaid_status_limit
@login_required
def status():
    """Check Item health; never returns tokens."""
    try:
        payload = check_status(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
        )
    except PlaidServiceError as exc:
        return _error_response(exc)
    return jsonify(payload)
