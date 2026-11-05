import os

import io

from flask import render_template, redirect, url_for, flash, request, current_app, send_file

from flask_login import current_user, login_required

from werkzeug.utils import secure_filename

from datetime import datetime

from app.students import students_bp

from app.students.forms import StudentForm

from app.models import db
from app.utils.helpers import _generate_random_password, _get_school_id

from app.models.user import User

from app.models.school import School

from app.models.academic import Class, AcademicYear
from app.academic.routes import _get_active_year_id

from app.models.student import StudentProfile, StudentEnrollment, StudentParent, StudentBulletinAccess

from app.models.finance import SchoolPayment

from app.auth.decorators import role_required, school_admin_required

from app.utils.pdf_attestation import generate_attestation_pdf

from flask_wtf.csrf import generate_csrf, validate_csrf
from app.models.assignment import Assignment, Submission
from app.utils.audit import log_action








@students_bp.route('/')

@role_required('super_admin', 'school_admin')

def list():

    """Liste des eleves avec filtres."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    page = request.args.get('page', 1, type=int)

    q = request.args.get('q', request.args.get('search', '')).strip()

    class_id = request.args.get('class_id', None, type=int)

    year_id = request.args.get('year_id', None, type=int)

    statut_filter = request.args.get('statut', 'all')  # 'all', 'nouveau', 'continuite'


    # Requete via les profils d'eleves de cette ecole

    query = StudentProfile.query.join(User).filter(

        User.school_id == school_id,

        User.role == 'student',

        User.actif == True

    )



    if q:

        query = query.filter(

            db.or_(

                User.nom.ilike(f'%{q}%'),

                User.prenom.ilike(f'%{q}%'),

                StudentProfile.matricule.ilike(f'%{q}%'),

            )

        )



    if year_id or class_id:

        from sqlalchemy.orm import aliased
        se_alias = aliased(StudentEnrollment)
        query = query.join(se_alias, StudentProfile.id == se_alias.student_profile_id)
        if year_id:
            query = query.filter(se_alias.academic_year_id == year_id)
        if class_id:
            query = query.filter(se_alias.class_id == class_id)


    # Filtre nouveau / continuite
    if statut_filter != 'all' and year_id:
        current_year = db.session.get(AcademicYear, year_id)
        if current_year:
            prev_year = AcademicYear.query.filter(
                AcademicYear.school_id == school_id,
                AcademicYear.date_debut < current_year.date_debut
            ).order_by(AcademicYear.date_debut.desc()).first()
            
            if prev_year:
                prev_enr = StudentEnrollment.query.filter_by(academic_year_id=prev_year.id).all()
                prev_student_ids = {e.student_profile_id for e in prev_enr}
                
                if statut_filter == 'nouveau':
                    # Élèves dans l'année courante mais PAS dans la précédente
                    if prev_student_ids:
                        query = query.filter(~StudentProfile.id.in_(prev_student_ids))
                elif statut_filter == 'continuite':
                    # Élèves présents dans les 2 années
                    if prev_student_ids:
                        query = query.filter(StudentProfile.id.in_(prev_student_ids))
                    else:
                        query = query.filter(StudentProfile.id == -1)  # aucun

    query = query.order_by(User.nom, User.prenom)

    pagination = query.paginate(page=page, per_page=current_app.config['ITEMS_PER_PAGE'], error_out=False)

    students = pagination.items



    years = AcademicYear.query.filter_by(school_id=school_id).order_by(AcademicYear.date_debut.desc()).all()
    class_query = Class.query.filter_by(school_id=school_id, actif=True)
    if year_id:
        class_query = class_query.filter_by(academic_year_id=year_id)
    classes = class_query.order_by(Class.nom).all()



    return render_template('students/list.html',

                          students=students, pagination=pagination,

                          q=q, class_id=class_id, year_id=year_id,

                          years=years, classes=classes, school_id=school_id,
                          statut_filter=statut_filter,

                          breadcrumbs=[("Élèves", None)])





@students_bp.route('/create', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def create():

    """Inscription d'un nouvel eleve."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    form = StudentForm()

    form.load_choices(school_id)



    if form.validate_on_submit():

        # 1. Creer User

        email = form.email.data.strip().lower() if form.email.data else f"eleve_{datetime.utcnow().timestamp()}@placeholder.local"

        password = form.password.data or _generate_random_password()



        user = User(

            prenom=form.prenom.data.strip(),

            nom=form.nom.data.strip(),

            email=email,

            telephone=form.telephone.data.strip() if form.telephone.data else None,

            role='student',

            school_id=school_id,

            actif=True,

        )

        user.set_password(password)

        db.session.add(user)

        db.session.flush()



        # 2. Creer StudentProfile

        # Auto-generer le matricule si demande

        matricule_val = form.matricule.data.strip().upper() if form.matricule.data else None

        if form.matricule_auto.data and not matricule_val:

            count = StudentProfile.query.join(User).filter(

                User.school_id == school_id, User.role == 'student'

            ).count()

            matricule_val = f'ET{school_id}-{count + 1:04d}'



        profile = StudentProfile(

            user_id=user.id,

            date_naissance=form.date_naissance.data,

            lieu_naissance=form.lieu_naissance.data.strip() if form.lieu_naissance.data else None,

            sexe=form.sexe.data or None,

            nationalite=form.nationalite.data.strip() if form.nationalite.data else None,

            personne_urgence=form.personne_urgence.data.strip() if form.personne_urgence.data else None,

            telephone_urgence=form.telephone_urgence.data.strip() if form.telephone_urgence.data else None,

            allergies=form.allergies.data.strip() if form.allergies.data else None,

            traitements=form.traitements.data.strip() if form.traitements.data else None,

            groupe_sanguin=form.groupe_sanguin.data or None,

            observations_medicales=form.observations_medicales.data.strip() if form.observations_medicales.data else None,

            matricule=matricule_val,

            boursier=form.boursier.data,

            bourse_description=form.bourse_description.data.strip() if form.bourse_description.data else None,

            date_inscription=datetime.utcnow().date(),

        )

        db.session.add(profile)

        db.session.flush()



        # 3. Creer l'inscription (StudentEnrollment)

        enrollment = StudentEnrollment(

            student_profile_id=profile.id,

            class_id=form.class_id.data,

            academic_year_id=form.academic_year_id.data,

            school_id=school_id,

            date_inscription=datetime.utcnow().date(),

            statut='actif',

        )

        db.session.add(enrollment)



        # 4. Creer le compte parent si demande

        if form.create_parent.data:

            parent_email = form.parent_email.data.strip().lower() if form.parent_email.data else None

            parent = None

            if parent_email:

                parent = User.query.filter_by(email=parent_email).first()

            if not parent:

                parent_user_email = parent_email or f"parent_{datetime.utcnow().timestamp()}@placeholder.local"

                parent = User(

                    prenom=form.parent_prenom.data.strip(),

                    nom=form.parent_nom.data.strip(),

                    email=parent_user_email,

                    telephone=form.parent_telephone.data.strip() if form.telephone.data else None,

                    role='parent',

                    school_id=school_id,

                    actif=True,

                )

                parent.set_password(_generate_random_password())

                db.session.add(parent)

                db.session.flush()



            # Creer le lien parent-eleve

            existing_link = StudentParent.query.filter_by(

                parent_id=parent.id, student_profile_id=profile.id

            ).first()

            if not existing_link:

                sp = StudentParent(

                    parent_id=parent.id,

                    student_profile_id=profile.id,

                    relation='tuteur',

                    est_tuteur_principal=True,

                    peut_payer=True,

                    recoit_notifications=True,

                )

                db.session.add(sp)



        # 5. Gestion des documents administratifs

        doc_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'archives', str(profile.id))

        os.makedirs(doc_dir, exist_ok=True)



        # Photo d'identite

        photo = request.files.get('photo_identite')

        if photo and photo.filename:

            filename = secure_filename(photo.filename)

            ext = filename.rsplit('.', 1)[-1].lower()

            if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):

                photo_path = os.path.join(doc_dir, f'photo_identite.{ext}')

                photo.save(photo_path)

                profile.photo_identite = f'/uploads/archives/{profile.id}/photo_identite.{ext}'



        # Documents : acte de naissance, certificat medical, bulletin precedent

        for field_name, attr_name in [

            ('acte_naissance_file', 'acte_naissance'),

            ('certificat_medical_file', 'certificat_medical'),

            ('bulletin_precedent_file', 'bulletin_precedent'),

        ]:

            doc = request.files.get(field_name)

            if doc and doc.filename:

                filename = secure_filename(doc.filename)

                ext = filename.rsplit('.', 1)[-1].lower()

                if ext in ('jpg', 'jpeg', 'png', 'pdf', 'gif', 'webp'):

                    unique_name = f'{attr_name}.{ext}'

                    doc_path = os.path.join(doc_dir, unique_name)

                    doc.save(doc_path)

                    setattr(profile, attr_name, f'/uploads/archives/{profile.id}/{attr_name}.{ext}')



        db.session.commit()



        flash(f'Eleve "{user.nom_complet}" inscrit avec succes.', 'success')

        return redirect(url_for('students.detail', profile_id=profile.id))



    return render_template('students/create.html', form=form, student=None, school_id=school_id,

                          breadcrumbs=[("Élèves", url_for('students.list', school_id=school_id)), ("Inscription", None)])





