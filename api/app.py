"""Flask application factory for the portal API."""

import logging
import os
import sys

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_session import Session
from werkzeug.exceptions import HTTPException

from api.config import Config
from api.extensions import db, migrate
from api.middleware import register_security_middleware
from api.rate_limit import init_limiter

logger = logging.getLogger(__name__)

_DEV_SECRET_DEFAULT = "dev-only-change-me"


def _assert_dev_login_safe(app: Flask) -> None:
    """Refuse to boot if ENABLE_DEV_LOGIN is on in production."""
    enabled = bool(app.config.get("ENABLE_DEV_LOGIN"))
    env = (app.config.get("FLASK_ENV") or "").strip().lower()
    if enabled and env == "production":
        logger.critical(
            "REFUSING TO START: ENABLE_DEV_LOGIN=true while FLASK_ENV=production. "
            "Disable ENABLE_DEV_LOGIN before deploying."
        )
        raise RuntimeError(
            "ENABLE_DEV_LOGIN cannot be enabled when FLASK_ENV=production"
        )
    if enabled:
        # Loud startup warning for local/dev
        banner = (
            "\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
            "!!  WARNING: ENABLE_DEV_LOGIN is ON                       !!\n"
            "!!  POST /api/auth/dev-login bypasses Microsoft SSO.      !!\n"
            "!!  NEVER enable this setting in production.              !!\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
        )
        print(banner, file=sys.stderr)
        logger.warning(
            "ENABLE_DEV_LOGIN is enabled (FLASK_ENV=%s) — local SSO bypass active",
            env or "development",
        )


def _assert_production_secrets(app: Flask) -> None:
    """Refuse weak / missing secrets when FLASK_ENV=production (issue #28)."""
    env = (app.config.get("FLASK_ENV") or "").strip().lower()
    if env != "production":
        return

    secret = app.config.get("SECRET_KEY") or ""
    fernet = app.config.get("FERNET_KEY") or ""
    use_gcp = bool(app.config.get("USE_GCP_SECRETS"))

    problems: list[str] = []
    if not secret or secret == _DEV_SECRET_DEFAULT:
        problems.append("SECRET_KEY must be set to a non-default value")
    if not fernet:
        problems.append("FERNET_KEY must be set")
    if not use_gcp:
        problems.append("USE_GCP_SECRETS must be true in production")
    if not app.config.get("SESSION_COOKIE_SECURE", False):
        problems.append("SESSION_COOKIE_SECURE must be true in production")

    if problems:
        detail = "; ".join(problems)
        logger.critical("REFUSING TO START in production: %s", detail)
        raise RuntimeError(f"Production security checks failed: {detail}")


def _register_error_handlers(app: Flask) -> None:
    """Return JSON errors without stack traces, paths, SQL, or key material."""

    from api.tenancy import TenancyError

    @app.errorhandler(TenancyError)
    def _tenancy_error(exc: TenancyError):
        return jsonify({"error": "Forbidden", "detail": exc.detail}), 403

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        return jsonify({"error": exc.name, "detail": exc.description}), exc.code

    @app.errorhandler(Exception)
    def _unhandled_error(exc: Exception):
        logger.exception("Unhandled server error")
        # Never mirror exception text — it may include paths, SQL, or secrets.
        return jsonify({"error": "Internal server error"}), 500


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)
    # Never enable Flask interactive debugger in this app factory.
    app.config["DEBUG"] = False
    app.config["PROPAGATE_EXCEPTIONS"] = False
    _assert_dev_login_safe(app)
    _assert_production_secrets(app)

    CORS(
        app,
        origins=app.config["CORS_ORIGINS"],
        supports_credentials=True,
    )

    # Redis-backed server-side sessions when REDIS_URL is configured
    redis_url = app.config.get("REDIS_URL") or ""
    if redis_url:
        import redis as redis_lib

        app.config["SESSION_REDIS"] = redis_lib.from_url(redis_url)
        Session(app)

    db.init_app(app)
    migrate.init_app(app, db)
    init_limiter(app)
    register_security_middleware(app)
    _register_error_handlers(app)

    # Register models with SQLAlchemy so Alembic can see them
    from api import models  # noqa: F401

    from api.auth import bp as auth_bp
    from api.integrations import bp as integrations_bp
    from api.msgraph_bp import bp as msgraph_bp
    from api.plaid_bp import bp as plaid_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(integrations_bp, url_prefix="/api/integrations")
    app.register_blueprint(plaid_bp, url_prefix="/api/plaid")
    app.register_blueprint(msgraph_bp, url_prefix="/api/msgraph")

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                # Surface so operators / the SPA can detect unsafe local bypass.
                "dev_login_enabled": bool(app.config.get("ENABLE_DEV_LOGIN")),
                "flask_env": app.config.get("FLASK_ENV"),
            }
        )

    _register_portal_static(app)

    return app


def _register_portal_static(app: Flask) -> None:
    """Serve the built React SPA from PORTAL_STATIC_DIR (Cloud Run same-origin)."""
    static_dir = (app.config.get("PORTAL_STATIC_DIR") or "").strip()
    if not static_dir or not os.path.isdir(static_dir):
        return
    index_path = os.path.join(static_dir, "index.html")
    if not os.path.isfile(index_path):
        logger.warning("PORTAL_STATIC_DIR set but index.html missing: %s", static_dir)
        return

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def portal_spa(path: str):
        # API blueprints are registered first; this catch-all is for SPA routes only.
        if path.startswith("api/") or path == "api":
            return jsonify({"error": "Not found"}), 404
        candidate = os.path.join(static_dir, path)
        if path and os.path.isfile(candidate):
            return send_from_directory(static_dir, path)
        return send_from_directory(static_dir, "index.html")



if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
