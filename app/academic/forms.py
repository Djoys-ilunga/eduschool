from flask_wtf import FlaskForm
from wtforms import StringField, DateField, SelectField, TextAreaField, SubmitField, HiddenField, IntegerField
from wtforms.validators import DataRequired, Length, Optional, ValidationError, NumberRange, Regexp
from app.models.academic import AcademicYear, Class, Subject, ClassSubject
from app.models import db


class AcademicYearForm(FlaskForm):
    """Formulaire de creation/modification d'une annee scolaire."""

    nom = StringField('Nom de l\'annee scolaire', validators=[
        DataRequired(message="Le nom est requis."),
        Length(min=4, max=50, message="Entre 4 et 50 caracteres.")
    ])
    date_debut = DateField('Date de debut', validators=[
        DataRequired(message="La date de debut est requise.")
    ])
    date_fin = DateField('Date de fin', validators=[
        DataRequired(message="La date de fin est requise.")
    ])
    statut = SelectField('Statut', choices=[
        ('active', 'Active'),
        ('close', 'Close (plus d\'inscriptions)'),
        ('archivee', 'Archivee'),
    ], default='active')

    # Trimestres
    t1_debut = DateField('1er Trimestre — Debut', validators=[Optional()])
    t1_fin = DateField('1er Trimestre — Fin', validators=[Optional()])
    t2_debut = DateField('2eme Trimestre — Debut', validators=[Optional()])
    t2_fin = DateField('2eme Trimestre — Fin', validators=[Optional()])
    t3_debut = DateField('3eme Trimestre — Debut', validators=[Optional()])
    t3_fin = DateField('3eme Trimestre — Fin', validators=[Optional()])

    submit = SubmitField('Enregistrer')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def validate_nom(self, nom):
        year_id = getattr(self, '_year_id', None)
        school_id = getattr(self, '_school_id', None)
        if school_id:
            existing = db.session.execute(
                db.select(AcademicYear).filter_by(school_id=school_id, nom=nom.data.strip())
            ).scalar_one_or_none()
            if existing and (year_id is None or existing.id != year_id):
                raise ValidationError('Une annee scolaire avec ce nom existe deja.')

    def set_ids(self, year_id=None, school_id=None):
        self._year_id = year_id
        self._school_id = school_id


class ClassForm(FlaskForm):
    """Formulaire de creation/modification d'une classe."""

    nom = StringField('Nom de la classe', validators=[
        DataRequired(message="Le nom est requis."),
        Length(min=2, max=100, message="Entre 2 et 100 caracteres.")
    ])
    niveau = StringField('Niveau', validators=[
        Optional(), Length(max=50),
        Regexp(r'^[a-zA-Z0-9\s\-]+$', message='Caracteres invalides. Utilisez lettres, chiffres, espaces et tirets.')
    ],
                         description="Niveau d'etude (obligatoire pour la passation)",
                         render_kw={"list": "niveau-suggestions", "placeholder": "Ex: 6eme, 5eme, Terminale, 2eme annee..."})
    section = StringField('Section', validators=[Optional(), Length(max=50)],
                          description="Ex: Scientifique, Litteraire, Technique")
    capacite_max = IntegerField('Capacite maximale', validators=[
        Optional(), NumberRange(min=1, message="Au moins 1.")
    ])
    salle = StringField('Salle', validators=[Optional(), Length(max=50)])
    academic_year_id = SelectField('Annee scolaire', coerce=lambda x: int(x) if x else None, validators=[
        DataRequired(message="Veuillez choisir une annee scolaire.")
    ])
    titulaire_id = SelectField('Titulaire (professeur principal)', coerce=lambda x: int(x) if x else None,
                                validators=[Optional()])

    submit = SubmitField('Enregistrer')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def load_choices(self, school_id):
        """Charge les annees scolaires et enseignants d'une ecole."""
        from app.models.user import User
        years = AcademicYear.query.filter_by(school_id=school_id).order_by(AcademicYear.date_debut.desc()).all()
        self.academic_year_id.choices = [('', '-- Choisir --')] + [
            (y.id, f"{y.nom} ({y.statut})") for y in years
        ]
        teachers = User.query.filter_by(school_id=school_id, role='teacher', actif=True).order_by(User.nom).all()
        self.titulaire_id.choices = [('', '-- Aucun --')] + [
            (t.id, t.nom_complet) for t in teachers
        ]

    def validate_nom(self, nom):
        class_id = getattr(self, '_class_id', None)
        year_id = self.academic_year_id.data
        if year_id:
            existing = db.session.execute(
                db.select(Class).filter_by(academic_year_id=year_id, nom=nom.data.strip())
            ).scalar_one_or_none()
            if existing and (class_id is None or existing.id != class_id):
                raise ValidationError('Une classe avec ce nom existe deja dans cette annee scolaire.')

    def set_class_id(self, class_id):
        self._class_id = class_id


