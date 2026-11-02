"""Microsoft Graph blueprint package."""

from flask import Blueprint

bp = Blueprint('msgraph', __name__)

from src.api.msgraph_bp import routes  # noqa: F401
