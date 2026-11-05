from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Regexp
from app.models.user import User
from app.models import db


class LoginForm(FlaskForm):
    email = StringField(' ou Matricule', validators=[
        DataRequired(message="L'email ou le matricule est requis."),
    ])
    password = PasswordField('Mot de passe', validators=[
        DataRequired(message="Le mot de passe est requis.")
    ])
    remember_me = BooleanField('Se souvenir de moi')
    submit = SubmitField('Se connecter')


class ResetPasswordRequestForm(FlaskForm):
    email = StringField('', validators=[
        DataRequired(message="L'email est requis."),
    ])
    submit = SubmitField('Envoyer le lien de reinitialisation')


class ResetPasswordForm(FlaskForm):
    password = PasswordField('Nouveau mot de passe', validators=[
        DataRequired(message="Le mot de passe est requis."),
        Length(min=8, message="Le mot de passe doit contenir au moins 8 caracteres."),
        Regexp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)', message="Le mot de passe doit contenir au moins une minuscule, une majuscule et un chiffre.")
    ])
    password_confirm = PasswordField('Confirmer le mot de passe', validators=[
        DataRequired(message="Veuillez confirmer le mot de passe."),
        EqualTo('password', message="Les mots de passe ne correspondent pas.")
    ])
    submit = SubmitField('Réinitialiser le mot de passe')


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Mot de passe actuel', validators=[
        DataRequired(message="Le mot de passe actuel est requis.")
    ])
    new_password = PasswordField('Nouveau mot de passe', validators=[
        DataRequired(message="Le nouveau mot de passe est requis."),
        Length(min=8, message="Le mot de passe doit contenir au moins 8 caracteres."),
        Regexp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)', message="Le mot de passe doit contenir au moins une minuscule, une majuscule et un chiffre.")
    ])
    confirm_password = PasswordField('Confirmer le nouveau mot de passe', validators=[
        DataRequired(message="Veuillez confirmer le mot de passe."),
        EqualTo('new_password', message="Les mots de passe ne correspondent pas.")
    ])
    submit = SubmitField('Changer le mot de passe')
