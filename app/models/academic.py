from app.models import db
from datetime import datetime


class AcademicYear(db.Model):
    """Année scolaire (ex: 2026-2027)."""
    __tablename__ = 'academic_years'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    nom = db.Column(db.String(50), nullable=False)  # ex: "2026-2027"
    date_debut = db.Column(db.Date, nullable=False)
    date_fin = db.Column(db.Date, nullable=False)
    statut = db.Column(db.String(20), nullable=False, default='active')  # active, closee, archivee
    trimestres_json = db.Column(db.Text, nullable=True)  # JSON: [{"nom":"T1","debut":"...","fin":"..."},...]

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    school = db.relationship('School', backref='annees_scolaires', lazy=True)
    classes = db.relationship('Class', backref='annee_scolaire', lazy=True, cascade='all, delete-orphan')

    @property
    def trimestres(self):
        import json
        if not self.trimestres_json:
            # Générer des trimestres par défaut
            return [
                {'nom': '1er Trimestre', 'debut': str(self.date_debut), 'fin': ''},
                {'nom': '2ème Trimestre', 'debut': '', 'fin': ''},
                {'nom': '3ème Trimestre', 'debut': '', 'fin': str(self.date_fin)},
            ]
        return json.loads(self.trimestres_json)

    def __repr__(self):
        return f'<AcademicYear {self.nom} ({self.statut})>'


class Subject(db.Model):
    """Matière / Discipline."""
    __tablename__ = 'subjects'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    nom = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(20), nullable=True)
    description = db.Column(db.Text, nullable=True)
    categorie = db.Column(db.String(50), nullable=True)  # scientifique, litteraire, technique, langue, sport
    actif = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    school = db.relationship('School', backref='matieres', lazy=True)

    def __repr__(self):
        return f'<Subject {self.nom}>'


class Class(db.Model):
    """Classe / Promotion (ex: 6ème A, Terminale S1)."""
    __tablename__ = 'classes'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False, index=True)

    nom = db.Column(db.String(100), nullable=False)  # ex: "6ème A"
    niveau = db.Column(db.String(50), nullable=True)  # ex: "6ème", "Terminale"
    section = db.Column(db.String(50), nullable=True)  # ex: "Scientifique", "Littéraire"
    capacite_max = db.Column(db.Integer, nullable=True)
    salle = db.Column(db.String(50), nullable=True)
    titulaire_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    actif = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    school = db.relationship('School', backref='classes_list', lazy=True)
    titulaire = db.relationship('User', foreign_keys=[titulaire_id], backref='classe_titulaire', lazy=True)
    matieres = db.relationship('ClassSubject', backref='classe', lazy=True, cascade='all, delete-orphan')

    @property
    def nombre_eleves(self):
        from app.models.student import StudentEnrollment
        return StudentEnrollment.query.filter_by(class_id=self.id, statut='actif').count()

    def __repr__(self):
        return f'<Class {self.nom}>'


class ClassSubject(db.Model):
    """Association Classe-Matière avec coefficient et heures."""
    __tablename__ = 'class_subjects'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    coefficient = db.Column(db.Float, nullable=False, default=1.0)
    heures_par_semaine = db.Column(db.Float, nullable=True)
    groupe = db.Column(db.String(50), nullable=True)  # ex: "Groupe 1", "Optionnel"

    __table_args__ = (
        db.UniqueConstraint('class_id', 'subject_id', name='uq_class_subject'),
    )

    # Relations
    subject = db.relationship('Subject', backref='classes_associees', lazy=True)
    teacher = db.relationship('User', foreign_keys=[teacher_id], backref='matieres_enseignees', lazy=True)

    def __repr__(self):
        return f'<ClassSubject class={self.class_id} subject={self.subject_id} coef={self.coefficient}>'


class Trimester(db.Model):
    """Trimestre avec dates precises."""
    __tablename__ = 'trimesters'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False, index=True)
    numero = db.Column(db.Integer, nullable=False)  # 1, 2, 3
    nom = db.Column(db.String(50), nullable=False)  # "1er Trimestre"
    date_debut = db.Column(db.Date, nullable=False)
    date_fin = db.Column(db.Date, nullable=False)
    coefficient = db.Column(db.Float, default=1.0)  # poids dans la moyenne annuelle

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    school = db.relationship('School', backref='trimestres', lazy=True)
    annee_scolaire = db.relationship('AcademicYear', backref='trimestres_list', lazy=True)
    periodes = db.relationship('Period', backref='trimestre', lazy=True, cascade='all, delete-orphan',
                               order_by='Period.numero')

    __table_args__ = (
        db.UniqueConstraint('academic_year_id', 'numero', name='uq_trimester_num'),
    )

    def __repr__(self):
        return f'<Trimester {self.numero} ({self.nom})>'


