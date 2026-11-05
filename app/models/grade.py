from app.models import db
from datetime import datetime
from sqlalchemy import func


class Grade(db.Model):
    """Note d'un eleve pour une matiere/classe/trimestre."""
    __tablename__ = 'grades'

    id = db.Column(db.Integer, primary_key=True)
    student_profile_id = db.Column(db.Integer, db.ForeignKey('student_profiles.id', ondelete='CASCADE'), nullable=False, index=True)
    class_subject_id = db.Column(db.Integer, db.ForeignKey('class_subjects.id'), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False, index=True)

    type_note = db.Column(db.String(20), nullable=False, default='devoir')  # devoir, interro, examen, tp, oral
    period_id = db.Column(db.Integer, db.ForeignKey('periods.id', ondelete='SET NULL'), nullable=True, index=True)
    trimestre = db.Column(db.Integer, nullable=False, default=1)  # 1, 2, 3 (legacy, peut etre derive du period.trimester.numero)
    valeur = db.Column(db.Float, nullable=False)
    note_max = db.Column(db.Float, nullable=False, default=20.0)
    date_evaluation = db.Column(db.Date, nullable=True)
    commentaire = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    student_profile = db.relationship('StudentProfile', backref='notes', lazy=True)
    class_subject = db.relationship('ClassSubject', backref='notes', lazy=True)
    teacher = db.relationship('User', foreign_keys=[teacher_id], backref='notes_saisies', lazy=True)
    school = db.relationship('School', backref='notes', lazy=True)
    annee_scolaire = db.relationship('AcademicYear', backref='notes', lazy=True)

    @property
    def valeur_sur_vingt(self):
        """Convertit la note sur 20."""
        if self.note_max and self.note_max != 20:
            return round((self.valeur / self.note_max) * 20, 2)
        return round(self.valeur, 2)

    @property
    def student(self):
        return self.student_profile.user if self.student_profile else None

    @property
    def coefficient(self):
        return self.class_subject.coefficient if self.class_subject else 1.0

    @staticmethod
    def moyenne_eleve_matiere_periode(student_profile_id, class_subject_id, period_id):
        """Moyenne d'un eleve pour une matiere sur une periode specifique.
        Ponderation par type: devoir=1, interro=2, examen=3, tp=1, oral=1
        """
        notes = Grade.query.filter_by(
            student_profile_id=student_profile_id,
            class_subject_id=class_subject_id,
            period_id=period_id,
        ).all()
        if not notes:
            return None
        poids_types = {'devoir': 1, 'interro': 2, 'examen': 3, 'tp': 1, 'oral': 1}
        total_pondere = 0.0
        total_poids = 0.0
        for note in notes:
            poids = poids_types.get(note.type_note, 1)
            total_pondere += note.valeur_sur_vingt * poids
            total_poids += poids
        return round(total_pondere / total_poids, 2) if total_poids > 0 else None

    @staticmethod
    def moyenne_eleve_matiere_trimestre(student_profile_id, class_subject_id, trimestre):
        """Moyenne trimestrielle = moyenne ponderee des periodes.
        Chaque periode a un coefficient (ex: interro=1, compo=2, examen=3).
        Si aucune periode n'existe, fallback sur le calcul direct par type_note.
        """
        from app.models.academic import Period
        # Essayer le calcul par periodes
        notes_with_period = Grade.query.filter_by(
            student_profile_id=student_profile_id,
            class_subject_id=class_subject_id,
            trimestre=trimestre,
        ).filter(Grade.period_id.isnot(None)).all()

        if notes_with_period:
            # Grouper par period_id
            period_notes = {}
            for note in notes_with_period:
                period_notes.setdefault(note.period_id, []).append(note)

            total_pondere = 0.0
            total_coef = 0.0
            for pid, pnotes in period_notes.items():
                # Moyenne de la periode
                poids_types = {'devoir': 1, 'interro': 2, 'examen': 3, 'tp': 1, 'oral': 1}
                sp, sw = 0.0, 0.0
                for n in pnotes:
                    w = poids_types.get(n.type_note, 1)
                    sp += n.valeur_sur_vingt * w
                    sw += w
                moy_periode = sp / sw if sw > 0 else 0
                # Coefficient de la periode
                period = db.session.get(Period, pid)
                coef_periode = period.coefficient if period else 1.0
                total_pondere += moy_periode * coef_periode
                total_coef += coef_periode
            return round(total_pondere / total_coef, 2) if total_coef > 0 else None

        # Fallback: calcul direct sans periodes
        notes = Grade.query.filter_by(
            student_profile_id=student_profile_id,
            class_subject_id=class_subject_id,
            trimestre=trimestre,
        ).all()
        if not notes:
            return None
        poids_types = {'devoir': 1, 'interro': 2, 'examen': 3, 'tp': 1, 'oral': 1}
        total_pondere = 0.0
        total_poids = 0.0
        for note in notes:
            poids = poids_types.get(note.type_note, 1)
            total_pondere += note.valeur_sur_vingt * poids
            total_poids += poids
        return round(total_pondere / total_poids, 2) if total_poids > 0 else None

    @staticmethod
    def moyenne_annuelle_eleve(student_profile_id, academic_year_id):
        """Moyenne annuelle = moyenne ponderee des 3 trimestres."""
        from app.models.academic import Trimester
        trimestres = Trimester.query.filter_by(academic_year_id=academic_year_id).order_by(Trimester.numero).all()
        if not trimestres:
            # Fallback: moyenne simple des 3 trimestres
            total, count = 0.0, 0
            for t in [1, 2, 3]:
                mg = Grade.moyenne_generale_trimestre(student_profile_id, t, academic_year_id)
                if mg is not None:
                    total += mg
                    count += 1
            return round(total / count, 2) if count > 0 else None
        total_pondere, total_coef = 0.0, 0.0
        for t in trimestres:
            mg = Grade.moyenne_generale_trimestre(student_profile_id, t.numero, academic_year_id)
            if mg is not None:
                total_pondere += mg * t.coefficient
                total_coef += t.coefficient
        return round(total_pondere / total_coef, 2) if total_coef > 0 else None

    @staticmethod
    def moyenne_generale_trimestre(student_profile_id, trimestre, academic_year_id):
        """Calcule la moyenne generale d'un eleve pour un trimestre.
        Moyenne = somme(moyenne_matiere * coefficient) / somme(coefficients)
        """
        from app.models.academic import ClassSubject
        from app.models.student import StudentEnrollment

        enrollment = StudentEnrollment.query.filter_by(
            student_profile_id=student_profile_id,
            academic_year_id=academic_year_id,
            statut='actif',
        ).first()
        if not enrollment:
            return None

        class_subjects = ClassSubject.query.filter_by(class_id=enrollment.class_id).all()
        if not class_subjects:
            return None

        total_pondere = 0.0
        total_coefficients = 0.0

        for cs in class_subjects:
            moyenne = Grade.moyenne_eleve_matiere_trimestre(student_profile_id, cs.id, trimestre)
            if moyenne is not None:
                total_pondere += moyenne * cs.coefficient
                total_coefficients += cs.coefficient

        return round(total_pondere / total_coefficients, 2) if total_coefficients > 0 else None

    def __repr__(self):
        return f'<Grade {self.valeur}/{self.note_max} eleve={self.student_profile_id}>'
