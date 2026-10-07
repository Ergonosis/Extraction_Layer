"""Flask application factory for the portal API."""

import logging
import sys

from flask import Flask, jsonify
from flask_cors import CORS
from flask_session import Session

from api.config import Config
from api.extensions import db, migrate
from api.middleware import register_security_middleware
from api.rate_limit import init_limiter

logger = logging.getLogger(__name__)


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


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)
    _assert_dev_login_safe(app)

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

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