@students_bp.route('/<int:profile_id>')

@role_required('super_admin', 'school_admin', 'teacher', 'parent', 'student')

def detail(profile_id):

    """Fiche detaillee d'un eleve."""

    profile = db.session.get(StudentProfile, profile_id)

    if not profile:

        flash('Eleve introuvable.', 'danger')

        return redirect(url_for('students.list', school_id=_get_school_id()))


    # Eleve: ne peut voir que sa propre fiche
    if current_user.role == 'student':
        own_profile = StudentProfile.query.filter_by(user_id=current_user.id).first()
        if not own_profile or own_profile.id != profile_id:
            flash('Acces refuse.', 'danger')
            return redirect(url_for('dashboard.index'))

    # Parent: verifier le lien

    if current_user.role == 'parent':

        link = StudentParent.query.filter_by(parent_id=current_user.id, student_profile_id=profile_id).first()

        if not link:

            flash('Acces refuse.', 'danger')

            return redirect(url_for('dashboard.index'))



    user = profile.user

    enrollment = StudentEnrollment.query.filter_by(

        student_profile_id=profile_id, statut='actif'

    ).order_by(StudentEnrollment.created_at.desc()).first()



    # Parents disponibles pour association

    from app.models.user import User

    parents_disponibles = User.query.filter_by(

        school_id=user.school_id, role='parent', actif=True

    ).order_by(User.nom, User.prenom).all()



    # Annees et classes pour le modal "changer de classe"

    years = AcademicYear.query.filter_by(school_id=user.school_id).filter(

        AcademicYear.statut.in_(['active', 'close'])

    ).order_by(AcademicYear.date_debut.desc()).all()

    classes = Class.query.filter_by(school_id=user.school_id, actif=True).order_by(Class.nom).all()



    return render_template('students/detail.html',

                          profile=profile, user=user, enrollment=enrollment,

                          parents_disponibles=parents_disponibles,

                          years=years, classes=classes,

                          csrf_token=generate_csrf(),

                          breadcrumbs=[("Élèves", url_for('students.list', school_id=user.school_id)), ("Fiche Élève", None)])





