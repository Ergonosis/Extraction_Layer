"""Rate limiting via flask-limiter (PostgreSQL shared counters by default)."""

from __future__ import annotations

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Register custom storage scheme before Limiter resolves STORAGE_URI.
import api.rate_limit_storage  # noqa: F401

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["30 per minute"],
    # Never silently fall back to process-local memory on storage failure.
    in_memory_fallback_enabled=False,
)

# Auth / mutation endpoint limits (issue #21+)
auth_login_limit = limiter.limit("10 per minute")
auth_callback_limit = limiter.limit("5 per minute")
auth_me_limit = limiter.limit("30 per minute")
mutation_limit = limiter.limit("10 per minute")
strict_mutation_limit = limiter.limit("5 per minute")
# Integration status polls (issues #24 / #25)
plaid_status_limit = limiter.limit("15 per minute")
msgraph_status_limit = limiter.limit("15 per minute")


def init_limiter(app: Flask) -> Limiter:
    """Bind limiter to the app; prefer shared PostgreSQL, optional Redis."""
    backend = (app.config.get("RATELIMIT_STORAGE_BACKEND") or "sqlalchemy").strip().lower()

    if backend == "redis":
        redis_url = (app.config.get("REDIS_URL") or "").strip()
        if not redis_url:
            raise RuntimeError(
                "REDIS_URL must be set when RATELIMIT_STORAGE_BACKEND=redis"
            )
        app.config["RATELIMIT_STORAGE_URI"] = redis_url
        app.config.pop("RATELIMIT_STORAGE_OPTIONS", None)
    elif backend in {"sqlalchemy", "postgres", "postgresql", "portal-postgres"}:
        database_url = (app.config.get("DATABASE_URL") or "").strip()
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL must be set when using PostgreSQL rate-limit storage"
            )
        app.config["RATELIMIT_STORAGE_URI"] = "portal-postgres://"
        app.config["RATELIMIT_STORAGE_OPTIONS"] = {
            "database_url": database_url,
            "pool_size": int(app.config.get("DB_POOL_SIZE") or 2),
            "max_overflow": int(app.config.get("DB_MAX_OVERFLOW") or 1),
        }
    else:
        raise RuntimeError(
            f"Unsupported RATELIMIT_STORAGE_BACKEND={backend!r}; "
            "use sqlalchemy or redis (memory:// is not allowed)"
        )

    limiter.init_app(app)
    return limiter
