"""MONEV BOS/BOP Blueprint."""

from flask import Blueprint

monev_bos_bp = Blueprint("monev_bos", __name__, url_prefix="/monev-bos", template_folder="templates")

from . import routes
