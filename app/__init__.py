from flask import Flask, jsonify, send_from_directory
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from app.models import db
from config import config_by_name
import os
import logging
from logging.handlers import RotatingFileHandler

login_manager = LoginManager()
migrate = Migrate()

login_manager.login_view = 'auth.login'
login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
login_manager.login_message_category = 'warning'


def create_app(config_name=None):
    """Factory de l'application Flask."""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Logging fichier avec rotation (production)
    if config_name != 'development':
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        handler = RotatingFileHandler(
            os.path.join(log_dir, 'eduschool.log'),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(module)s: %(message)s'
        ))
        handler.setLevel(logging.WARNING)
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.WARNING)

    # Initialisation des extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # SQLite pragmas optimisés production
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Création du dossier uploads
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Enregistrement des blueprints
    from app.auth import auth_bp
    from app.dashboard import dashboard_bp
    from app.schools import schools_bp
    from app.users import users_bp
    from app.academic import academic_bp
    from app.students import students_bp
    from app.finance import finance_bp
    from app.communication import com_bp
    from app.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(schools_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(academic_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(com_bp)
    app.register_blueprint(admin_bp)

    # User loader pour Flask-Login
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Gestion des erreurs

    # Injecte l'annee scolaire active dans tous les templates
    from markupsafe import Markup
    from flask_wtf.csrf import generate_csrf
    
    def _csrf_input():
        """Retourne un champ hidden CSRF complet (Markup)."""
        token = generate_csrf()
        return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')
    
    # csrf_token en globals Jinja = impossible a ecraser par render_template()
    app.jinja_env.globals['_csrf'] = _csrf_input

    # Health check — monitoring
    @app.route('/health')
    def health_check():
        try:
            with db.engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            return jsonify({'status': 'ok', 'db': 'connected'}), 200
        except Exception as e:
            return jsonify({'status': 'error', 'db': str(e)}), 500

    # Route pour servir les fichiers uploadés
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # Filtre Jinja pour formater les dates en francais
    @app.template_filter('date_fr')
    def date_fr_filter(dt, fmt='%d %B %Y'):
        """Formate une date avec les noms de mois/jours en francais."""
        if dt is None:
            return ''
        mois = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
        jours = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
        result = dt.strftime(fmt)
        # Remplacer les noms anglais par les francais
        en_months = ['January', 'February', 'March', 'April', 'May', 'June',
                     'July', 'August', 'September', 'October', 'November', 'December']
        en_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for en, fr in zip(en_months, mois):
            result = result.replace(en, fr)
        for en, fr in zip(en_days, jours):
            result = result.replace(en, fr)
        return result
    
    @app.context_processor
    def inject_years():
        from flask_login import current_user
        ctx = {}
        if current_user.is_authenticated:
            school_id = current_user.school_id if not current_user.is_super_admin else None
            from app.models.academic import AcademicYear
            if school_id:
                years = AcademicYear.query.filter_by(school_id=school_id).order_by(AcademicYear.date_debut.desc()).all()
            else:
                years = AcademicYear.query.order_by(AcademicYear.date_debut.desc()).all()
            from app.academic.routes import _get_active_year_id
            active_id = _get_active_year_id(school_id)
            active_year = None
            if active_id:
                active_year = AcademicYear.query.get(active_id)
            ctx.update(all_years=years, active_year=active_year, active_year_id=active_id)
        else:
            ctx.update(all_years=[], active_year=None, active_year_id=None)
        return ctx

    from app.utils.errors import register_error_handlers
    register_error_handlers(app)

    # Initialisation DB
    from app.utils.database import init_db
    with app.app_context():
        init_db()

    return app
