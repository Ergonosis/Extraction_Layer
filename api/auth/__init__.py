"""Auth blueprint: Microsoft SSO + CSRF helpers."""

from flask import Blueprint

bp = Blueprint("auth", __name__)

from api.auth import routes  # noqa: E402, F401
