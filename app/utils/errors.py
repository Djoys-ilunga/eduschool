from flask import render_template
from flask_login import current_user


def register_error_handlers(app):
    """Enregistre les gestionnaires d'erreurs personnalisés."""

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(e):
        return render_template('errors/500.html'), 500
