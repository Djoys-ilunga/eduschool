"""Devoirs & Soumissions — Modèles de données."""
from app.models import db
from datetime import datetime


class Assignment(db.Model):
    """Devoir / Travail assigné par un enseignant à une classe."""
    __tablename__ = 'assignments'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=True, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    titre = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    date_limite = db.Column(db.DateTime, nullable=False)
    fichier_joint = db.Column(db.String(500), nullable=True)
    fichier_joint_nom = db.Column(db.String(255), nullable=True)
    authorise_retard = db.Column(db.Boolean, default=False)
    max_points = db.Column(db.Float, nullable=True)
    statut = db.Column(db.String(20), nullable=False, default='actif')  # actif, termine, archive

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    school = db.relationship('School', backref='assignments', lazy=True)
    classe = db.relationship('Class', backref='assignments', lazy=True)
    academic_year = db.relationship('AcademicYear', backref='assignments', lazy=True)
    subject = db.relationship('Subject', backref='assignments', lazy=True)
    teacher = db.relationship('User', foreign_keys=[teacher_id], backref='assignments_given', lazy=True)
    submissions = db.relationship('Submission', backref='assignment', lazy=True,
                                  cascade='all, delete-orphan',
                                  order_by='Submission.date_soumission.desc()')

    @property
    def nombre_soumissions(self):
        return len(self.submissions)

    @property
    def nombre_eleves_classe(self):
        from app.models.student import StudentEnrollment
        return StudentEnrollment.query.filter_by(
            class_id=self.class_id, statut='actif'
        ).count()

    @property
    def nombre_non_rendus(self):
        return self.nombre_eleves_classe - self.nombre_soumissions

    @property
    def est_en_retard(self):
        return datetime.utcnow() > self.date_limite

    def __repr__(self):
        return f'<Assignment {self.id} "{self.titre}" class={self.class_id}>'


class Submission(db.Model):
    """Soumission d'un devoir par un élève."""
    __tablename__ = 'submissions'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id', ondelete='CASCADE'),
                              nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    fichier = db.Column(db.String(500), nullable=True)
    fichier_nom = db.Column(db.String(255), nullable=True)
    commentaire = db.Column(db.Text, nullable=True)
    note = db.Column(db.Float, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    statut = db.Column(db.String(20), nullable=False, default='soumis')  # soumis, note, revision

    date_soumission = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    student = db.relationship('User', foreign_keys=[student_id], backref='submissions', lazy=True)

    @property
    def est_en_retard(self):
        return self.date_soumission > self.assignment.date_limite

    @staticmethod
    def allowed_file(filename):
        ALLOWED = {
            'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp',
            'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg',
            'zip', 'rar', '7z',
            'txt', 'csv', 'py', 'c', 'cpp', 'java', 'js', 'html', 'css', 'sql', 'json', 'xml',
            'mp3', 'mp4', 'wav', 'ogg',
        }
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED

    def __repr__(self):
        return f'<Submission {self.id} student={self.student_id} assignment={self.assignment_id}>'
