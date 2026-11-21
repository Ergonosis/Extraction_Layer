"""Billing HTTP blueprints (customer + admin)."""

from flask import Blueprint

bp = Blueprint('billing', __name__)
admin_bp = Blueprint('admin_billing', __name__)

from src.api.billing_bp import admin_routes, routes  # noqa: F401
