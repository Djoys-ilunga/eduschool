from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SelectMultipleField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, Optional
import json


class AnnouncementForm(FlaskForm):
    titre = StringField('Titre', validators=[DataRequired(), Length(max=200)])
    contenu = TextAreaField('Message', validators=[DataRequired(), Length(max=5000)])
    priorite = SelectField('Priorite', choices=[
        ('normale', 'Normale'), ('importante', 'Importante'), ('urgente', 'Urgente'),
    ], default='normale')
    target_roles = SelectMultipleField('Roles cibles', choices=[], validators=[Optional()])
    target_users = SelectMultipleField('Utilisateurs cibles', choices=[], validators=[Optional()])
    published = BooleanField('Publier maintenant', default=True)
    submit = SubmitField('Publier')

    def load_choices(self, school_id):
        from app.models.academic import Class
        from app.models.user import User
        classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()
        self.target_classes = [(c.id, c.nom) for c in classes]

        # Charger les roles
        self.target_roles.choices = [
            ('teacher', 'Enseignants'), ('parent', 'Parents'),
            ('student', 'Eleves'), ('school_admin', 'Administrateurs'),
        ]

        # Charger les utilisateurs par role
        users = User.query.filter_by(school_id=school_id, actif=True).order_by(User.role, User.nom, User.prenom).all()
        self.target_users.choices = [
            (u.id, f"{u.nom_complet} ({u.role})")
            for u in users
        ]
