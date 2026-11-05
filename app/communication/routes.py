from flask import render_template, redirect, url_for, flash, request, current_app, send_from_directory
from flask_login import current_user
import json
from datetime import datetime
import os

from app.communication import com_bp
from app.communication.forms import AnnouncementForm
from app.models import db
from app.models.announcement import Announcement
from app.models.user import User
from app.models.academic import AcademicYear, Class
from app.utils.helpers import _get_school_id
from app.auth.decorators import role_required

@com_bp.route('/annonces')
@role_required('super_admin', 'school_admin', 'teacher', 'parent', 'student')
def list_annonces():
    school_id = _get_school_id() or current_user.school_id
    if not school_id:
        flash('Aucune ecole.', 'warning')
        return redirect(url_for('dashboard.index'))

    annonces = Announcement.for_user(current_user)

    # Filtrer par annee scolaire active
    from app.academic.routes import _get_active_year_id
    year_id = _get_active_year_id(school_id)
    if year_id:
        annonces = [a for a in annonces if a.academic_year_id is None or a.academic_year_id == year_id]

    # Filtre par priorite
    filter_priorite = request.args.get('filter', 'all')
    if filter_priorite != 'all':
        annonces = [a for a in annonces if a.priorite == filter_priorite]

    return render_template('communication/annonces.html', annonces=annonces, school_id=school_id,
                          filter_priorite=filter_priorite,
                          breadcrumbs=[("Annonces", None)])


@com_bp.route('/annonces/create', methods=['GET', 'POST'])
@role_required('super_admin', 'school_admin')
def create_annonce():
    school_id = _get_school_id()
    if not school_id:
        flash('Veuillez selectionner une ecole.', 'warning')
        return redirect(url_for('dashboard.index'))

    form = AnnouncementForm()
    form.load_choices(school_id)
    classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()
    all_users = User.query.filter_by(school_id=school_id, actif=True).order_by(User.role, User.nom, User.prenom).all()
    users_by_role = {}
    for u in all_users:
        role_label = {'teacher':'Enseignants','parent':'Parents','student':'Élèves','school_admin':'Admins'}.get(u.role, u.role)
        if role_label not in users_by_role:
            users_by_role[role_label] = []
        users_by_role[role_label].append((u.id, f'{u.prenom} {u.nom} ({u.role})'))
    roles_choices = [
        ('teacher', 'Enseignants'), ('parent', 'Parents'),
        ('student', 'Eleves'), ('school_admin', 'Administrateurs'),
    ]

    if form.validate_on_submit():
        annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()
        target_classes = request.form.getlist('target_classes')
        target_roles = request.form.getlist('target_roles')
        target_users = request.form.getlist('target_users')

        annonce = Announcement(
            school_id=school_id,
            author_id=current_user.id,
            academic_year_id=annee.id if annee else None,
            titre=form.titre.data,
            contenu=form.contenu.data,
            priorite=form.priorite.data,
            target_class_ids=json.dumps([int(c) for c in target_classes]) if target_classes else None,
            target_roles=json.dumps(target_roles) if target_roles else None,
            target_user_ids=json.dumps([int(u) for u in target_users]) if target_users else None,
            published=form.published.data,
        )
        db.session.add(annonce)
        db.session.flush()  # besoin de annonce.id pour le nom du fichier

        # Gestion du fichier joint
        fichier = request.files.get('fichier_joint')
        if fichier and fichier.filename:
            from werkzeug.utils import secure_filename
            ALLOWED = {'pdf','doc','docx','xls','xlsx','ppt','pptx','jpg','jpeg','png','gif','bmp','webp','zip','txt','csv'}
            filename = secure_filename(fichier.filename)
            ext = filename.rsplit('.',1)[-1].lower() if '.' in filename else ''
            if ext in ALLOWED:
                saved = f"annonce_{annonce.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{ext}"
                upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'annonces')
                os.makedirs(upload_dir, exist_ok=True)
                fichier.save(os.path.join(upload_dir, saved))
                annonce.fichier_joint = f'annonces/{saved}'
                annonce.fichier_joint_nom = filename
            else:
                flash(f'Type de fichier non autorise: .{ext}', 'warning')

        db.session.commit()
        
        # Envoyer email aux utilisateurs cibles individuellement
        if target_users:
            try:
                from app.utils.email import send_announcement_notification
                notified = 0
                for uid in target_users:
                    target_user = db.session.get(User, int(uid))
                    if target_user and target_user.email:
                        send_announcement_notification(target_user, annonce)
                        notified += 1
                if notified:
                    flash(f'Annonce publiee et envoyee par email a {notified} personne(s).', 'success')
                else:
                    flash('Annonce publiee (emails non envoyes - verifiez la configuration Brevo).', 'warning')
            except Exception as e:
                flash(f'Annonce publiee (emails non envoyes: {e}).', 'warning')
        else:
            flash('Annonce publiee.', 'success')
        return redirect(url_for('communication.list_annonces', school_id=school_id))

    return render_template('communication/annonce_form.html', form=form,
                          classes=classes, users_by_role=users_by_role,
                          roles_choices=roles_choices, school_id=school_id)


