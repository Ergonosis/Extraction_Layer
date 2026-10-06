"""Integrations blueprint package."""

from flask import Blueprint

bp = Blueprint("integrations", __name__)

from api.integrations import routes  # noqa: E402, F401
