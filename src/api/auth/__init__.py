"""Auth blueprint: Microsoft SSO + CSRF helpers."""

from flask import Blueprint

bp = Blueprint('auth', __name__)

from src.api.auth import routes  # noqa: F401
