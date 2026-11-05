from app.models import db
from datetime import datetime


class School(db.Model):
    __tablename__ = 'schools'

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    adresse = db.Column(db.String(255), nullable=True)
    ville = db.Column(db.String(100), nullable=True)
    pays = db.Column(db.String(100), nullable=False, default='CD')
    telephone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    site_web = db.Column(db.String(255), nullable=True)
    logo = db.Column(db.String(255), nullable=True)
    cachet = db.Column(db.String(255), nullable=True)

    # Configuration
    devise = db.Column(db.String(10), nullable=False, default='CDF')
    langue = db.Column(db.String(10), nullable=False, default='fr')
    fuseau_horaire = db.Column(db.String(50), default='Africa/Kinshasa')
    type_ecole = db.Column(db.String(30), nullable=True)  # primaire, secondaire, superieur, mixte

    @property
    def cycle(self):
        """Retourne 'trimestre' ou 'semestre' selon le type d'ecole."""
        if self.type_ecole and 'secondaire' in self.type_ecole.lower():
            return 'semestre'
        return 'trimestre'

    @property
    def nb_divisions(self):
        """Nombre de divisions: 3 pour primaire, 2 pour secondaire."""
        return 2 if self.cycle == 'semestre' else 3

    @property
    def division_label(self):
        """Label: 'Trimestre' ou 'Semestre'."""
        return 'Semestre' if self.cycle == 'semestre' else 'Trimestre'

    @property
    def division_short(self):
        return 'S' if self.cycle == 'semestre' else 'T'

    # Statut
    statut = db.Column(db.String(20), nullable=False, default='active')  # active, suspendue, en_attente
    plan_id = db.Column(db.Integer, db.ForeignKey('plans.id'), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    plan = db.relationship('Plan', backref='ecoles', lazy=True)

    @property
    def nombre_eleves(self):
        from app.models.user import User
        return User.query.filter_by(school_id=self.id, role='student', actif=True).count()

    @property
    def nombre_enseignants(self):
        from app.models.user import User
        return User.query.filter_by(school_id=self.id, role='teacher', actif=True).count()

    @property
    def nombre_classes(self):
        from app.models.academic import Class
        return Class.query.filter_by(school_id=self.id, actif=True).count()

    def __repr__(self):
        return f'<School {self.nom} ({self.code})>'
