import secrets, string
from flask import request
from flask_login import current_user


def _get_school_id():
    """Retourne l'ID de l'ecole courante selon le role.
    - Super admin: lit school_id depuis les query params
    - Autres roles: utilise l'ecole de l'utilisateur connecte
    """
    if current_user.is_authenticated and hasattr(current_user, 'is_super_admin') and current_user.is_super_admin:
        return request.args.get('school_id', None, type=int)
    return current_user.school_id if current_user.is_authenticated else None


def _generate_random_password(length=10):
    chars = string.ascii_letters + string.digits
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(length))
        if any(c.isupper() for c in pwd) and any(c.islower() for c in pwd) and any(c.isdigit() for c in pwd):
            return pwd