class Period(db.Model):
    """Periode / Sequence dans un trimestre."""
    __tablename__ = 'periods'

    id = db.Column(db.Integer, primary_key=True)
    trimester_id = db.Column(db.Integer, db.ForeignKey('trimesters.id', ondelete='CASCADE'), nullable=False, index=True)
    numero = db.Column(db.Integer, nullable=False)  # 1, 2, 3 dans le trimestre
    nom = db.Column(db.String(50), nullable=False)  # "Interrogations", "Compositions", "Examens"
    date_debut = db.Column(db.Date, nullable=False)
    date_fin = db.Column(db.Date, nullable=False)
    coefficient = db.Column(db.Float, default=1.0)  # poids dans le trimestre (ex: compo=2, examen=3)
    type_evaluation = db.Column(db.String(30), default='continue')  # continue, composition, examen

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    notes = db.relationship('Grade', backref='period', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('trimester_id', 'numero', name='uq_period_num'),
    )

    def __repr__(self):
        return f'<Period {self.numero} ({self.nom})>'

    @staticmethod
    def default_periods_for_division(school, div_num):
        """Retourne les periodes par defaut pour une division (trimestre ou semestre)."""
        cycle = school.cycle if school else 'trimestre'
        prefix = 'S' if cycle == 'semestre' else 'T'
        if cycle == 'semestre':
            # Secondaire: 2 periodes par semestre
            return [
                {'numero': 1, 'nom': f'Interrogations {prefix}{div_num}', 'coefficient': 1.0, 'type_evaluation': 'continue'},
                {'numero': 2, 'nom': f'Examens {prefix}{div_num}', 'coefficient': 3.0, 'type_evaluation': 'examen'},
            ]
        else:
            # Primaire: 3 periodes par trimestre
            return [
                {'numero': 1, 'nom': f'Interrogations {prefix}{div_num}', 'coefficient': 1.0, 'type_evaluation': 'continue'},
                {'numero': 2, 'nom': f'Compositions {prefix}{div_num}', 'coefficient': 2.0, 'type_evaluation': 'composition'},
                {'numero': 3, 'nom': f'Examens {prefix}{div_num}', 'coefficient': 3.0, 'type_evaluation': 'examen'},
            ]


class Deliberation(db.Model):
    """Conseil de classe / Deliberation par classe et trimestre."""
    __tablename__ = 'deliberations'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False, index=True)
    trimester_id = db.Column(db.Integer, db.ForeignKey('trimesters.id'), nullable=False, index=True)

    statut = db.Column(db.String(20), nullable=False, default='brouillon')  # brouillon, valide, publie
    date_deliberation = db.Column(db.DateTime, nullable=True)
    decision_json = db.Column(db.Text, nullable=True)  # JSON: {"<student_id>": "<decision>"}
    matieres_repechage = db.Column(db.Text, nullable=True)  # JSON: {"<student_id>": [<subject_id>, ...]}
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    school = db.relationship('School', backref='deliberations', lazy=True)
    annee_scolaire = db.relationship('AcademicYear', backref='deliberations', lazy=True)
    classe = db.relationship('Class', backref='deliberations', lazy=True)
    trimester = db.relationship('Trimester', backref='deliberations', lazy=True)
    creator = db.relationship('User', foreign_keys=[created_by], backref='deliberations_creees', lazy=True)

    # Decisions possibles
    DECISIONS = [
        ('passe', 'Passe'),
        ('redouble', 'Redouble'),
        ('avertissement', 'Avertissement'),
        ('encouragement', 'Encouragement'),
        ('felicitations', 'Félicitations'),
        ('repechage', 'Repêchage'),
    ]

    __table_args__ = (
        db.UniqueConstraint('class_id', 'trimester_id', 'academic_year_id', name='uq_deliberation_class_trimester_year'),
    )

    @property
    def decisions(self):
        """Retourne le dict des decisions parse depuis le JSON."""
        import json
        if not self.decision_json:
            return {}
        return json.loads(self.decision_json)

    @decisions.setter
    def decisions(self, value):
        import json
        self.decision_json = json.dumps(value)

    @property
    def matieres_repechage_dict(self):
        """Retourne le dict des matieres a reprendre parse depuis le JSON."""
        import json
        if not self.matieres_repechage:
            return {}
        try:
            return json.loads(self.matieres_repechage)
        except (json.JSONDecodeError, TypeError):
            return {}

    @matieres_repechage_dict.setter
    def matieres_repechage_dict(self, value):
        import json
        self.matieres_repechage = json.dumps(value)

    def __repr__(self):
        return f'<Deliberation class={self.class_id} T{self.trimester_id} ({self.statut})>'
