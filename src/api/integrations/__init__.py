"""Integrations blueprint: dashboard status (connect flows in later issues)."""

from flask import Blueprint

bp = Blueprint('integrations', __name__)

from src.api.integrations import routes  # noqa: F401