class SubjectForm(FlaskForm):
    """Formulaire de creation/modification d'une matiere."""

    nom = StringField('Nom de la matiere', validators=[
        DataRequired(message="Le nom est requis."),
        Length(min=2, max=150, message="Entre 2 et 150 caracteres.")
    ])
    code = StringField('Code', validators=[Optional(), Length(max=20)],
                       description="Ex: MATH, FRAN, PHYS")
    description = TextAreaField('Description', validators=[Optional(), Length(max=1000)])
    categorie = SelectField('Categorie', choices=[
        ('', '-- Aucune --'),
        ('scientifique', 'Scientifique'),
        ('litteraire', 'Litteraire'),
        ('technique', 'Technique'),
        ('langue', 'Langue'),
        ('sport', 'Sport'),
        ('artistique', 'Artistique'),
        ('autre', 'Autre'),
    ], validators=[Optional()])
    actif = SelectField('Statut', choices=[
        (True, 'Actif'),
        (False, 'Inactif'),
    ], coerce=lambda x: x == 'True' if isinstance(x, str) else bool(x), default=True)

    submit = SubmitField('Enregistrer')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def validate_nom(self, nom):
        subject_id = getattr(self, '_subject_id', None)
        school_id = getattr(self, '_school_id', None)
        if school_id:
            existing = db.session.execute(
                db.select(Subject).filter_by(school_id=school_id, nom=nom.data.strip())
            ).scalar_one_or_none()
            if existing and (subject_id is None or existing.id != subject_id):
                raise ValidationError('Une matiere avec ce nom existe deja.')

    def set_ids(self, subject_id=None, school_id=None):
        self._subject_id = subject_id
        self._school_id = school_id


class ClassSubjectForm(FlaskForm):
    """Formulaire d'association Classe-Matiere."""

    subject_id = SelectField('Matiere', coerce=lambda x: int(x) if x else None, validators=[
        DataRequired(message="Veuillez choisir une matiere.")
    ])
    teacher_id = SelectField('Enseignant', coerce=lambda x: int(x) if x else None, validators=[Optional()])
    coefficient = StringField('Coefficient', validators=[
        DataRequired(message="Le coefficient est requis.")
    ], default='1')
    heures_par_semaine = StringField('Heures/semaine', validators=[Optional()])
    groupe = StringField('Groupe', validators=[Optional(), Length(max=50)],
                         description="Ex: Groupe 1, Optionnel")

    submit = SubmitField('Ajouter')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def load_choices(self, school_id, exclude_ids=None):
        """Charge les matieres et enseignants disponibles."""
        from app.models.user import User
        query = Subject.query.filter_by(school_id=school_id, actif=True).order_by(Subject.nom)
        self.subject_id.choices = [('', '-- Choisir une matiere --')] + [
            (s.id, f"{s.nom} ({s.code or '-'})")
            for s in query.all()
            if not exclude_ids or s.id not in exclude_ids
        ]
        teachers = User.query.filter_by(school_id=school_id, role='teacher', actif=True).order_by(User.nom).all()
        self.teacher_id.choices = [('', '-- Aucun --')] + [
            (t.id, t.nom_complet) for t in teachers
        ]

    def validate_coefficient(self, field):
        try:
            val = float(field.data.replace(',', '.'))
            if val <= 0:
                raise ValidationError('Le coefficient doit etre superieur a 0.')
            field.data = val
        except (ValueError, TypeError):
            raise ValidationError('Veuillez entrer un nombre valide.')

    def validate_heures_par_semaine(self, field):
        if field.data:
            try:
                field.data = float(field.data.replace(',', '.'))
            except (ValueError, TypeError):
                raise ValidationError('Veuillez entrer un nombre valide.')


class ClassSubjectEditForm(FlaskForm):
    """Formulaire d'edition d'une association."""

    teacher_id = SelectField('Enseignant', coerce=lambda x: int(x) if x else None, validators=[Optional()])
    coefficient = StringField('Coefficient', validators=[DataRequired()], default='1')
    heures_par_semaine = StringField('Heures/semaine', validators=[Optional()])
    groupe = StringField('Groupe', validators=[Optional(), Length(max=50)])
    submit = SubmitField('Mettre a jour')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def load_teachers(self, school_id):
        from app.models.user import User
        teachers = User.query.filter_by(school_id=school_id, role='teacher', actif=True).order_by(User.nom).all()
        self.teacher_id.choices = [('', '-- Aucun --')] + [
            (t.id, t.nom_complet) for t in teachers
        ]

    def validate_coefficient(self, field):
        try:
            val = float(field.data.replace(',', '.'))
            if val <= 0:
                raise ValidationError('Le coefficient doit etre superieur a 0.')
            field.data = val
        except (ValueError, TypeError):
            raise ValidationError('Veuillez entrer un nombre valide.')

    def validate_heures_par_semaine(self, field):
        if field.data:
            try:
                field.data = float(field.data.replace(',', '.'))
            except (ValueError, TypeError):
                raise ValidationError('Veuillez entrer un nombre valide.')


from app.models.timetable import Timetable


