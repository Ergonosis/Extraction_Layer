"""MS Graph delegated lifecycle routes (connect / callback / disconnect / status)."""

from __future__ import annotations

from flask import jsonify, redirect, request, session

from api.auth.decorators import login_required
from api.msgraph_bp import bp
from api.msgraph_bp.service import (
    MsGraphServiceError,
    cancel_connect,
    check_status,
    complete_callback,
    disconnect,
    list_available_permissions,
    portal_post_connect_url,
    start_connect,
    update_permissions,
)
from api.rate_limit import (
    auth_callback_limit,
    auth_me_limit,
    msgraph_status_limit,
    mutation_limit,
    strict_mutation_limit,
)


@bp.get("/ping")
def ping():
    """Scaffold placeholder so the blueprint is reachable."""
    return jsonify({"blueprint": "msgraph", "status": "ok"})


def _error_response(exc: MsGraphServiceError):
    return jsonify({"error": exc.message}), exc.status_code


@bp.post("/connect")
@mutation_limit
@login_required
def connect():
    """Start Graph consent; validate scopes against allowlist; return authorize_url."""
    body = request.get_json(silent=True) or {}
    try:
        payload = start_connect(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
            requested_scopes=body.get("scopes"),
        )
    except MsGraphServiceError as exc:
        return _error_response(exc)
    return jsonify(payload)


@bp.get("/callback")
@auth_callback_limit
@login_required
def callback():
    """Handle Microsoft redirect: exchange code, store encrypted tokens."""
    error = request.args.get("error")
    if error:
        detail = request.args.get("error_description") or error
        try:
            cancel_connect(
                user_id=session["user_id"],
                organization_id=session["organization_id"],
            )
        except MsGraphServiceError:
            pass
        return redirect(f"{portal_post_connect_url()}?msgraph_error=1", code=302)

    code = request.args.get("code") or ""
    state = request.args.get("state") or ""
    try:
        complete_callback(code=code, state=state)
    except MsGraphServiceError as exc:
        if exc.status_code == 401:
            return jsonify({"error": exc.message}), exc.status_code
        return redirect(f"{portal_post_connect_url()}?msgraph_error=1", code=302)

    return redirect(portal_post_connect_url(), code=302)


@bp.post("/disconnect")
@strict_mutation_limit
@login_required
def disconnect_route():
    """Delete Graph credentials without decrypting; clear permissions."""
    try:
        payload = disconnect(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
        )
    except MsGraphServiceError as exc:
        return _error_response(exc)
    return jsonify(payload)


@bp.post("/cancel")
@mutation_limit
@login_required
def cancel_route():
    """Reset abandoned connecting status."""
    try:
        payload = cancel_connect(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
        )
    except MsGraphServiceError as exc:
        return _error_response(exc)
    return jsonify(payload)


@bp.get("/status")
@msgraph_status_limit
@login_required
def status():
    """Refresh tokens; never returns plaintext tokens."""
    try:
        payload = check_status(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
        )
    except MsGraphServiceError as exc:
        return _error_response(exc)
    return jsonify(payload)


@bp.get("/permissions/available")
@auth_me_limit
@login_required
def permissions_available():
    """Allowlist permissions with labels and current is_active flags."""
    try:
        payload = list_available_permissions(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
        )
    except MsGraphServiceError as exc:
        return _error_response(exc)
    return jsonify(payload)


@bp.put("/permissions")
@mutation_limit
@login_required
def permissions_update():
    """Toggle active scopes or return incremental consent redirect_url."""
    body = request.get_json(silent=True) or {}
    try:
        payload = update_permissions(
            user_id=session["user_id"],
            organization_id=session["organization_id"],
            requested_scopes=body.get("scopes"),
        )
    except MsGraphServiceError as exc:
        return _error_response(exc)
    return jsonify(payload)
