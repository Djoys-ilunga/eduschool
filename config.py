import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration centrale de l'application."""
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError(
            'SECRET_KEY manquante. Definissez-la dans le fichier .env :\n'
            '  SECRET_KEY=votre-cle-secrete-tres-longue\n'
            '  (utilisez: python -c "import secrets; print(secrets.token_hex(32))")'
        )
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(os.path.dirname(__file__), 'eduschool.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'max_overflow': 10,
    }

    # Flask-Login
    USE_SESSION_FOR_NEXT = True

    # Upload
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    # Pagination
    ITEMS_PER_PAGE = 20

    # Plans par défaut
    DEFAULT_PLANS = [
        {
            'nom': 'Gratuit',
            'prix': 0,
            'devise': 'USD',
            'max_eleves': 50,
            'max_enseignants': 5,
            'feature_limitees': True
        },
        {
            'nom': 'Basique',
            'prix': 29,
            'devise': 'USD',
            'max_eleves': 300,
            'max_enseignants': 30,
            'feature_limitees': False
        },
        {
            'nom': 'Premium',
            'prix': 79,
            'devise': 'USD',
            'max_eleves': 1000,
            'max_enseignants': 100,
            'feature_limitees': False
        },
        {
            'nom': 'Enterprise',
            'prix': 199,
            'devise': 'USD',
            'max_eleves': 99999,
            'max_enseignants': 9999,
            'feature_limitees': False
        }
    ]


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}
