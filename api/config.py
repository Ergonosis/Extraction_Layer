"""Settings loaded from environment variables / GCP Secret Manager."""

from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _secret_from_gcp(secret_id: str) -> str | None:
    """Load the latest secret value from GCP Secret Manager, or None on failure/skip."""
    project = os.getenv("GCP_PROJECT_ID", "")
    if not project or not secret_id:
        return None
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("utf-8")
    except Exception:
        return None


def _load_secret(env_name: str, default: str = "") -> str:
    """Prefer GCP Secret Manager when USE_GCP_SECRETS is set; else env / default."""
    if _env_bool("USE_GCP_SECRETS", False):
        secret_id = os.getenv(f"{env_name}_SECRET_ID", env_name)
        value = _secret_from_gcp(secret_id)
        if value:
            return value
    return os.getenv(env_name, default)


class Config:
    """Base configuration for the portal API."""

    FLASK_ENV = os.getenv("FLASK_ENV", "development")

    SECRET_KEY = _load_secret("SECRET_KEY", "dev-only-change-me")
    # Local default: dedicated extraction-portal-postgres Docker container (host port 5434).
    # Do not use 5432/5433 (other projects). Override with DATABASE_URL for Cloud SQL in production.
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://portal:portal@localhost:5434/portal",
    )

    # Dedicated portal Redis (Docker extraction-portal-redis). Used for sessions + rate limits.
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Microsoft Entra ID — multi-tenant SSO (issue #21)
    # Authority uses /organizations so any work/school tenant can sign in.
    MS_CLIENT_ID = os.getenv("MS_CLIENT_ID", "")
    MS_CLIENT_SECRET = _load_secret("MS_CLIENT_SECRET", "")
    MS_TENANT_ID = os.getenv("MS_TENANT_ID", "")  # optional legacy; not used for SSO authority
    MS_AUTHORITY = os.getenv(
        "MS_AUTHORITY",
        "https://login.microsoftonline.com/organizations",
    )
    # Local default goes through the Vite proxy so the session cookie is set on the SPA origin.
    MS_REDIRECT_URI = os.getenv(
        "MS_REDIRECT_URI",
        "http://localhost:5175/api/auth/callback",
    )
    # Separate redirect for Graph delegated consent (issue #25) — register in Entra.
    MS_GRAPH_REDIRECT_URI = os.getenv(
        "MS_GRAPH_REDIRECT_URI",
        "http://localhost:5175/api/msgraph/callback",
    )
    # Comma-separated Entra tenant IDs; empty = allow any organizational tenant
    MS_TENANT_ALLOWLIST = [
        tid.strip()
        for tid in os.getenv("MS_TENANT_ALLOWLIST", "").split(",")
        if tid.strip()
    ]
    MS_SSO_SCOPES = ["openid", "profile", "email"]

    # Where the browser returns after successful SSO
    PORTAL_URL = os.getenv("PORTAL_URL", "http://localhost:5175").rstrip("/")
    PORTAL_POST_LOGIN_PATH = os.getenv("PORTAL_POST_LOGIN_PATH", "/connections")

    # LOCAL ONLY: POST /api/auth/dev-login. Never enable in production.
    # Requires FLASK_ENV != production AND ENABLE_DEV_LOGIN=true.
    ENABLE_DEV_LOGIN = _env_bool("ENABLE_DEV_LOGIN", False)

    # Plaid (used by later issues)
    PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "")
    PLAID_SECRET = _load_secret("PLAID_SECRET", "")
    PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")
    # Where portal-triggered Plaid exports write JSON (issue #27)
    PLAID_RECORDS_DIR = os.getenv("PLAID_RECORDS_DIR", "records")

    # Fernet key for token encryption (used by later issues)
    FERNET_KEY = _load_secret("FERNET_KEY", "")

    # CORS: portal origin for local Vite dev server
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5175").split(",")
        if origin.strip()
    ]

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Secure cookies break plain http://localhost; enable in production (or set env).
    SESSION_COOKIE_SECURE = _env_bool(
        "SESSION_COOKIE_SECURE",
        default=(FLASK_ENV == "production"),
    )
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_REFRESH_EACH_REQUEST = True

    # flask-session (Redis-backed when REDIS_URL is set)
    SESSION_TYPE = "redis"
    SESSION_PERMANENT = True
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "portal:session:"
