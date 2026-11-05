from app.models import db
from datetime import datetime


class Announcement(db.Model):
    """Annonce collective ciblee par classe et/ou role."""
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=True)

    titre = db.Column(db.String(200), nullable=False)
    contenu = db.Column(db.Text, nullable=False)
    priorite = db.Column(db.String(20), default='normale')  # normale, importante, urgente
    fichier_joint = db.Column(db.String(500), nullable=True)
    fichier_joint_nom = db.Column(db.String(255), nullable=True)

    # Ciblage — JSON lists
    target_class_ids = db.Column(db.Text, nullable=True)   # JSON: [1, 3, 5] ou null = toutes
    target_roles = db.Column(db.Text, nullable=True)        # JSON: ["teacher", "parent"] ou null = tous
    target_user_ids = db.Column(db.Text, nullable=True)     # JSON: [user_id, ...] ou None = tous

    published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    school = db.relationship('School', backref='annonces', lazy=True)
    author = db.relationship('User', foreign_keys=[author_id], backref='annonces_ecrites', lazy=True)
    annee_scolaire = db.relationship('AcademicYear', backref='annonces', lazy=True)

    @property
    def target_classes(self):
        import json
        if self.target_class_ids:
            try:
                return json.loads(self.target_class_ids)
            except (json.JSONDecodeError, TypeError):
                return []
        return None

    @property
    def target_roles_list(self):
        import json
        if self.target_roles:
            try:
                return json.loads(self.target_roles)
            except (json.JSONDecodeError, TypeError):
                return []
        return None

    @property
    def target_user_ids_list(self):
        import json
        if self.target_user_ids:
            try:
                return json.loads(self.target_user_ids)
            except (json.JSONDecodeError, TypeError):
                return []
        return None

    @property
    def is_global(self):
        return (self.target_classes is None and 
                self.target_roles_list is None and 
                self.target_user_ids_list is None)

    @property
    def priorite_badge(self):
        badges = {'normale': 'secondary', 'importante': 'warning', 'urgente': 'danger'}
        return badges.get(self.priorite, 'secondary')

    @staticmethod
    def for_user(user):
        """Retourne les annonces visibles pour un utilisateur."""
        from app.models.student import StudentProfile, StudentEnrollment, StudentParent
        query = Announcement.query.filter_by(school_id=user.school_id, published=True)

        if user.is_super_admin or user.role == 'school_admin':
            return query.order_by(Announcement.created_at.desc()).all()

        all_annonces = query.order_by(Announcement.created_at.desc()).all()
        visible = []

        for a in all_annonces:
            # Global = visible par tous
            if a.is_global:
                visible.append(a)
                continue

            # Ciblage individuel
            target_users = a.target_user_ids_list
            if target_users:
                if user.id not in target_users:
                    continue  # skip, this user is not targeted

            # Ciblage par role
            target_roles = a.target_roles_list
            if target_roles and user.role not in target_roles:
                continue

            # Ciblage par classe
            target_classes = a.target_classes
            if target_classes:
                if user.role == 'teacher':
                    from app.models.academic import ClassSubject
                    teacher_classes = [cs.class_id for cs in ClassSubject.query.filter_by(teacher_id=user.id).all()]
                    from app.models.academic import Class
                    titulaire_classes = [c.id for c in Class.query.filter_by(titulaire_id=user.id).all()]
                    all_classes = set(teacher_classes + titulaire_classes)
                    if not any(cid in target_classes for cid in all_classes):
                        continue
                elif user.role == 'student':
                    profile = StudentProfile.query.filter_by(user_id=user.id).first()
                    if profile:
                        enrollment = StudentEnrollment.query.filter_by(student_profile_id=profile.id, statut='actif').first()
                        if not enrollment or enrollment.class_id not in target_classes:
                            continue
                elif user.role == 'parent':
                    liens = StudentParent.query.filter_by(parent_id=user.id).all()
                    parent_classes = set()
                    for lien in liens:
                        enrollment = StudentEnrollment.query.filter_by(student_profile_id=lien.student_profile_id, statut='actif').first()
                        if enrollment:
                            parent_classes.add(enrollment.class_id)
                    if not any(cid in target_classes for cid in parent_classes):
                        continue
            visible.append(a)

        return visible

    def __repr__(self):
        return f'<Announcement {self.titre[:30]}>'