@students_bp.route('/<int:profile_id>/edit', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def edit(profile_id):

    """Modification du dossier eleve."""

    profile = db.session.get(StudentProfile, profile_id)

    if not profile:

        flash('Eleve introuvable.', 'danger')

        return redirect(url_for('students.list', school_id=_get_school_id()))



    user = profile.user

    school_id = user.school_id



    form = StudentForm(obj=user)

    form.set_ids(user_id=user.id, profile_id=profile_id)

    form.load_choices(school_id)



    if form.validate_on_submit():

        user.prenom = form.prenom.data.strip()

        user.nom = form.nom.data.strip()

        user.telephone = form.telephone.data.strip() if form.telephone.data else None

        if form.email.data:

            user.email = form.email.data.strip().lower()

        if form.password.data:

            user.set_password(form.password.data)



        profile.date_naissance = form.date_naissance.data

        profile.lieu_naissance = form.lieu_naissance.data.strip() if form.lieu_naissance.data else None

        profile.sexe = form.sexe.data or None

        profile.nationalite = form.nationalite.data.strip() if form.nationalite.data else None

        profile.personne_urgence = form.personne_urgence.data.strip() if form.personne_urgence.data else None

        profile.telephone_urgence = form.telephone_urgence.data.strip() if form.telephone_urgence.data else None

        profile.allergies = form.allergies.data.strip() if form.allergies.data else None

        profile.traitements = form.traitements.data.strip() if form.traitements.data else None

        profile.groupe_sanguin = form.groupe_sanguin.data or None

        profile.observations_medicales = form.observations_medicales.data.strip() if form.observations_medicales.data else None

        profile.matricule = form.matricule.data.strip().upper() if form.matricule.data else None

        profile.boursier = form.boursier.data

        profile.bourse_description = form.bourse_description.data.strip() if form.bourse_description.data else None



        # Gestion upload photo d'identite

        photo = request.files.get('photo_identite')

        if photo and photo.filename:

            filename = secure_filename(photo.filename)

            ext = filename.rsplit('.', 1)[-1].lower()

            if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):

                unique_name = f'photo_identite.{ext}'

                photo_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'archives', str(profile_id))

                os.makedirs(photo_dir, exist_ok=True)


                photo_path = os.path.join(photo_dir, unique_name)

                photo.save(photo_path)

                # Supprimer l'ancienne photo si remplacement

                if profile.photo_identite:

                    old_path = os.path.join(current_app.static_folder, profile.photo_identite.lstrip('/'))

                    if os.path.exists(old_path):

                        os.remove(old_path)

                profile.photo_identite = f'/uploads/archives/{profile_id}/photo_identite.{ext}'

        # Gestion upload documents administratifs
        doc_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'archives', str(profile_id))
        os.makedirs(doc_dir, exist_ok=True)
        for field_name, attr_name in [
            ('acte_naissance_file', 'acte_naissance'),
            ('certificat_medical_file', 'certificat_medical'),
            ('bulletin_precedent_file', 'bulletin_precedent'),
        ]:
            doc = request.files.get(field_name)
            if doc and doc.filename:
                filename = secure_filename(doc.filename)
                ext = filename.rsplit('.', 1)[-1].lower()
                if ext in ('jpg', 'jpeg', 'png', 'pdf', 'gif', 'webp'):
                    unique_name = f'{attr_name}.{ext}'
                    doc_path = os.path.join(doc_dir, unique_name)
                    doc.save(doc_path)
                    # Supprimer l'ancien document si remplacement
                    old_doc = getattr(profile, attr_name)
                    if old_doc:
                        old_path = os.path.join(current_app.static_folder, old_doc.lstrip('/'))
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    setattr(profile, attr_name, f'/uploads/archives/{profile_id}/{attr_name}.{ext}')

        db.session.commit()

        flash(f'Dossier de "{user.nom_complet}" mis a jour.', 'success')

        return redirect(url_for('students.detail', profile_id=profile_id))



    if not form.is_submitted():

        form.date_naissance.data = profile.date_naissance

        form.lieu_naissance.data = profile.lieu_naissance

        form.sexe.data = profile.sexe

        form.nationalite.data = profile.nationalite

        form.personne_urgence.data = profile.personne_urgence

        form.telephone_urgence.data = profile.telephone_urgence

        form.allergies.data = profile.allergies

        form.traitements.data = profile.traitements

        form.groupe_sanguin.data = profile.groupe_sanguin

        form.observations_medicales.data = profile.observations_medicales

        form.matricule.data = profile.matricule

        form.boursier.data = profile.boursier

        form.bourse_description.data = profile.bourse_description

        enrollment = StudentEnrollment.query.filter_by(

            student_profile_id=profile_id, statut='actif'

        ).first()

        if enrollment:

            form.academic_year_id.data = enrollment.academic_year_id

            form.class_id.data = enrollment.class_id



    return render_template('students/create.html', form=form, student=user, school_id=school_id,

                          breadcrumbs=[("Élèves", url_for('students.list', school_id=school_id)), ("Modification", None)])





