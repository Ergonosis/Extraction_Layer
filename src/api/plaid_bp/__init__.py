"""Plaid blueprint package."""

from flask import Blueprint

bp = Blueprint('plaid', __name__)

from src.api.plaid_bp import routes  # noqa: F401
