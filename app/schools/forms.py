from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FileField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Length, Optional, ValidationError
from app.models.school import School
from app.models.subscription import Plan
from app.models import db
from flask import current_app


class SchoolForm(FlaskForm):
    """Formulaire de création/modification d'une école."""

    # Infos générales
    nom = StringField('Nom de l\'école', validators=[
        DataRequired(message="Le nom de l'école est requis."),
        Length(min=3, max=200, message="Le nom doit contenir entre 3 et 200 caractères.")
    ])
    code = StringField('Code', validators=[
        DataRequired(message="Le code est requis."),
        Length(min=2, max=20, message="Le code doit contenir entre 2 et 20 caractères.")
    ])
    type_ecole = SelectField('Type d\'établissement', choices=[
        ('', '-- Sélectionner --'),
        ('primaire', 'Primaire'),
        ('secondaire', 'Secondaire'),
        ('superieur', 'Supérieur'),
        ('mixte', 'Mixte'),
    ], validators=[Optional()])

    # Adresse
    adresse = StringField('Adresse', validators=[Optional(), Length(max=255)])
    ville = StringField('Ville', validators=[Optional(), Length(max=100)])
    pays = SelectField('Pays', choices=[
        ('CD', 'RDC - Congo'),
        ('CG', 'Congo Brazzaville'),
        ('AO', 'Angola'),
        ('CM', 'Cameroun'),
        ('CI', "Côte d'Ivoire"),
        ('SN', 'Sénégal'),
        ('ML', 'Mali'),
        ('BF', 'Burkina Faso'),
        ('GA', 'Gabon'),
        ('FR', 'France'),
        ('BE', 'Belgique'),
        ('CA', 'Canada'),
        ('US', 'États-Unis'),
    ], default='CD')

    # Contact
    telephone = StringField('Téléphone', validators=[Optional(), Length(max=20)])
    email = StringField('', validators=[Optional(), Length(max=120)])
    site_web = StringField('Site web', validators=[Optional(), Length(max=255)])

    # Configuration
    devise = SelectField('Devise', choices=[
        ('CDF', 'CDF - Franc Congolais'),
        ('USD', 'USD - Dollar US'),
        ('EUR', 'EUR - Euro'),
        ('XOF', 'XOF - Franc CFA'),
        ('XAF', 'XAF - Franc CFA'),
    ], default='CDF')
    langue = SelectField('Langue', choices=[
        ('fr', 'Français'),
        ('en', 'Anglais'),
    ], default='fr')
    fuseau_horaire = SelectField('Fuseau horaire', choices=[
        ('Africa/Kinshasa', 'Africa/Kinshasa (GMT+1)'),
        ('Africa/Lagos', 'Africa/Lagos (GMT+1)'),
        ('Africa/Nairobi', 'Africa/Nairobi (GMT+3)'),
        ('Europe/Paris', 'Europe/Paris'),
        ('America/New_York', 'America/New_York'),
    ], default='Africa/Kinshasa')

    # Abonnement
    plan_id = SelectField('Plan d\'abonnement', coerce=lambda x: int(x) if x else None, validators=[DataRequired(message="Veuillez choisir un plan.")])

    # Logo
    logo = FileField('Logo', validators=[Optional()])

    submit = SubmitField('Enregistrer')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Charge les plans disponibles
        self.plan_id.choices = [('', '-- Choisir un plan --')] + [
            (p.id, f'{p.nom} — {p.prix:,.0f} {p.devise}/mois (max {p.max_eleves} élèves)')
            for p in Plan.query.filter_by(actif=True).order_by(Plan.prix).all()
        ]

    def validate_code(self, code):
        """Vérifie l'unicité du code."""
        # Passe si l'ID de l'école est fourni (modification du même code)
        school_id = getattr(self, '_school_id', None)
        existing = db.session.execute(
            db.select(School).filter_by(code=code.data.strip().upper())
        ).scalar_one_or_none()
        if existing and (school_id is None or existing.id != school_id):
            raise ValidationError('Ce code est déjà utilisé par une autre école.')

    def validate_nom(self, nom):
        """Vérifie l'unicité du nom."""
        school_id = getattr(self, '_school_id', None)
        existing = db.session.execute(
            db.select(School).filter_by(nom=nom.data.strip())
        ).scalar_one_or_none()
        if existing and (school_id is None or existing.id != school_id):
            raise ValidationError('Ce nom est déjà utilisé par une autre école.')

    def set_school_id(self, school_id):
        """Stocke l'ID pour le mode édition."""
        self._school_id = school_id


class SchoolSettingsForm(FlaskForm):
    """Formulaire des paramètres de l'école."""
    devise = SelectField('Devise', choices=[
        ('CDF', 'CDF'), ('USD', 'USD'), ('EUR', 'EUR'), ('XOF', 'XOF'), ('XAF', 'XAF'),
    ])
    langue = SelectField('Langue', choices=[('fr', 'Français'), ('en', 'Anglais')])
    fuseau_horaire = SelectField('Fuseau horaire', choices=[
        ('Africa/Kinshasa', 'Africa/Kinshasa'),
        ('Africa/Lagos', 'Africa/Lagos'),
        ('Africa/Nairobi', 'Africa/Nairobi'),
        ('Europe/Paris', 'Europe/Paris'),
    ])
    submit = SubmitField('Enregistrer les paramètres')
