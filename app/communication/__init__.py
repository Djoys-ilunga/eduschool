from flask import Blueprint
com_bp = Blueprint('communication', __name__, url_prefix='/communication')
from app.communication import routes  # noqa
