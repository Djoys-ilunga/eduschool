from flask import Blueprint

students_bp = Blueprint('students', __name__, template_folder='../templates/students', url_prefix='/students')

from app.students import routes  # noqa
