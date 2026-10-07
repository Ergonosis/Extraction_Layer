"""Rate limiting via flask-limiter (Redis-backed when REDIS_URL is set)."""

from __future__ import annotations

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["30 per minute"],
)

# Auth / mutation endpoint limits (issue #21+)
auth_login_limit = limiter.limit("10 per minute")
auth_callback_limit = limiter.limit("5 per minute")
auth_me_limit = limiter.limit("30 per minute")
mutation_limit = limiter.limit("10 per minute")
strict_mutation_limit = limiter.limit("5 per minute")


def init_limiter(app: Flask) -> Limiter:
    """Bind limiter to the app; prefer Redis storage from config."""
    redis_url = (app.config.get("REDIS_URL") or "").strip()
    app.config["RATELIMIT_STORAGE_URI"] = redis_url or "memory://"
    limiter.init_app(app)
    return limiter