@students_bp.route('/<int:profile_id>/attestation')

@role_required('super_admin', 'school_admin', 'parent', 'student')

def attestation(profile_id):

    """Génère et télécharge l'attestation de scolarité en PDF."""

    profile = db.session.get(StudentProfile, profile_id)

    if not profile:

        flash('Élève introuvable.', 'danger')

        return redirect(url_for('dashboard.index'))

    # Eleve: ne peut generer que sa propre attestation
    if current_user.role == 'student':
        own_profile = StudentProfile.query.filter_by(user_id=current_user.id).first()
        if not own_profile or own_profile.id != profile_id:
            flash('Acces refuse.', 'danger')
            return redirect(url_for('dashboard.index'))


    # Parent: verifier le lien

    if current_user.role == 'parent':

        link = StudentParent.query.filter_by(parent_id=current_user.id, student_profile_id=profile_id).first()

        if not link:

            flash('Acces refuse.', 'danger')

            return redirect(url_for('dashboard.index'))



    user = profile.user

    school = School.query.get(user.school_id)

    if not school:

        flash('École introuvable.', 'danger')

        return redirect(url_for('students.detail', profile_id=profile_id))



    enrollment = StudentEnrollment.query.filter_by(

        student_profile_id=profile_id, statut='actif'

    ).order_by(StudentEnrollment.created_at.desc()).first()



    pdf_bytes = generate_attestation_pdf(profile, school, enrollment)



    return send_file(

        io.BytesIO(pdf_bytes),

        mimetype='application/pdf',

        as_attachment=True,

        download_name=f'attestation_{user.nom}_{user.prenom}.pdf'

    )





@students_bp.route('/<int:profile_id>/delete', methods=['POST'])

@role_required('super_admin', 'school_admin')

