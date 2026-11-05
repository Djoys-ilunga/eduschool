"""CSRF protection decorator for Flask routes.
Uses flask_wtf.csrf for token generation/validation (same as templates).
"""
from functools import wraps
from flask import request, flash, redirect, url_for
from flask_wtf.csrf import validate_csrf


def require_csrf(f):
    """Decorator: require valid CSRF token on POST/PUT/DELETE requests.
    
    Validation uses flask_wtf.csrf.validate_csrf — the same module
    that powers the {{ _csrf() }} template global and FlaskForm CSRF.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            try:
                validate_csrf(request.form.get('csrf_token', ''))
            except Exception:
                flash('Jeton CSRF invalide ou expire. Veuillez reessayer.', 'danger')
                return redirect(request.referrer or url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated
