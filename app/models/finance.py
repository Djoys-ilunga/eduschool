from app.models import db
from datetime import datetime


class FeeType(db.Model):
    """Type de frais scolaire."""
    __tablename__ = 'fee_types'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    nom = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    actif = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    school = db.relationship('School', backref='types_frais', lazy=True)

    def __repr__(self):
        return f'<FeeType {self.nom}>'


class Fee(db.Model):
    """Montant d'un type de frais pour une classe et une annee."""
    __tablename__ = 'fees'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    fee_type_id = db.Column(db.Integer, db.ForeignKey('fee_types.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    montant = db.Column(db.Float, nullable=False, default=0.0)
    devise = db.Column(db.String(10), default='CDF')
    echeance = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    school = db.relationship('School', backref='frais', lazy=True)
    fee_type = db.relationship('FeeType', backref='frais', lazy=True)
    classe = db.relationship('Class', backref='frais', lazy=True)
    annee_scolaire = db.relationship('AcademicYear', backref='frais', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('fee_type_id', 'class_id', 'academic_year_id', name='uq_fee_class_year'),
    )

    def __repr__(self):
        return f'<Fee {self.fee_type.nom if self.fee_type else ""} {self.montant}>'


class SchoolPayment(db.Model):
    """Paiement d'un eleve."""
    __tablename__ = 'school_payments'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    student_profile_id = db.Column(db.Integer, db.ForeignKey('student_profiles.id', ondelete='CASCADE'), nullable=False, index=True)
    fee_id = db.Column(db.Integer, db.ForeignKey('fees.id'), nullable=False)
    montant_paye = db.Column(db.Float, nullable=False)
    date_paiement = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    mode_paiement = db.Column(db.String(30), default='especes')  # especes, virement, mobile_money, cheque
    reference = db.Column(db.String(100), nullable=True)
    recu_par = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    commentaire = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    school = db.relationship('School', backref='paiements', lazy=True)
    student_profile = db.relationship('StudentProfile', backref='paiements', lazy=True)
    fee = db.relationship('Fee', backref='paiements', lazy=True)
    agent = db.relationship('User', foreign_keys=[recu_par], backref='paiements_recus', lazy=True)

    @property
    def montant_du(self):
        return self.fee.montant if self.fee else 0.0

    @property
    def reste_a_payer(self):
        total_du = self.montant_du
        total_paye = db.session.query(db.func.sum(SchoolPayment.montant_paye)).filter(
            SchoolPayment.student_profile_id == self.student_profile_id,
            SchoolPayment.fee_id == self.fee_id,
        ).scalar() or 0.0
        return round(total_du - total_paye, 2)

    @property
    def statut_label(self):
        reste = self.reste_a_payer
        if reste <= 0:
            return 'Paye', 'success'
        du = self.montant_du
        if reste >= du:
            return 'Impaye', 'danger'
        return 'Partiel', 'warning'

    @staticmethod
    def total_paye_eleve_fee(student_profile_id, fee_id):
        return db.session.query(db.func.sum(SchoolPayment.montant_paye)).filter(
            SchoolPayment.student_profile_id == student_profile_id,
            SchoolPayment.fee_id == fee_id,
        ).scalar() or 0.0

    def __repr__(self):
        return f'<Payment {self.montant_paye} eleve={self.student_profile_id}>'