class TimetableForm(FlaskForm):
    class_id = SelectField('Classe', coerce=lambda x: int(x) if x else None, validators=[DataRequired()])
    jour = SelectField('Jour', choices=[
        ('lundi', 'Lundi'), ('mardi', 'Mardi'), ('mercredi', 'Mercredi'),
        ('jeudi', 'Jeudi'), ('vendredi', 'Vendredi'), ('samedi', 'Samedi'),
    ], validators=[DataRequired()])
    heure_debut = SelectField('Heure debut', validators=[DataRequired()])
    heure_fin = SelectField('Heure fin', validators=[DataRequired()])
    subject_id = SelectField('Matiere', coerce=lambda x: int(x) if x else None, validators=[DataRequired()])
    teacher_id = SelectField('Enseignant', coerce=lambda x: int(x) if x else None, validators=[Optional()])
    salle = StringField('Salle', validators=[Optional(), Length(max=50)])
    submit = SubmitField('Ajouter')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def load_choices(self, school_id):
        from app.models.user import User
        from app.models.academic import Class, Subject
        classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()
        self.class_id.choices = [('', '-- Choisir --')] + [(c.id, c.nom) for c in classes]
        subjects = Subject.query.filter_by(school_id=school_id, actif=True).order_by(Subject.nom).all()
        self.subject_id.choices = [('', '-- Choisir --')] + [(s.id, s.nom) for s in subjects]
        teachers = User.query.filter_by(school_id=school_id, role='teacher', actif=True).order_by(User.nom).all()
        self.teacher_id.choices = [('', '-- Aucun --')] + [(t.id, t.nom_complet) for t in teachers]
        creneaux = Timetable.creneaux_horaires_defaut()
        self.heure_debut.choices = [(c[0], c[0]) for c in creneaux]
        self.heure_fin.choices = [(c[1], c[1]) for c in creneaux]


class GradeForm(FlaskForm):
    student_profile_id = SelectField('Eleve', coerce=lambda x: int(x) if x else None, validators=[DataRequired()])
    class_subject_id = SelectField('Matiere', coerce=lambda x: int(x) if x else None, validators=[DataRequired()])
    type_note = SelectField('Type', choices=[
        ('devoir', 'Devoir'), ('interro', 'Interrogation'),
        ('examen', 'Examen'), ('tp', 'TP'), ('oral', 'Oral'),
    ], validators=[DataRequired()])
    period_id = SelectField('Trimestre / Periode', coerce=lambda x: int(x) if x else None, validators=[DataRequired(message='Selectionnez un trimestre et une periode.')])
    valeur = StringField('Note', validators=[DataRequired()])
    note_max = StringField('Sur', default='20')
    date_evaluation = DateField('Date', validators=[Optional()])
    commentaire = TextAreaField('Commentaire', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Enregistrer')

    def load_choices(self, school_id, class_id=None, trimestre=None):
        from app.models.academic import ClassSubject, Period, Trimester
        from app.models.student import StudentEnrollment, StudentProfile
        from app.models.user import User
        if class_id:
            css = ClassSubject.query.filter_by(class_id=class_id).order_by(ClassSubject.id).all()
            self.class_subject_id.choices = [(cs.id, f'{cs.subject.nom} (coef {cs.coefficient})') for cs in css]
            enrollments = StudentEnrollment.query.filter_by(class_id=class_id, statut='actif')\
                .join(StudentProfile).join(User).order_by(User.nom, User.prenom).all()
            self.student_profile_id.choices = [(e.student_profile_id, e.student_profile.user.nom_complet) for e in enrollments]
        else:
            self.class_subject_id.choices = [('', '-- Choisir une classe d abord --')]
            self.student_profile_id.choices = [('', '-- Choisir une classe d abord --')]
        # Periodes filtrables par trimestre (cascade)
        q = Period.query.join(Trimester).filter(Trimester.school_id == school_id)
        if trimestre:
            q = q.filter(Trimester.numero == trimestre)
        periods = q.order_by(Trimester.numero, Period.numero).all()
        self.period_id.choices = [('', '-- Choisir --')] + [
            (p.id, f'{p.trimestre.nom} — {p.nom}  (coef {p.coefficient})')
            for p in periods
        ]

    def validate_valeur(self, field):
        try:
            field.data = float(field.data.replace(',', '.'))
            if field.data < 0:
                raise ValidationError('La note ne peut pas etre negative.')
            if field.data > 20:
                raise ValidationError('La note ne peut pas depasser 20.')
        except (ValueError, TypeError):
            raise ValidationError('Veuillez entrer un nombre valide.')

    def validate_note_max(self, field):
        try:
            val = float(field.data.replace(',', '.')) if field.data else 0
            if val <= 0:
                raise ValidationError('La note maximale doit etre superieure a 0.')
            field.data = val
        except (ValueError, TypeError):
            raise ValidationError('Veuillez entrer un nombre valide pour la note maximale.')

    def validate_date_evaluation(self, field):
        from datetime import date
        if field.data and field.data > date.today():
            raise ValidationError('La date d\'evaluation ne peut pas etre dans le futur.')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        # Au moins un de student_profile_id ou period_id doit etre selectionne
        if not self.student_profile_id.data and not self.period_id.data:
            self.student_profile_id.errors.append('Selectionnez un eleve ou une periode.')
            self.period_id.errors.append('Selectionnez un eleve ou une periode.')
            return False
        return True
