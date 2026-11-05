from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SelectField, TextAreaField, DateField, SubmitField
from wtforms.validators import DataRequired, Optional, Length, NumberRange


class FeeTypeForm(FlaskForm):
    nom = StringField('Nom', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Enregistrer')


class FeeForm(FlaskForm):
    fee_type_id = SelectField('Type de frais', coerce=lambda x: int(x) if x else None, validators=[DataRequired()])
    class_id = SelectField('Classe', coerce=lambda x: int(x) if x else None, validators=[DataRequired()])
    montant = FloatField('Montant', validators=[DataRequired(), NumberRange(min=0)])
    devise = SelectField('Devise', choices=[('CDF', 'CDF'), ('USD', 'USD')], default='CDF')
    echeance = DateField('Echeance', validators=[Optional()])
    submit = SubmitField('Enregistrer')

    def load_choices(self, school_id, year_id=None):
        from app.models.finance import FeeType
        from app.models.academic import Class
        types = FeeType.query.filter_by(school_id=school_id, actif=True).order_by(FeeType.nom).all()
        self.fee_type_id.choices = [('', '-- Choisir --')] + [(t.id, t.nom) for t in types]
        classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()
        self.class_id.choices = [('', '-- Choisir --')] + [(c.id, c.nom) for c in classes]


class PaymentForm(FlaskForm):
    student_profile_id = SelectField('Eleve', coerce=lambda x: int(x) if x else None, validators=[DataRequired()])
    fee_id = SelectField('Frais', coerce=lambda x: int(x) if x else None, validators=[DataRequired()])
    montant_paye = FloatField('Montant paye', validators=[DataRequired(), NumberRange(min=0)])
    mode_paiement = SelectField('Mode', choices=[
        ('especes', 'Especes'), ('virement', 'Virement'),
        ('mobile_money', 'Mobile Money'), ('cheque', 'Cheque'),
    ], default='especes')
    reference = StringField('Reference', validators=[Optional(), Length(max=100)])
    commentaire = TextAreaField('Commentaire', validators=[Optional(), Length(max=500)])
    date_paiement = DateField('Date', validators=[DataRequired()])
    submit = SubmitField('Enregistrer')

    def load_choices(self, school_id, class_id=None, year_id=None):
        from app.models.student import StudentProfile, StudentEnrollment
        from app.models.finance import Fee
        if class_id:
            enrollments = StudentEnrollment.query.filter_by(class_id=class_id, statut='actif').all()
            self.student_profile_id.choices = [(e.student_profile_id, e.student_profile.user.nom_complet) for e in enrollments]
            fees = Fee.query.filter_by(school_id=school_id, class_id=class_id, academic_year_id=year_id).all()
            self.fee_id.choices = [(f.id, f'{f.fee_type.nom} ({f.montant:,.0f} {f.devise})') for f in fees]
        else:
            self.student_profile_id.choices = [('', '-- Choisir une classe --')]
            self.fee_id.choices = [('', '-- Choisir une classe --')]
