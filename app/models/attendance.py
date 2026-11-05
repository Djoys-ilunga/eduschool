from app.models import db
from datetime import datetime


class Attendance(db.Model):
    """Suivi des absences, retards et exclusions d'un eleve."""
    __tablename__ = 'attendances'

    id = db.Column(db.Integer, primary_key=True)
    student_profile_id = db.Column(db.Integer, db.ForeignKey('student_profiles.id', ondelete='CASCADE'), nullable=False, index=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='SET NULL'), nullable=True, index=True)

    date = db.Column(db.Date, nullable=False, index=True)
    type = db.Column(db.String(20), nullable=False, default='absence')  # 'absence', 'retard', 'exclusion'
    justifie = db.Column(db.Boolean, default=False)
    motif = db.Column(db.Text, nullable=True)
    duree_minutes = db.Column(db.Integer, nullable=True)  # Pour les retards (duree en minutes)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    student_profile = db.relationship('StudentProfile', backref='absences', lazy=True)
    school = db.relationship('School', backref='attendances', lazy=True)
    academic_year = db.relationship('AcademicYear', backref='attendances', lazy=True)
    classe = db.relationship('Class', backref='attendances', lazy=True)
    auteur = db.relationship('User', backref='absences_marquees', lazy=True)

    @property
    def type_label(self):
        labels = {
            'absence': 'Absence',
            'retard': 'Retard',
            'exclusion': 'Exclusion',
        }
        return labels.get(self.type, self.type)

    @property
    def statut_label(self):
        if self.justifie:
            return 'Justifié'
        return 'Non justifié'

    def __repr__(self):
        return f'<Attendance student={self.student_profile_id} date={self.date} type={self.type}>'
