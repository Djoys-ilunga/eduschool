from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, Optional, ValidationError
from app.models.user import User
from app.models.school import School
from app.models import db
from flask_login import current_user


class UserForm(FlaskForm):
    """Formulaire de création/modification d'un utilisateur."""

    prenom = StringField('Prénom', validators=[
        DataRequired(message="Le prénom est requis."),
        Length(min=1, max=80)
    ])
    nom = StringField('Nom', validators=[
        DataRequired(message="Le nom est requis."),
        Length(min=1, max=80)
    ])
    email = StringField('Email', validators=[
        DataRequired(message="L'email est requis."),
        Length(max=120)
    ])
    telephone = StringField('Téléphone', validators=[Optional(), Length(max=20)])

    role = SelectField('Rôle', choices=[
        ('school_admin', 'Administrateur d\'école'),
        ('teacher', 'Enseignant'),
        ('parent', 'Parent'),
        ('student', 'Élève'),
    ], validators=[DataRequired(message="Veuillez choisir un rôle.")])

    school_id = SelectField('École', coerce=lambda x: int(x) if x else None, validators=[Optional()])

    password = PasswordField('Mot de passe', validators=[
        Optional(),
        Length(min=8, message="Le mot de passe doit contenir au moins 8 caractères.")
    ])
    password_confirm = PasswordField('Confirmer le mot de passe', validators=[
        EqualTo('password', message="Les mots de passe ne correspondent pas.")
    ])

    actif = BooleanField('Compte actif', default=True)

    submit = SubmitField('Enregistrer')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Charge les écoles disponibles
        schools = School.query.order_by(School.nom).all()
        self.school_id.choices = [('', '-- Aucune école (Super Admin uniquement) --')] + [
            (s.id, f'{s.nom} ({s.code})') for s in schools
        ]

        # Rôles disponibles selon le rôle de l'utilisateur connecté
        if current_user.is_authenticated:
            if current_user.is_super_admin:
                self.role.choices.insert(0, ('super_admin', 'Super Administrateur'))
            if current_user.role == 'school_admin':
                # Un admin d'école ne peut créer que des rôles subalternes
                self.role.choices = [
                    ('teacher', 'Enseignant'),
                    ('parent', 'Parent'),
                    ('student', 'Élève'),
                ]
                # Fixe l'école
                self.school_id.choices = [(current_user.school_id, current_user.school.nom)]
                self.school_id.data = current_user.school_id

    def validate_email(self, email):
        user_id = getattr(self, '_user_id', None)
        existing = db.session.execute(
            db.select(User).filter_by(email=email.data.strip().lower())
        ).scalar_one_or_none()
        if existing and (user_id is None or existing.id != user_id):
            raise ValidationError('Cet email est déjà utilisé.')

    def set_user_id(self, user_id):
        self._user_id = user_id


class UserEditForm(UserForm):
    """Formulaire d'édition — mot de passe optionnel."""
    password = PasswordField('Nouveau mot de passe (laisser vide pour ne pas changer)', validators=[
        Optional(),
        Length(min=8, message="Le mot de passe doit contenir au moins 8 caractères.")
    ])


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Mot de passe actuel', validators=[
        DataRequired(message="Veuillez entrer votre mot de passe actuel.")
    ])
    new_password = PasswordField('Nouveau mot de passe', validators=[
        DataRequired(message="Veuillez entrer un nouveau mot de passe."),
        Length(min=8, message="8 caractères minimum.")
    ])
    confirm_password = PasswordField('Confirmer', validators=[
        DataRequired(),
        EqualTo('new_password', message="Les mots de passe ne correspondent pas.")
    ])
    submit = SubmitField('Changer le mot de passe')