@com_bp.route('/annonces/<int:annonce_id>')
@role_required('super_admin', 'school_admin', 'teacher', 'parent', 'student')
def detail_annonce(annonce_id):
    annonce = db.session.get(Announcement, annonce_id)
    if not annonce:
        flash('Annonce introuvable.', 'danger')
        return redirect(url_for('communication.list_annonces', school_id=_get_school_id()))
    school_id = _get_school_id()
    return render_template('communication/annonce_detail.html', annonce=annonce, school_id=school_id,
                          breadcrumbs=[("Annonces", url_for('communication.list_annonces', school_id=school_id)), ("Détail", None)])



@com_bp.route('/annonces/<int:annonce_id>/download')
@role_required('super_admin', 'school_admin', 'teacher', 'parent', 'student')
def download_annonce_file(annonce_id):
    annonce = db.session.get(Announcement, annonce_id)
    if not annonce or not annonce.fichier_joint:
        flash('Aucun fichier joint.', 'warning')
        return redirect(url_for('communication.detail_annonce', annonce_id=annonce_id))
    
    # Verifier que l'utilisateur a le droit de voir cette annonce (respect du ciblage)
    if current_user.role not in ('super_admin', 'school_admin'):
        visible = Announcement.for_user(current_user)
        visible_ids = {a.id for a in visible}
        if annonce.id not in visible_ids:
            flash('Acces non autorise a ce fichier.', 'danger')
            return redirect(url_for('communication.list_annonces', school_id=current_user.school_id))
    
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], annonce.fichier_joint)
    if not os.path.exists(file_path):
        flash('Fichier introuvable.', 'danger')
        return redirect(url_for('communication.detail_annonce', annonce_id=annonce_id))
    return send_from_directory(
        os.path.join(current_app.config['UPLOAD_FOLDER'], os.path.dirname(annonce.fichier_joint)),
        os.path.basename(annonce.fichier_joint),
        as_attachment=True,
        download_name=annonce.fichier_joint_nom or os.path.basename(annonce.fichier_joint)
    )


@com_bp.route('/annonces/<int:annonce_id>/edit', methods=['GET', 'POST'])
@role_required('super_admin', 'school_admin')
def edit_annonce(annonce_id):
    annonce = db.session.get(Announcement, annonce_id)
    if not annonce:
        flash('Annonce introuvable.', 'danger')
        return redirect(url_for('communication.list_annonces', school_id=_get_school_id()))

    school_id = annonce.school_id
    form = AnnouncementForm()
    classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()
    all_users = User.query.filter_by(school_id=school_id, actif=True).order_by(User.role, User.nom, User.prenom).all()
    users_by_role = {}
    for u in all_users:
        role_label = {'teacher':'Enseignants','parent':'Parents','student':'Élèves','school_admin':'Admins'}.get(u.role, u.role)
        if role_label not in users_by_role:
            users_by_role[role_label] = []
        users_by_role[role_label].append((u.id, f'{u.prenom} {u.nom} ({u.role})'))
    roles_choices = [
        ('teacher', 'Enseignants'), ('parent', 'Parents'),
        ('student', 'Eleves'), ('school_admin', 'Administrateurs'),
    ]

    if form.validate_on_submit():
        annonce.titre = form.titre.data
        annonce.contenu = form.contenu.data
        annonce.priorite = form.priorite.data
        target_classes = request.form.getlist('target_classes')
        target_roles = request.form.getlist('target_roles')
        target_users = request.form.getlist('target_users')
        annonce.target_class_ids = json.dumps([int(c) for c in target_classes]) if target_classes else None
        annonce.target_roles = json.dumps(target_roles) if target_roles else None
        annonce.target_user_ids = json.dumps([int(u) for u in target_users]) if target_users else None
        annonce.published = form.published.data
        db.session.commit()
        flash('Annonce modifiee.', 'success')
        return redirect(url_for('communication.detail_annonce', annonce_id=annonce.id, school_id=school_id))

    # Pre-remplissage GET
    if request.method == 'GET':
        form.titre.data = annonce.titre
        form.contenu.data = annonce.contenu
        form.priorite.data = annonce.priorite
        form.published.data = annonce.published

    return render_template('communication/edit_annonce.html', form=form,
                          annonce=annonce, classes=classes, users_by_role=users_by_role,
                          roles_choices=roles_choices, school_id=school_id)


@com_bp.route('/annonces/<int:annonce_id>/delete', methods=['POST'])
@role_required('super_admin', 'school_admin')

def delete_annonce(annonce_id):
    annonce = db.session.get(Announcement, annonce_id)
    if annonce:
        db.session.delete(annonce)
        db.session.commit()
        flash('Annonce supprimee.', 'info')
    return redirect(url_for('communication.list_annonces', school_id=_get_school_id()))
