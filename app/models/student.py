from app.models import db
from datetime import datetime


class StudentProfile(db.Model):
    """Profil etendu de l'eleve (complement de la table User)."""
    __tablename__ = 'student_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)

    # Identite etendue
    date_naissance = db.Column(db.Date, nullable=True)
    lieu_naissance = db.Column(db.String(100), nullable=True)
    sexe = db.Column(db.String(1), nullable=True)  # M, F
    nationalite = db.Column(db.String(50), nullable=True, default='Congolaise')

    # Contact famille
    adresse_famille = db.Column(db.String(255), nullable=True)
    personne_urgence = db.Column(db.String(100), nullable=True)
    telephone_urgence = db.Column(db.String(20), nullable=True)

    # Sante
    allergies = db.Column(db.Text, nullable=True)
    traitements = db.Column(db.Text, nullable=True)
    groupe_sanguin = db.Column(db.String(5), nullable=True)
    observations_medicales = db.Column(db.Text, nullable=True)

    # Scolarite
    matricule = db.Column(db.String(30), unique=True, nullable=True, index=True)
    date_inscription = db.Column(db.Date, nullable=True)
    statut = db.Column(db.String(20), nullable=False, default='inscrit')  # inscrit, redoublant, transfere, exclu, diplome
    boursier = db.Column(db.Boolean, default=False)
    bourse_description = db.Column(db.String(200), nullable=True)

    # Documents
    acte_naissance = db.Column(db.String(255), nullable=True)
    photo_identite = db.Column(db.String(255), nullable=True)
    certificat_medical = db.Column(db.String(255), nullable=True)
    bulletin_precedent = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    user = db.relationship('User', backref=db.backref('student_profile', uselist=False, cascade='all, delete-orphan'), lazy=True)
    parents = db.relationship('StudentParent', backref='student_profile', lazy=True, cascade='all, delete-orphan')

    @property
    def age(self):
        if not self.date_naissance:
            return None
        today = datetime.utcnow().date()
        return today.year - self.date_naissance.year - (
            (today.month, today.day) < (self.date_naissance.month, self.date_naissance.day)
        )

    @property
    def parent_bulletin_access(self):
        """Retourne True si le parent a acces aux bulletins (par defaut: True)."""
        from app.models.student import StudentBulletinAccess
        access = StudentBulletinAccess.query.filter_by(student_profile_id=self.id).first()
        return access.parent_access if access else True

    def __repr__(self):
        return f'<StudentProfile user={self.user_id} matricule={self.matricule}>'


class StudentParent(db.Model):
    """Lien parent-eleve (un parent peut avoir plusieurs enfants)."""
    __tablename__ = 'student_parents'

    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    student_profile_id = db.Column(db.Integer, db.ForeignKey('student_profiles.id', ondelete='CASCADE'), nullable=False, index=True)
    relation = db.Column(db.String(30), nullable=True)  # pere, mere, tuteur, oncle, tante, etc.
    est_tuteur_principal = db.Column(db.Boolean, default=False)
    peut_payer = db.Column(db.Boolean, default=True)
    recoit_notifications = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def student(self):
        """Retourne l'utilisateur eleve via le StudentProfile."""
        return self.student_profile.user if self.student_profile else None

    # Relations
    parent = db.relationship('User', foreign_keys=[parent_id], backref=db.backref('enfants', lazy=True, cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('parent_id', 'student_profile_id', name='uq_parent_student'),
    )

    def __repr__(self):
        return f'<StudentParent parent={self.parent_id} student={self.student_profile_id}>'


class StudentEnrollment(db.Model):
    """Inscription d'un eleve a une classe pour une annee scolaire."""
    __tablename__ = 'student_enrollments'

    id = db.Column(db.Integer, primary_key=True)
    student_profile_id = db.Column(db.Integer, db.ForeignKey('student_profiles.id', ondelete='CASCADE'), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False, index=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)

    date_inscription = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    statut = db.Column(db.String(20), nullable=False, default='actif')  # actif, redouble, transfere, termine
    date_fin = db.Column(db.Date, nullable=True)  # Date de fin d'inscription (archive/termine)
    numero_ordre = db.Column(db.Integer, nullable=True)  # Numero dans la classe

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    student_profile = db.relationship('StudentProfile', backref='inscriptions', lazy=True)
    classe = db.relationship('Class', backref='eleves_inscrits', lazy=True)
    annee_scolaire = db.relationship('AcademicYear', backref='inscriptions', lazy=True)
    school = db.relationship('School', backref='inscriptions', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('student_profile_id', 'academic_year_id', name='uq_student_year'),
    )

    @property
    def student(self):
        return self.student_profile.user if self.student_profile else None

    def __repr__(self):
        return f'<StudentEnrollment student={self.student_profile_id} class={self.class_id}>'


class StudentBulletinAccess(db.Model):
    """Controle d'acces parent aux bulletins : active/desactive par eleve."""
    __tablename__ = 'student_bulletin_access'

    id = db.Column(db.Integer, primary_key=True)
    student_profile_id = db.Column(db.Integer, db.ForeignKey('student_profiles.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    parent_access = db.Column(db.Boolean, default=True)  # True = parent peut voir les bulletins
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student_profile = db.relationship('StudentProfile', backref=db.backref('bulletin_access', lazy=True, uselist=False, cascade='all, delete-orphan'), lazy=True)

    def __repr__(self):
        return f'<BulletinAccess student={self.student_profile_id} parent_access={self.parent_access}>'
