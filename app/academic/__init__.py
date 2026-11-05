from flask import Blueprint

academic_bp = Blueprint('academic', __name__, template_folder='../templates/academic', url_prefix='/academic')

from app.academic import routes  # noqa
