"""Call Center blueprint."""

from flask import Blueprint

call_center_bp = Blueprint(
    "call_center",
    __name__,
    template_folder="templates",
    url_prefix="/call-center",
)

call_center_api_bp = Blueprint(
    "call_center_api",
    __name__,
    url_prefix="/api/callcenter",
)

from . import routes  # noqa: E402, F401
