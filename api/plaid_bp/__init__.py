"""Plaid blueprint package."""

from flask import Blueprint

bp = Blueprint("plaid", __name__)

from api.plaid_bp import routes  # noqa: E402, F401
