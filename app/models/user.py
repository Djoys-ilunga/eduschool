from app.models import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # super_admin, school_admin, teacher, parent, student
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=True, index=True)

    nom = db.Column(db.String(80), nullable=False)
    prenom = db.Column(db.String(80), nullable=False)
    telephone = db.Column(db.String(20), nullable=True)
    adresse = db.Column(db.String(255), nullable=True)
    photo = db.Column(db.String(255), nullable=True)

    actif = db.Column(db.Boolean, default=True)
    email_confirme = db.Column(db.Boolean, default=False)
    derniere_connexion = db.Column(db.DateTime, nullable=True)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    school = db.relationship('School', backref='utilisateurs', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"

    @property
    def is_super_admin(self):
        return self.role == 'super_admin'

    @property
    def is_school_admin(self):
        return self.role == 'school_admin'

    def has_permission(self, permission_name):
        """Vérifie si l'utilisateur a une permission spécifique."""
        if self.is_super_admin:
            return True  # Super admin a tous les droits
        role_perms = RolePermission.query.filter_by(role_name=self.role).all()
        return any(rp.permission_name == permission_name for rp in role_perms)

    def __repr__(self):
        return f'<User {self.email} ({self.role})>'


class Role(db.Model):
    __tablename__ = 'roles'

    name = db.Column(db.String(20), primary_key=True)  # super_admin, school_admin, teacher, parent, student
    description = db.Column(db.String(200), nullable=True)

    permissions = db.relationship('RolePermission', backref='role', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Role {self.name}>'


class Permission(db.Model):
    __tablename__ = 'permissions'

    name = db.Column(db.String(50), primary_key=True)
    description = db.Column(db.String(200), nullable=True)
    categorie = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<Permission {self.name}>'


class RolePermission(db.Model):
    __tablename__ = 'role_permissions'

    id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(20), db.ForeignKey('roles.name', ondelete='CASCADE'), nullable=False)
    permission_name = db.Column(db.String(50), db.ForeignKey('permissions.name', ondelete='CASCADE'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('role_name', 'permission_name', name='uq_role_permission'),
    )

    def __repr__(self):
        return f'<RolePermission {self.role_name}:{self.permission_name}>'
