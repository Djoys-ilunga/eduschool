from flask_wtf import FlaskForm
from wtforms import StringField, DateField, SelectField, TextAreaField, BooleanField, SubmitField, FileField
from wtforms.validators import DataRequired, Length, Optional, ValidationError
from app.models.user import User
from app.models.student import StudentProfile
from app.models import db


class StudentForm(FlaskForm):
    """Formulaire d'inscription d'un eleve (cree User + StudentProfile + Enrollment)."""

    # --- Infos User ---
    prenom = StringField('Prenom', validators=[
        DataRequired(message="Le prenom est requis."), Length(max=80)
    ])
    nom = StringField('Nom', validators=[
        DataRequired(message="Le nom est requis."), Length(max=80)
    ])
    email = StringField('', validators=[Optional(), Length(max=120)])
    telephone = StringField('Telephone', validators=[Optional(), Length(max=20)])
    password = StringField('Mot de passe', validators=[
        Optional(), Length(min=8, message="Minimum 8 caracteres.")
    ])

    # --- Infos Profil ---
    date_naissance = DateField('Date de naissance', validators=[Optional()])
    lieu_naissance = StringField('Lieu de naissance', validators=[Optional(), Length(max=100)])
    sexe = SelectField('Sexe', choices=[
        ('', '-- Non specifie --'), ('M', 'Masculin'), ('F', 'Feminin')
    ], validators=[Optional()])
    nationalite = StringField('Nationalite', validators=[Optional(), Length(max=50)], default='Congolaise')

    # Contact urgence
    personne_urgence = StringField('Personne a contacter en urgence', validators=[Optional(), Length(max=100)])
    telephone_urgence = StringField('Telephone urgence', validators=[Optional(), Length(max=20)])

    # Photo
    photo_identite = FileField('Photo d\'identite')

    # Documents administratifs
    acte_naissance_file = FileField('Acte de naissance (PDF/Image)')
    certificat_medical_file = FileField('Certificat medical (PDF/Image)')
    bulletin_precedent_file = FileField('Dernier bulletin (PDF/Image)')

    # Sante
    allergies = TextAreaField('Allergies', validators=[Optional(), Length(max=1000)])
    traitements = TextAreaField('Traitements en cours', validators=[Optional(), Length(max=1000)])
    groupe_sanguin = SelectField('Groupe sanguin', choices=[
        ('', '-- Inconnu --'), ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-'),
    ], validators=[Optional()])
    observations_medicales = TextAreaField('Observations medicales', validators=[Optional(), Length(max=1000)])

    # --- Scolarite ---
    matricule_auto = BooleanField('Matricule automatique', default=True)
    matricule = StringField('Matricule', validators=[Optional(), Length(max=30)])
    boursier = BooleanField('Boursier')
    bourse_description = StringField('Description de la bourse', validators=[Optional(), Length(max=200)])

    # --- Parent (optionnel) ---
    create_parent = BooleanField('Creer un compte parent')
    parent_prenom = StringField('Prenom du parent', validators=[Optional(), Length(max=80)])
    parent_nom = StringField('Nom du parent', validators=[Optional(), Length(max=80)])
    parent_email = StringField(' du parent', validators=[Optional(), Length(max=120)])
    parent_telephone = StringField('Telephone du parent', validators=[Optional(), Length(max=20)])

    # --- Inscription ---
    class_id = SelectField('Classe', coerce=lambda x: int(x) if x else None, validators=[
        DataRequired(message="Veuillez choisir une classe.")
    ])
    academic_year_id = SelectField('Annee scolaire', coerce=lambda x: int(x) if x else None, validators=[
        DataRequired(message="Veuillez choisir une annee scolaire.")
    ])

    submit = SubmitField('Inscrire')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def load_choices(self, school_id):
        """Charge les classes et annees scolaires."""
        from app.models.academic import Class, AcademicYear
        years = AcademicYear.query.filter_by(school_id=school_id).filter(
            AcademicYear.statut.in_(['active', 'close'])
        ).order_by(AcademicYear.date_debut.desc()).all()
        self.academic_year_id.choices = [('', '-- Choisir --')] + [
            (y.id, f"{y.nom} ({y.statut})") for y in years
        ]
        classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()
        self.class_id.choices = [('', '-- Choisir --')] + [
            (c.id, f"{c.nom} ({c.niveau or '-'})") for c in classes
        ]

    def validate_email(self, email):
        if not email.data:
            return
        user_id = getattr(self, '_user_id', None)
        existing = db.session.execute(
            db.select(User).filter_by(email=email.data.strip().lower())
        ).scalar_one_or_none()
        if existing and (user_id is None or existing.id != user_id):
            raise ValidationError('Cet email est deja utilise.')

    def validate_matricule(self, matricule):
        if not matricule.data:
            return
        profile_id = getattr(self, '_profile_id', None)
        existing = db.session.execute(
            db.select(StudentProfile).filter_by(matricule=matricule.data.strip().upper())
        ).scalar_one_or_none()
        if existing and (profile_id is None or existing.id != profile_id):
            raise ValidationError('Ce matricule est deja utilise.')

    def set_ids(self, user_id=None, profile_id=None):
        self._user_id = user_id
        self._profile_id = profile_id


class ParentLinkForm(FlaskForm):
    """Formulaire d'association parent-eleve."""

    parent_id = SelectField('Parent', coerce=lambda x: int(x) if x else None, validators=[
        DataRequired(message="Veuillez choisir un parent.")
    ])
    relation = SelectField('Lien de parente', choices=[
        ('pere', 'Pere'),
        ('mere', 'Mere'),
        ('tuteur', 'Tuteur legal'),
        ('oncle', 'Oncle'),
        ('tante', 'Tante'),
        ('frere', 'Frere'),
        ('soeur', 'Soeur'),
        ('grand_parent', 'Grand-parent'),
        ('autre', 'Autre'),
    ], validators=[Optional()])
    est_tuteur_principal = BooleanField('Tuteur principal')
    peut_payer = BooleanField('Autorise a payer', default=True)
    recoit_notifications = BooleanField('Recoit les notifications', default=True)

    submit = SubmitField('Associer')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def load_parents(self, school_id):
        """Charge les utilisateurs ayant le role parent."""
        from app.models.user import User
        parents = User.query.filter_by(school_id=school_id, role='parent', actif=True).order_by(User.nom).all()
        self.parent_id.choices = [('', '-- Choisir un parent --')] + [
            (p.id, f"{p.nom_complet} ({p.email or p.telephone or '-'})") for p in parents
        ]
