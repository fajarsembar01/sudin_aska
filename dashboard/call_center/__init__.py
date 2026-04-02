"""Call Center blueprint."""

from flask import Blueprint

call_center_bp = Blueprint(
    "call_center",
    __name__,
    template_folder="templates",
    url_prefix="/call-center",
)

from . import routes  # noqa: E402, F401
