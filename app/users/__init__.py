from flask import Blueprint

users_bp = Blueprint('users', __name__, template_folder='../templates/users', url_prefix='/users')

from app.users import routes  # noqa
