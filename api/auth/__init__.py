"""Auth blueprint package (SSO routes added in a later issue)."""

from flask import Blueprint

bp = Blueprint("auth", __name__)

from api.auth import routes  # noqa: E402, F401
