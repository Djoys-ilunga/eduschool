from app.models import db
from datetime import datetime


class Timetable(db.Model):
    """Emploi du temps — un creneau par classe/jour/matiere."""
    __tablename__ = 'timetable'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    jour = db.Column(db.String(10), nullable=False)  # lundi, mardi, mercredi, jeudi, vendredi, samedi
    heure_debut = db.Column(db.String(5), nullable=False)  # HH:MM ex: "08:00"
    heure_fin = db.Column(db.String(5), nullable=False)  # HH:MM ex: "09:00"
    salle = db.Column(db.String(50), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    school = db.relationship('School', backref='emploi_du_temps', lazy=True)
    annee_scolaire = db.relationship('AcademicYear', backref='creneaux', lazy=True)
    classe = db.relationship('Class', backref='creneaux', lazy=True)
    subject = db.relationship('Subject', backref='creneaux', lazy=True)
    teacher = db.relationship('User', foreign_keys=[teacher_id], backref='creneaux_enseignant', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('class_id', 'jour', 'heure_debut', name='uq_creneau_classe'),
    )

    @property
    def duree_minutes(self):
        """Duree du creneau en minutes."""
        try:
            h1, m1 = map(int, self.heure_debut.split(':'))
            h2, m2 = map(int, self.heure_fin.split(':'))
            return (h2 * 60 + m2) - (h1 * 60 + m1)
        except (ValueError, AttributeError):
            return 0

    @property
    def creneau_label(self):
        """Label lisible du creneau."""
        return f"{self.heure_debut} - {self.heure_fin}"

    @classmethod
    def jours_semaine(cls):
        return ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi']

    @classmethod
    def creneaux_horaires_defaut(cls):
        """Creneaux horaires standards pour une ecole."""
        return [
            ('08:00', '09:00'),
            ('09:00', '10:00'),
            ('10:00', '10:30'),  # Recreation
            ('10:30', '11:30'),
            ('11:30', '12:30'),
            ('12:30', '13:30'),  # Pause
            ('13:30', '14:30'),
            ('14:30', '15:30'),
            ('15:30', '16:30'),
        ]

    def __repr__(self):
        return f'<Timetable {self.jour} {self.heure_debut} classe={self.class_id}>'