def delete(profile_id):

    """Suppression d'un eleve."""


    profile = db.session.get(StudentProfile, profile_id)

    if not profile:

        flash('Eleve introuvable.', 'danger')

        return redirect(url_for('students.list', school_id=_get_school_id()))



    user = profile.user

    nom = user.nom_complet

    uid = user.id

    try:

        # Nettoyer toutes les FK qui bloquent la suppression

        SchoolPayment.query.filter_by(student_profile_id=profile_id).delete()

        # Supprimer bulletin_access (NOT NULL constraint)
        StudentBulletinAccess.query.filter_by(student_profile_id=profile_id).delete()

        from app.models.announcement import Announcement

        Announcement.query.filter_by(author_id=uid).delete()

        Class.query.filter_by(titulaire_id=uid).update({'titulaire_id': None})

        from app.models.academic import ClassSubject

        ClassSubject.query.filter_by(teacher_id=uid).update({'teacher_id': None})

        from app.models.timetable import Timetable

        Timetable.query.filter_by(teacher_id=uid).update({'teacher_id': None})

        from app.models.attendance import Attendance

        Attendance.query.filter_by(created_by=uid).delete()

        from app.models.grade import Grade

        Grade.query.filter_by(teacher_id=uid).update({'teacher_id': None})

        from app.models.assignment import Assignment, Submission

        assignments = Assignment.query.filter_by(teacher_id=uid).all()

        for a in assignments:

            Submission.query.filter_by(assignment_id=a.id).delete()

        Assignment.query.filter_by(teacher_id=uid).delete()

        Submission.query.filter_by(student_id=uid).delete()

        SchoolPayment.query.filter_by(recu_par=uid).update({'recu_par': None})

        # Supprimer les inscriptions et liens parent (NOT NULL constraints)
        StudentEnrollment.query.filter_by(student_profile_id=profile_id).delete()
        StudentParent.query.filter_by(student_profile_id=profile_id).delete()

        # Supprimer le profile avec SQL brut pour éviter le cascade ORM
        from sqlalchemy import text
        db.session.execute(text("DELETE FROM student_profiles WHERE id = :pid"), {"pid": profile_id})
        db.session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
        db.session.commit()

    except Exception as e:

        db.session.rollback()

        flash(f'Erreur lors de la suppression: {str(e)}', 'danger')

        return redirect(url_for('students.detail', profile_id=profile_id))

    flash(f'Eleve "{nom}" supprime.', 'info')

    return redirect(url_for('students.list', school_id=user.school_id))


@students_bp.route('/<int:profile_id>/toggle-bulletin', methods=['POST'])
@role_required('super_admin', 'school_admin')
def toggle_bulletin_access(profile_id):
    """Active/desactive l'acces parent aux bulletins."""

    profile = db.session.get(StudentProfile, profile_id)
    if not profile:
        flash('Eleve introuvable.', 'danger')
        return redirect(url_for('students.list', school_id=_get_school_id()))
    access = StudentBulletinAccess.query.filter_by(student_profile_id=profile_id).first()
    if access:
        access.parent_access = not access.parent_access
    else:
        access = StudentBulletinAccess(student_profile_id=profile_id, parent_access=False)
        db.session.add(access)
    db.session.commit()
    status = 'active' if access.parent_access else 'desactive'
    flash(f'Acces bulletin parent {status} pour {profile.user.nom_complet}.', 'success')
    return redirect(url_for('students.detail', profile_id=profile_id))





# ============================================================

# ASSOCIATION PARENTS

# ============================================================



@students_bp.route('/<int:profile_id>/parents/add', methods=['POST'])

@role_required('super_admin', 'school_admin')

def add_parent(profile_id):

    """Associer un parent a un eleve."""

    from app.students.forms import ParentLinkForm

    profile = db.session.get(StudentProfile, profile_id)

    if not profile:

        flash('Eleve introuvable.', 'danger')

        return redirect(url_for('students.list', school_id=_get_school_id()))



    school_id = profile.user.school_id

    form = ParentLinkForm()

    form.load_parents(school_id)



    if form.validate_on_submit():

        existing = StudentParent.query.filter_by(

            parent_id=form.parent_id.data,

            student_profile_id=profile_id

        ).first()

        if existing:

            flash('Ce parent est deja associe a cet eleve.', 'warning')

        else:

            sp = StudentParent(

                parent_id=form.parent_id.data,

                student_profile_id=profile_id,

                relation=form.relation.data or None,

                est_tuteur_principal=form.est_tuteur_principal.data,

                peut_payer=form.peut_payer.data,

                recoit_notifications=form.recoit_notifications.data,

            )

            db.session.add(sp)

            db.session.commit()

            flash('Parent associe avec succes.', 'success')



    return redirect(url_for('students.detail', profile_id=profile_id))





