from datetime import datetime, timedelta
from collections import defaultdict
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.dashboard import dashboard_bp
from app.models import db
from app.models.school import School
from app.models.user import User
from app.models.subscription import Subscription, Payment
from app.models.academic import AcademicYear, Class, Subject, ClassSubject
from app.models.student import StudentProfile, StudentParent, StudentEnrollment
from app.models.grade import Grade
from app.models.audit_log import AuditLog
from app.models.attendance import Attendance
from app.models.finance import SchoolPayment
from app.models.announcement import Announcement
from app.models.assignment import Assignment, Submission
from app.auth.decorators import role_required


@dashboard_bp.route('/dashboard')
@login_required
def index():
    """Redirige vers le dashboard correspondant au role de l'utilisateur."""
    role_routes = {
        'super_admin': 'dashboard.super_admin',
        'school_admin': 'dashboard.school_admin',
        'teacher': 'dashboard.teacher',
        'parent': 'dashboard.parent',
        'student': 'dashboard.student',
    }
    endpoint = role_routes.get(current_user.role, 'auth.login')
    return redirect(url_for(endpoint))


@dashboard_bp.route('/dashboard/super-admin')
@login_required
def super_admin():
    """Dashboard Super Admin — vue globale de la plateforme."""
    if current_user.role != 'super_admin':
        flash('Acces non autorise.', 'danger')
        return redirect(url_for('dashboard.index'))

    stats = {
        'total_ecoles': School.query.count(),
        'ecoles_actives': School.query.filter_by(statut='active').count(),
        'total_eleves': User.query.filter_by(role='student', actif=True).count(),
        'total_enseignants': User.query.filter_by(role='teacher', actif=True).count(),
        'total_admins': User.query.filter_by(role='school_admin', actif=True).count(),
        'total_parents': User.query.filter_by(role='parent', actif=True).count(),
        'total_classes': Class.query.filter_by(actif=True).count(),
        'total_matieres': Subject.query.filter_by(actif=True).count(),
        'abonnements_actifs': Subscription.query.filter_by(statut='active').count(),
    }

    ecoles_recentes = School.query.order_by(School.created_at.desc()).limit(5).all()

    # Ecoles par mois (derniers 12 mois)
    now = datetime.utcnow()
    mois_labels = []
    ecoles_counts = []
    for i in range(11, -1, -1):
        debut_mois = now.replace(day=1) - timedelta(days=i * 30)
        fin_mois = (debut_mois.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        count = School.query.filter(
            School.created_at >= debut_mois.replace(day=1),
            School.created_at <= fin_mois
        ).count()
        mois_labels.append(debut_mois.strftime('%b %Y'))
        ecoles_counts.append(count)

    # Repartition par role
    repartition_roles = {
        'labels': ['Admins école', 'Enseignants', 'Parents', 'Élèves'],
        'data': [
            stats['total_admins'],
            stats['total_enseignants'],
            stats['total_parents'],
            stats['total_eleves'],
        ]
    }

    return render_template(
        'dashboard/super_admin.html',
        stats=stats,
        ecoles_recentes=ecoles_recentes,
        ecoles_labels=mois_labels,
        ecoles_counts=ecoles_counts,
        repartition_roles=repartition_roles,
        breadcrumbs=[("Tableau de Bord", None)]
    )


@dashboard_bp.route('/dashboard/school-admin')
@login_required
def school_admin():
    """Dashboard Administrateur d'ecole."""
    if current_user.role not in ('super_admin', 'school_admin'):
        flash('Acces non autorise.', 'danger')
        return redirect(url_for('dashboard.index'))

    school = current_user.school
    if not school and current_user.role == 'school_admin':
        flash('Aucune ecole associee a votre compte.', 'warning')
        return redirect(url_for('auth.logout'))

    school_id = school.id if school else None

    # Annee scolaire active
    from app.academic.routes import _get_active_year_id
    year_id = _get_active_year_id(school_id)
    annee_active = AcademicYear.query.get(year_id) if year_id else None

    stats = {
        'total_eleves': User.query.filter_by(school_id=school_id, role='student', actif=True).count(),
        'total_enseignants': User.query.filter_by(school_id=school_id, role='teacher', actif=True).count(),
        'total_classes': Class.query.filter_by(school_id=school_id, actif=True).count(),
        'total_matieres': Subject.query.filter_by(school_id=school_id, actif=True).count(),
        'total_parents': User.query.filter_by(school_id=school_id, role='parent', actif=True).count(),
    }

    classes_recentes = Class.query.filter_by(school_id=school_id, actif=True).order_by(
        Class.created_at.desc()
    ).limit(5).all()

    # Effectifs par classe et repartition sexe
    classes_effectifs = []
    labels_classes = []
    effectifs_data = []
    nb_garcons = 0
    nb_filles = 0

    for c in Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all():
        eleves_ids = [e.student_profile_id for e in StudentEnrollment.query.filter_by(
            class_id=c.id, statut='actif'
        ).all()]
        nb = len(eleves_ids)
        labels_classes.append(c.nom)
        effectifs_data.append(nb)

        # Sexe
        for sp in StudentProfile.query.filter(StudentProfile.id.in_(eleves_ids)).all():
            if sp.sexe == 'M':
                nb_garcons += 1
            elif sp.sexe == 'F':
                nb_filles += 1

    repartition_sexe = {
        'labels': ['Garçons', 'Filles', 'Non spécifié'],
        'data': [nb_garcons, nb_filles, stats['total_eleves'] - nb_garcons - nb_filles]
    }

    return render_template(
        'dashboard/school_admin.html',
        school=school,
        stats=stats,
        annee_active=annee_active,
        classes_recentes=classes_recentes,
        classes_labels=labels_classes,
        classes_effectifs=effectifs_data,
        repartition_sexe=repartition_sexe,
        breadcrumbs=[("Tableau de Bord", None)]
    )


@dashboard_bp.route('/dashboard/teacher')
@login_required
def teacher():
    """Dashboard Enseignant."""
    if current_user.role != 'teacher':
        flash('Acces non autorise.', 'danger')
        return redirect(url_for('dashboard.index'))

    # Classes ou le prof enseigne
    matieres_enseignees = ClassSubject.query.filter_by(
        teacher_id=current_user.id
    ).order_by(ClassSubject.id).all()

    # Classes dont il est titulaire (annee active)
    from app.academic.routes import _get_active_year_id
    active_year_id = _get_active_year_id(current_user.school_id)
    classes_titulaire = Class.query.filter_by(
        titulaire_id=current_user.id, actif=True,
        academic_year_id=active_year_id
    ).all()

    # Moyennes par matiere/classe
    moyennes_labels = []
    moyennes_data = []
    for cs in matieres_enseignees:
        label = f"{cs.subject.nom} ({cs.classe.nom})"
        notes = Grade.query.filter_by(class_subject_id=cs.id).all()
        if notes:
            moyenne = round(sum(n.valeur_sur_vingt for n in notes) / len(notes), 2)
        else:
            moyenne = 0
        moyennes_labels.append(label)
        moyennes_data.append(moyenne)

    return render_template(
        'dashboard/teacher.html',
        matieres_enseignees=matieres_enseignees,
        classes_titulaire=classes_titulaire,
        moyennes_labels=moyennes_labels,
        moyennes_data=moyennes_data,
        breadcrumbs=[("Tableau de Bord", None)]
    )


@dashboard_bp.route('/dashboard/parent')
@login_required
def parent():
    """Dashboard Parent."""
    if current_user.role != 'parent':
        flash('Acces non autorise.', 'danger')
        return redirect(url_for('dashboard.index'))

    # Recuperer les enfants du parent
    liens = StudentParent.query.filter_by(parent_id=current_user.id).all()

    enfants_data = []
    for lien in liens:
        profile = lien.student_profile
        if not profile:
            continue
        enrollment = StudentEnrollment.query.filter_by(
            student_profile_id=profile.id, statut='actif'
        ).first()
        enfants_data.append({
            'profile': profile,
            'lien': lien,
            'enrollment': enrollment,
        })

    return render_template('dashboard/parent.html',
                          enfants_data=enfants_data, nb_enfants=len(enfants_data),
                          breadcrumbs=[("Tableau de Bord", None)])


@dashboard_bp.route('/dashboard/student')
@login_required
def student():
    """Dashboard Eleve — miroir du dashboard parent."""
    if current_user.role != 'student':
        flash('Acces non autorise.', 'danger')
        return redirect(url_for('dashboard.index'))

    profile = StudentProfile.query.filter_by(user_id=current_user.id).first()
    enrollment = StudentEnrollment.query.filter_by(
        student_profile_id=profile.id if profile else None, statut='actif'
    ).first()

    return render_template('dashboard/student.html',
                          profile=profile,
                          enrollment=enrollment,
                          breadcrumbs=[("Tableau de Bord", None)])


@dashboard_bp.route('/dashboard/history')
@login_required
@role_required('super_admin', 'school_admin')
def history():
    """Historique global — agrege les 50 dernieres actions."""
    entries = []

    school_id = current_user.school_id

    # --- AuditLog (reserve aux super_admin et school_admin) ---
    if current_user.role != 'teacher':
        audit_q = AuditLog.query
        if school_id and current_user.role != 'super_admin':
            # Filtrer par l'ecole via le user lie
            audit_q = audit_q.join(User, AuditLog.user_id == User.id).filter(User.school_id == school_id)
        audits = audit_q.order_by(AuditLog.created_at.desc()).limit(50).all()
        for a in audits:
            author_name = f"{a.user.nom} {a.user.prenom}" if a.user else "Système"
            entries.append({
                'type': 'audit',
                'description': a.action,
                'detail': a.details or '',
                'date': a.created_at,
                'auteur': author_name,
            })

    # --- Grade ---
    grade_q = Grade.query
    if school_id:
        grade_q = grade_q.filter_by(school_id=school_id)
    grades = grade_q.order_by(Grade.created_at.desc()).limit(50).all()
    for g in grades:
        teacher_name = f"{g.teacher.nom} {g.teacher.prenom}" if g.teacher else "—"
        student_name = ''
        if g.student_profile and g.student_profile.user:
            student_name = f"{g.student_profile.user.nom} {g.student_profile.user.prenom}"
        subject_name = g.class_subject.subject.nom if g.class_subject and g.class_subject.subject else '?'
        entries.append({
            'type': 'grade',
            'description': f"Note {g.valeur}/{g.note_max} ({g.type_note})",
            'detail': f"{student_name} — {subject_name}",
            'date': g.created_at,
            'auteur': teacher_name,
        })

    # --- Attendance ---
    att_q = Attendance.query
    if school_id:
        att_q = att_q.filter_by(school_id=school_id)
    attendances = att_q.order_by(Attendance.created_at.desc()).limit(50).all()
    for a in attendances:
        author_name = f"{a.auteur.nom} {a.auteur.prenom}" if a.auteur else "—"
        student_name = ''
        if a.student_profile and a.student_profile.user:
            student_name = f"{a.student_profile.user.nom} {a.student_profile.user.prenom}"
        entries.append({
            'type': 'attendance',
            'description': f"{a.type_label}",
            'detail': f"{student_name} — {a.date.strftime('%d/%m/%Y')}" + (f" ({a.motif})" if a.motif else ''),
            'date': a.created_at,
            'auteur': author_name,
        })

    # --- SchoolPayment ---
    pay_q = SchoolPayment.query
    if school_id:
        pay_q = pay_q.filter_by(school_id=school_id)
    payments = pay_q.order_by(SchoolPayment.created_at.desc()).limit(50).all()
    from app.models.finance import Fee, FeeType
    for p in payments:
        agent_name = f"{p.agent.nom} {p.agent.prenom}" if p.agent else "—"
        student_name = ''
        if p.student_profile and p.student_profile.user:
            student_name = f"{p.student_profile.user.nom} {p.student_profile.user.prenom}"
        fee_label = ''
        if p.fee and p.fee.fee_type:
            fee_label = p.fee.fee_type.nom
        entries.append({
            'type': 'payment',
            'description': f"Paiement {p.montant_paye:,.0f} CDF",
            'detail': f"{student_name} — {fee_label}" + (f" (ref: {p.reference})" if p.reference else ''),
            'date': p.created_at,
            'auteur': agent_name,
        })

    # --- Announcement (Annonce) ---
    ann_q = Announcement.query
    if school_id:
        ann_q = ann_q.filter_by(school_id=school_id)
    annonces = ann_q.order_by(Announcement.created_at.desc()).limit(50).all()
    for a in annonces:
        author_name = f"{a.author.nom} {a.author.prenom}" if a.author else "—"
        entries.append({
            'type': 'announcement',
            'description': f"Annonce: {a.titre}",
            'detail': a.contenu[:150] + ('...' if len(a.contenu) > 150 else ''),
            'date': a.created_at,
            'auteur': author_name,
        })

    # Trier par date decroissante, garder les 50 plus recentes
    entries.sort(key=lambda e: e['date'], reverse=True)
    entries = entries[:50]

    return render_template(
        'dashboard/history.html',
        entries=entries,
        now=datetime.utcnow(),
        breadcrumbs=[("Historique", None)]
    )


@dashboard_bp.route('/dashboard/ma-fiche')
@login_required
def ma_fiche():
    """Redirige l'eleve vers sa propre fiche."""
    if current_user.role != 'student':
        flash('Acces non autorise.', 'danger')
        return redirect(url_for('dashboard.index'))
    profile = StudentProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        flash('Profil etudiant introuvable.', 'warning')
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('students.detail', profile_id=profile.id))


