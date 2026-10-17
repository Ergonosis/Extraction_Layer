"""Microsoft Graph blueprint package."""

from flask import Blueprint

bp = Blueprint("msgraph", __name__)

from api.msgraph_bp import routes  # noqa: E402, F401
