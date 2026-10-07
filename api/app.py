"""Flask application factory for the portal API."""

from flask import Flask, jsonify
from flask_cors import CORS
from flask_session import Session

from api.config import Config
from api.extensions import db, migrate
from api.middleware import register_security_middleware
from api.rate_limit import init_limiter


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

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
        return jsonify({"status": "ok"})

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