@dashboard_bp.route('/dashboard/mes-enfants')
@login_required
def mes_enfants():
    """Liste detaillee des enfants pour un parent."""
    if current_user.role != 'parent':
        flash('Acces non autorise.', 'danger')
        return redirect(url_for('dashboard.index'))

    from app.models.student import StudentProfile, StudentEnrollment, StudentParent
    from app.models.grade import Grade

    liens = StudentParent.query.filter_by(parent_id=current_user.id).all()
    enfants = []
    for lien in liens:
        profile = lien.student_profile
        if not profile:
            continue
        enrollment = StudentEnrollment.query.filter_by(student_profile_id=profile.id, statut='actif').first()
        timetable_count = 0
        latest_grade = None
        if enrollment:
            from app.models.timetable import Timetable
            timetable_count = Timetable.query.filter_by(
                class_id=enrollment.class_id
            ).count()
            latest_grade = Grade.query.filter_by(
                student_profile_id=profile.id
            ).order_by(Grade.created_at.desc()).first()
        enfants.append({
            'profile': profile,
            'lien': lien,
            'enrollment': enrollment,
            'timetable_count': timetable_count,
            'latest_grade': latest_grade,
        })

    return render_template('dashboard/mes_enfants.html', enfants=enfants, nb_enfants=len(enfants),
                          breadcrumbs=[("Tableau de Bord", url_for('dashboard.parent')), ("Mes Enfants", None)])


