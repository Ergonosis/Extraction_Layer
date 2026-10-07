"""Security headers and CSRF double-submit validation."""

from __future__ import annotations

import secrets

from flask import Flask, jsonify, request, session

MUTATING_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

# Paths that skip CSRF (keep empty of mutations that change state).
CSRF_EXEMPT_PATHS = frozenset()


def ensure_csrf_token() -> str:
    """Return the session CSRF token, creating one if missing."""
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
        session.permanent = True
    return token


def register_security_middleware(app: Flask) -> None:
    """Attach CSRF checks and security response headers."""

    @app.before_request
    def _csrf_protect():
        if request.method not in MUTATING_METHODS:
            return None
        if request.path in CSRF_EXEMPT_PATHS:
            return None

        expected = session.get("csrf_token")
        provided = request.headers.get("X-CSRF-Token", "")
        if not expected or not provided or not secrets.compare_digest(expected, provided):
            return jsonify({"error": "CSRF validation failed"}), 403
        return None

    @app.after_request
    def _security_headers(response):
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
