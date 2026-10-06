"""Settings loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration for the portal API."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/portal")

    # Microsoft Entra ID / MS Graph (used by later issues)
    MS_CLIENT_ID = os.getenv("MS_CLIENT_ID", "")
    MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "")
    MS_TENANT_ID = os.getenv("MS_TENANT_ID", "")

    # Plaid (used by later issues)
    PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "")
    PLAID_SECRET = os.getenv("PLAID_SECRET", "")
    PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")

    # Fernet key for token encryption (used by later issues)
    FERNET_KEY = os.getenv("FERNET_KEY", "")

    # CORS: portal origin for local Vite dev server
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