@students_bp.route('/<int:profile_id>/change-class', methods=['POST'])

@role_required('super_admin', 'school_admin')

def change_class(profile_id):

    """Changer la classe d'un eleve (desactive l'inscription active, cree la nouvelle)."""

    validate_csrf(request.form.get('csrf_token', ''))

    profile = db.session.get(StudentProfile, profile_id)

    if not profile:

        flash('Eleve introuvable.', 'danger')

        return redirect(url_for('students.list', school_id=_get_school_id()))



    school_id = profile.user.school_id

    new_class_id = request.form.get('class_id', type=int)

    new_year_id = request.form.get('academic_year_id', type=int)



    if not new_class_id or not new_year_id:

        flash('Classe et annee scolaire requises.', 'warning')

        return redirect(url_for('students.detail', profile_id=profile_id))



    # Desactiver les inscriptions actives

    active_enrollments = StudentEnrollment.query.filter_by(

        student_profile_id=profile_id, statut='actif'

    ).all()

    for e in active_enrollments:

        e.statut = 'termine'



    # Verifier si une inscription existe deja pour cette annee (reactivation)

    enrollment = StudentEnrollment.query.filter_by(

        student_profile_id=profile_id, academic_year_id=new_year_id

    ).first()

    if enrollment:

        enrollment.class_id = new_class_id

        enrollment.school_id = school_id

        enrollment.statut = 'actif'

        enrollment.date_inscription = datetime.utcnow().date()

    else:

        enrollment = StudentEnrollment(

            student_profile_id=profile_id,

            class_id=new_class_id,

            academic_year_id=new_year_id,

            school_id=school_id,

            date_inscription=datetime.utcnow().date(),

            statut='actif',

        )

        db.session.add(enrollment)

    db.session.commit()



    flash('Classe changee avec succes.', 'success')

    return redirect(url_for('students.detail', profile_id=profile_id))





@students_bp.route('/<int:profile_id>/parents/<int:sp_id>/remove', methods=['POST'])

@role_required('super_admin', 'school_admin')

def remove_parent(profile_id, sp_id):

    """Retirer le lien parent-eleve."""


    sp = db.session.get(StudentParent, sp_id)

    if sp:

        db.session.delete(sp)

        db.session.commit()

        flash('Parent dissocie de l eleve.', 'info')

    return redirect(url_for('students.detail', profile_id=profile_id))


# ============================================================
# DEVOIRS — Cote eleve
# ============================================================

@login_required

@students_bp.route('/devoirs')
def devoirs_eleve():
    if current_user.role != 'student':
        flash('Acces reserve aux eleves.', 'danger')
        return redirect(url_for('dashboard.index'))

    profile = StudentProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        flash('Profil eleve introuvable.', 'danger')
        return redirect(url_for('dashboard.index'))

    enrollment = StudentEnrollment.query.filter_by(
        student_profile_id=profile.id, statut='actif'
    ).first()
    if not enrollment:
        flash('Vous n\'etes inscrit a aucune classe.', 'warning')
        return redirect(url_for('dashboard.index'))

    school_id = enrollment.school_id
    class_id = enrollment.class_id
    year_id = enrollment.academic_year_id
    page = request.args.get('page', 1, type=int)

    query = Assignment.query.filter_by(
        school_id=school_id, class_id=class_id, statut='actif', academic_year_id=year_id
    ).order_by(Assignment.date_limite.asc())

    pagination = query.paginate(page=page, per_page=10, error_out=False)
    assignments = pagination.items

    soumis_ids = set()
    for a in assignments:
        for s in a.submissions:
            if s.student_id == current_user.id:
                soumis_ids.add(a.id)

    return render_template('academic/devoirs/eleve_list.html',
                          assignments=assignments, pagination=pagination,
                          soumis_ids=soumis_ids, enrollment=enrollment)


@login_required

@students_bp.route('/devoirs/<int:assignment_id>')
def devoirs_eleve_detail(assignment_id):
    if current_user.role != 'student':
        return redirect(url_for('dashboard.index'))

    profile = StudentProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        return redirect(url_for('dashboard.index'))

    assignment = db.session.get(Assignment, assignment_id)
    if not assignment:
        flash('Devoir introuvable.', 'danger')
        return redirect(url_for('students.devoirs_eleve'))

    enrollment = StudentEnrollment.query.filter_by(
        student_profile_id=profile.id, class_id=assignment.class_id, statut='actif'
    ).first()
    if not enrollment:
        flash('Vous n\'avez pas acces a ce devoir.', 'danger')
        return redirect(url_for('students.devoirs_eleve'))

    submission = Submission.query.filter_by(
        assignment_id=assignment_id, student_id=current_user.id
    ).first()

    return render_template('academic/devoirs/eleve_detail.html',
                          assignment=assignment, submission=submission)


