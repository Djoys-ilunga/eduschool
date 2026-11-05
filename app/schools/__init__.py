from flask import Blueprint

schools_bp = Blueprint('schools', __name__, template_folder='../templates/schools', url_prefix='/schools')

from app.schools import routes  # noqa
