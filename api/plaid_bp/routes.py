"""Plaid Link lifecycle routes (connect / exchange / disconnect / status)."""

from __future__ import annotations

from flask import jsonify, request, session

from api.auth.decorators import login_required
from api.plaid_bp import bp
from api.plaid_bp.service import (
    PlaidServiceError,
    cancel_connect,
    check_status,
    create_link_token,
    disconnect,
    exchange_public_token,
    run_export,
)
from api.rate_limit import (
    mutation_limit,
    plaid_status_limit,
    strict_mutation_limit,
)
from api.validation import ValidationError, reject_unknown_fields, require_object


@bp.get("/ping")
def ping():
    """Scaffold placeholder so the blueprint is reachable."""
    return jsonify({"blueprint": "plaid", "status": "ok"})


def _error_response(exc: PlaidServiceError | ValidationError):
    return jsonify({"error": exc.message}), exc.status_code


@bp.post("/connect")
@mutation_limit
@login_required
def connect():
    """Create a Plaid Link token; set integration status to connecting."""
    body = require_object(request.get_json(silent=True))
    try:
        reject_unknown_fields(body, ())
        payload = create_link_token(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
        )
    except ValidationError as exc:
        return _error_response(exc)
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
    try:
        body = require_object(request.get_json(silent=True))
        reject_unknown_fields(body, ("public_token",))
        payload = exchange_public_token(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
            public_token=body.get("public_token"),
        )
    except ValidationError as exc:
        return _error_response(exc)
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
    body = require_object(request.get_json(silent=True))
    try:
        reject_unknown_fields(body, ())
        payload = disconnect(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
        )
    except ValidationError as exc:
        return _error_response(exc)
    except PlaidServiceError as exc:
        return _error_response(exc)
    return jsonify(payload)


@bp.post("/cancel")
@mutation_limit
@login_required
def cancel_route():
    """Reset abandoned `connecting` status without revoking credentials."""
    body = require_object(request.get_json(silent=True))
    try:
        reject_unknown_fields(body, ())
        payload = cancel_connect(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
        )
    except ValidationError as exc:
        return _error_response(exc)
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


@bp.post("/export")
@mutation_limit
@login_required
def export_route():
    """Pull transactions via legacy fetch_and_store; never returns tokens."""
    try:
        body = require_object(request.get_json(silent=True))
        reject_unknown_fields(
            body,
            ("start_date", "end_date", "window_days", "account_filter"),
        )
        payload = run_export(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
            start_date=body.get("start_date"),
            end_date=body.get("end_date"),
            window_days=body.get("window_days"),
            account_filter=body.get("account_filter"),
        )
    except ValidationError as exc:
        return _error_response(exc)
    except PlaidServiceError as exc:
        return _error_response(exc)
    return jsonify(payload)