@login_required

@students_bp.route('/devoirs/<int:assignment_id>/submit', methods=['POST'])
def devoirs_eleve_submit(assignment_id):
    if current_user.role != 'student':
        return redirect(url_for('dashboard.index'))

    validate_csrf(request.form.get('csrf_token', ''))

    profile = StudentProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        return redirect(url_for('dashboard.index'))

    assignment = db.session.get(Assignment, assignment_id)
    if not assignment:
        flash('Devoir introuvable.', 'danger')
        return redirect(url_for('students.devoirs_eleve'))

    # Verifier que l'élève est dans la classe du devoir
    enrollment = StudentEnrollment.query.filter_by(
        student_profile_id=profile.id, class_id=assignment.class_id, statut='actif'
    ).first()
    if not enrollment:
        flash('Acces non autorise a ce devoir.', 'danger')
        return redirect(url_for('students.devoirs_eleve'))

    if not assignment.authorise_retard and assignment.date_limite < datetime.utcnow():
        flash('La date limite est depassee. Soumission impossible.', 'danger')
        return redirect(url_for('students.devoirs_eleve_detail', assignment_id=assignment_id))

    existing = Submission.query.filter_by(
        assignment_id=assignment_id, student_id=current_user.id
    ).first()

    fichier = request.files.get('fichier')
    commentaire = request.form.get('commentaire', '').strip()

    if not fichier or not fichier.filename:
        flash('Veuillez selectionner un fichier.', 'danger')
        return redirect(url_for('students.devoirs_eleve_detail', assignment_id=assignment_id))

    if not Submission.allowed_file(fichier.filename):
        flash('Type de fichier non autorise.', 'danger')
        return redirect(url_for('students.devoirs_eleve_detail', assignment_id=assignment_id))

    if existing and existing.fichier:
        old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], existing.fichier)
        if os.path.exists(old_path):
            os.remove(old_path)
    else:
        existing = Submission(
            assignment_id=assignment_id,
            student_id=current_user.id,
        )

    filename = secure_filename(fichier.filename)
    saved_name = f"sub_{assignment_id}_{current_user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'devoirs')
    os.makedirs(upload_dir, exist_ok=True)
    fichier.save(os.path.join(upload_dir, saved_name))

    existing.fichier = f'devoirs/{saved_name}'
    existing.fichier_nom = filename
    existing.commentaire = commentaire or None
    existing.statut = 'soumis'
    existing.date_soumission = datetime.utcnow()

    if existing not in db.session:
        db.session.add(existing)
    db.session.commit()

    log_action('devoir_submit', details=f'Eleve {current_user.id} devoir {assignment_id}: {filename}')
    flash('Devoir soumis avec succes !', 'success')
    return redirect(url_for('students.devoirs_eleve_detail', assignment_id=assignment_id))


# ============================================================
# ARCHIVES — Dossiers documents des eleves
# ============================================================