@dashboard_bp.route('/devoirs-enfants')
@login_required
def devoirs_enfants():
    """Resultats des devoirs des enfants pour les parents."""
    if current_user.role != 'parent':
        flash('Acces non autorise.', 'danger')
        return redirect(url_for('dashboard.index'))

    from app.models.student import StudentProfile, StudentEnrollment, StudentParent

    notes_only = request.args.get('notes_only', '0') == '1'

    liens = StudentParent.query.filter_by(parent_id=current_user.id).all()
    enfants_devoirs = []

    for lien in liens:
        profile = lien.student_profile
        if not profile:
            continue
        enrollment = StudentEnrollment.query.filter_by(
            student_profile_id=profile.id, statut='actif'
        ).first()
        if not enrollment:
            continue

        # Devoirs de la classe — filtre annee active
        assignments = Assignment.query.filter_by(
            class_id=enrollment.class_id, statut='actif', academic_year_id=enrollment.academic_year_id
        ).order_by(Assignment.date_limite.desc()).all()

        devoirs_data = []
        nb_notes = 0
        somme_notes = 0.0
        nb_notes_somme = 0
        for a in assignments:
            sub = Submission.query.filter_by(
                assignment_id=a.id, student_id=profile.user_id
            ).first()
            note_val = sub.note if sub else None

            # Filtre notes uniquement
            if notes_only and note_val is None:
                continue

            if note_val is not None:
                nb_notes += 1
                somme_notes += float(note_val)
                nb_notes_somme += 1

            devoirs_data.append({
                'assignment': a,
                'submission': sub,
                'rendu': sub is not None,
                'note': note_val,
                'feedback': sub.feedback if sub else None,
                'en_retard': sub.est_en_retard if sub else False,
            })

        moyenne = round(somme_notes / nb_notes_somme, 2) if nb_notes_somme > 0 else None

        enfants_devoirs.append({
            'enfant': profile.user,
            'profile': profile,
            'classe': enrollment.classe,
            'devoirs': devoirs_data,
            'nb_notes': nb_notes,
            'moyenne': moyenne,
        })

    return render_template('dashboard/devoirs_enfants.html',
                          enfants_devoirs=enfants_devoirs,
                          notes_only=notes_only,
                          breadcrumbs=[("Tableau de Bord", url_for('dashboard.parent')),
                                      ("Devoirs enfants", None)])
