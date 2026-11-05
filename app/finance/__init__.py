from flask import Blueprint

finance_bp = Blueprint('finance', __name__, url_prefix='/finance')

from app.finance import routes  # noqa