@students_bp.route('/archives')
@login_required
def archives():
    """Archives — Dossiers + Bulletins de tous les eleves (lecture seule).
    Accessible a tous les roles : admin voit tout, prof voit ses classes,
    parent voit ses enfants, eleve voit son propre dossier."""
    school_id = _get_school_id()
    if not school_id:
        flash('Veuillez selectionner une ecole.', 'warning')
        return redirect(url_for('dashboard.index'))

    from app.models.user import User
    from app.models.academic import AcademicYear, Trimester, ClassSubject

    # Toutes les annees pour le filtre
    all_years = AcademicYear.query.filter_by(school_id=school_id)\
        .order_by(AcademicYear.date_debut.desc()).all()
    year_filter = request.args.get('year_id', type=int)

    # Determiner les profils visibles selon le role
    if current_user.role in ('super_admin', 'school_admin'):
        # Inclut les eleves actifs ET les diplomes
        profiles = StudentProfile.query.join(User, StudentProfile.user_id == User.id)\
            .filter(User.school_id == school_id)\
            .order_by(StudentProfile.statut, User.nom, User.prenom).all()
    elif current_user.role == 'teacher':
        # Profs: eleves dans leurs classes
        teacher_class_ids = [cs.class_id for cs in ClassSubject.query.filter_by(
            teacher_id=current_user.id).all()]
        if not teacher_class_ids:
            profiles = []
        else:
            student_ids = db.session.query(StudentEnrollment.student_profile_id).filter(
                StudentEnrollment.class_id.in_(teacher_class_ids),
                StudentEnrollment.statut == 'actif'
            ).distinct().all()
            profiles = StudentProfile.query.join(User, StudentProfile.user_id == User.id)\
                .filter(StudentProfile.id.in_([s[0] for s in student_ids]))\
                .order_by(User.nom, User.prenom).all()
    elif current_user.role == 'parent':
        # Parent: ses enfants uniquement
        from app.models.student import StudentParent
        child_ids = [sp.student_profile_id for sp in StudentParent.query.filter_by(
            parent_id=current_user.id).all()]
        profiles = StudentProfile.query.join(User, StudentProfile.user_id == User.id)\
            .filter(StudentProfile.id.in_(child_ids))\
            .order_by(User.nom, User.prenom).all() if child_ids else []
    elif current_user.role == 'student':
        profile = StudentProfile.query.filter_by(user_id=current_user.id).first()
        profiles = [profile] if profile else []
    else:
        profiles = []

    # Construire les donnees: dossiers + bulletins par eleve
    import os as _os
    archives_data = []
    for p in profiles:
        # Dossier documents (archives/ID/)
        archive_dir = _os.path.join(current_app.config['UPLOAD_FOLDER'], 'archives', str(p.id))
        docs = []
        if _os.path.exists(archive_dir):
            for f in sorted(_os.listdir(archive_dir)):
                fpath = _os.path.join(archive_dir, f)
                if _os.path.isfile(fpath):
                    size = _os.path.getsize(fpath)
                    docs.append({'name': f, 'size': size, 'url': f'/uploads/archives/{p.id}/{f}'})

        # Bulletins par annee
        enrollments = StudentEnrollment.query.filter_by(student_profile_id=p.id)\
            .order_by(StudentEnrollment.date_inscription.desc()).all()
        years_with_bulletins = []
        for enr in enrollments:
            ac_year = db.session.get(AcademicYear, enr.academic_year_id)
            if not ac_year:
                continue
            if year_filter and ac_year.id != year_filter:
                continue
            trim_count = Trimester.query.filter_by(academic_year_id=ac_year.id).count()
            years_with_bulletins.append({
                'year': ac_year, 'enrollment': enr, 'trim_count': trim_count,
            })

        archives_data.append({
            'profile': p, 'docs': docs, 'has_docs': len(docs) > 0,
            'years': years_with_bulletins,
        })

    can_export = current_user.role in ('super_admin', 'school_admin')

    return render_template('students/archives.html',
                          archives_data=archives_data,
                          all_years=all_years, year_filter=year_filter,
                          school_id=school_id, can_export=can_export)







# ============================================================
# ARCHIVES — Export global et individuel
# ============================================================

@students_bp.route('/archives/export/all')
@login_required
@role_required('super_admin', 'school_admin')
def archives_export_all():
    school_id = _get_school_id()
    if not school_id:
        flash('Veuillez selectionner une ecole.', 'danger')
        return redirect(url_for('dashboard.index'))
    import zipfile, io as _io, os as _os
    archive_root = _os.path.join(current_app.config['UPLOAD_FOLDER'], 'archives')
    if not _os.path.exists(archive_root):
        flash('Aucune archive disponible.', 'warning')
        return redirect(url_for('students.archives', school_id=school_id))
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in _os.walk(archive_root):
            for file in files:
                fpath = _os.path.join(root, file)
                arcname = _os.path.relpath(fpath, archive_root)
                zf.write(fpath, arcname)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f'archives_ecole_{school_id}.zip')

@students_bp.route('/archives/export/<int:profile_id>')
@login_required
@role_required('super_admin', 'school_admin')
def archives_export_student(profile_id):
    profile = db.session.get(StudentProfile, profile_id)
    if not profile:
        flash('Eleve introuvable.', 'danger')
        return redirect(url_for('students.archives', school_id=_get_school_id()))
    import zipfile, io as _io, os as _os
    archive_dir = _os.path.join(current_app.config['UPLOAD_FOLDER'], 'archives', str(profile_id))
    if not _os.path.exists(archive_dir):
        flash('Aucun document pour cet eleve.', 'warning')
        return redirect(url_for('students.archives', school_id=_get_school_id()))
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in _os.listdir(archive_dir):
            fpath = _os.path.join(archive_dir, file)
            if _os.path.isfile(fpath):
                zf.write(fpath, f'{profile.user.nom}_{profile.user.prenom}/{file}')
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f'archive_{profile.user.nom}_{profile.user.prenom}.zip')
