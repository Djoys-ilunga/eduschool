from app.models import db
from app.models.user import Role, Permission, RolePermission
from app.models.subscription import Plan


def init_db():
    """Crée les tables et les données initiales si nécessaire."""
    db.create_all()

    # Migrations manuelles (colonnes ajoutees apres creation initiale)
    _migrate_columns()

    # Créer les rôles par défaut s'ils n'existent pas
    _init_roles()

    # Créer les plans par défaut s'ils n'existent pas
    _init_plans()


def _migrate_columns():
    """Ajoute les colonnes manquantes aux tables existantes."""
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)

    # deliberations.matieres_repechage
    if 'deliberations' in inspector.get_table_names():
        cols = [c['name'] for c in inspector.get_columns('deliberations')]
        if 'matieres_repechage' not in cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE deliberations ADD COLUMN matieres_repechage TEXT'))
                conn.commit()

    # student_enrollments.date_fin (archivage classes)
    if 'student_enrollments' in inspector.get_table_names():
        cols = [c['name'] for c in inspector.get_columns('student_enrollments')]
        if 'date_fin' not in cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE student_enrollments ADD COLUMN date_fin DATE'))
                conn.commit()


def _init_roles():
    """Crée les rôles et permissions de base."""
    from flask import current_app

    roles_defaut = {
        'super_admin': 'Super administrateur de la plateforme — accès à toutes les écoles',
        'school_admin': 'Administrateur d\'une école — gère son établissement',
        'teacher': 'Enseignant — gère ses classes, notes et emploi du temps',
        'parent': 'Parent d\'élève — suit ses enfants',
        'student': 'Élève — consulte ses notes et son emploi du temps',
    }

    for nom_role, description in roles_defaut.items():
        if not Role.query.get(nom_role):
            db.session.add(Role(name=nom_role, description=description))

    # Permissions
    permissions_defaut = {
        # Écoles
        'manage_schools': ('Gérer les écoles', 'ecoles'),
        'view_school': ('Voir son école', 'ecoles'),
        'edit_school': ('Modifier son école', 'ecoles'),

        # Utilisateurs
        'manage_users': ('Gérer tous les utilisateurs', 'utilisateurs'),
        'manage_school_users': ('Gérer les utilisateurs de son école', 'utilisateurs'),
        'view_users': ('Voir les utilisateurs', 'utilisateurs'),

        # Académique
        'manage_classes': ('Gérer les classes', 'academique'),
        'view_classes': ('Voir les classes', 'academique'),
        'manage_subjects': ('Gérer les matières', 'academique'),
        'manage_timetable': ('Gérer les emplois du temps', 'academique'),

        # Notes
        'manage_grades': ('Saisir et gérer les notes', 'notes'),
        'view_grades': ('Voir les notes', 'notes'),
        'manage_bulletins': ('Gérer les bulletins', 'notes'),

        # Finance
        'manage_finance': ('Gérer les finances', 'finance'),
        'view_finance': ('Voir les finances', 'finance'),
        'manage_payments': ('Gérer les paiements', 'finance'),

        # Rapports
        'view_reports': ('Voir les rapports', 'rapports'),
        'export_data': ('Exporter les données', 'rapports'),

        # Paramètres
        'manage_settings': ('Gérer les paramètres', 'parametres'),
        'manage_subscriptions': ('Gérer les abonnements', 'parametres'),

        # Parents / Élèves
        'view_my_children': ('Voir mes enfants', 'portail'),
        'view_my_grades': ('Voir mes notes', 'portail'),
        'make_payment': ('Effectuer un paiement', 'portail'),
    }

    for nom_perm, (description, categorie) in permissions_defaut.items():
        if not Permission.query.get(nom_perm):
            db.session.add(Permission(name=nom_perm, description=description, categorie=categorie))

    db.session.flush()

    # Attribution des permissions aux rôles
    attributions = {
        'super_admin': [
            'manage_schools', 'manage_users', 'manage_subscriptions',
            'view_reports', 'export_data',
        ],
        'school_admin': [
            'view_school', 'edit_school',
            'manage_school_users', 'view_users',
            'manage_classes', 'view_classes', 'manage_subjects', 'manage_timetable',
            'manage_grades', 'view_grades', 'manage_bulletins',
            'manage_finance', 'view_finance', 'manage_payments',
            'view_reports', 'export_data',
            'manage_settings',
        ],
        'teacher': [
            'view_classes', 'manage_timetable',
            'manage_grades', 'view_grades',
        ],
        'parent': [
            'view_my_children', 'view_grades', 'make_payment',
        ],
        'student': [
            'view_my_grades',
        ],
    }

    for nom_role, perms in attributions.items():
        for nom_perm in perms:
            existe = RolePermission.query.filter_by(
                role_name=nom_role, permission_name=nom_perm
            ).first()
            if not existe:
                db.session.add(RolePermission(role_name=nom_role, permission_name=nom_perm))

    db.session.commit()


def _init_plans():
    """Crée les plans d'abonnement par défaut."""
    from flask import current_app

    if Plan.query.count() == 0:
        for plan_data in current_app.config.get('DEFAULT_PLANS', []):
            plan = Plan(
                nom=plan_data['nom'],
                prix=plan_data['prix'],
                devise=plan_data['devise'],
                max_eleves=plan_data['max_eleves'],
                max_enseignants=plan_data['max_enseignants'],
                feature_limitees=plan_data['feature_limitees'],
            )
            db.session.add(plan)
        db.session.commit()
