import os

from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, current_app

from flask_login import login_required, current_user

from werkzeug.utils import secure_filename

from app.users import users_bp

from app.users.forms import UserForm, UserEditForm, ChangePasswordForm

from app.models import db

from app.models.user import User

from app.models.school import School

from app.auth.decorators import role_required, permission_required, school_admin_required

from flask_wtf.csrf import generate_csrf





@users_bp.route('/')

@role_required('super_admin', 'school_admin')

def list():

    """Liste paginée des utilisateurs avec filtres."""

    page = request.args.get('page', 1, type=int)

    q = request.args.get('q', request.args.get('search', '')).strip()

    filtre_role = request.args.get('role', '').strip()

    filtre_statut = request.args.get('statut', '').strip()



    query = User.query



    # Filtre par école

    if current_user.role == 'school_admin':

        query = query.filter(User.school_id == current_user.school_id)

    elif current_user.is_super_admin and request.args.get('school_id'):

        query = query.filter(User.school_id == int(request.args.get('school_id')))



    if q:

        query = query.filter(

            db.or_(

                User.nom.ilike(f'%{q}%'),

                User.prenom.ilike(f'%{q}%'),

                User.email.ilike(f'%{q}%'),

            )

        )



    if filtre_role:

        query = query.filter(User.role == filtre_role)



    if filtre_statut == 'actif':

        query = query.filter(User.actif == True)

    elif filtre_statut == 'inactif':

        query = query.filter(User.actif == False)



    query = query.order_by(User.role, User.nom, User.prenom)

    pagination = query.paginate(page=page, per_page=current_app.config['ITEMS_PER_PAGE'], error_out=False)

    users = pagination.items



    # Écoles pour le filtre super admin

    schools = School.query.order_by(School.nom).all() if current_user.is_super_admin else []



    return render_template(

        'users/list.html',

        users=users,

        pagination=pagination,

        q=q,

        filtre_role=filtre_role,

        filtre_statut=filtre_statut,

        schools=schools,

        breadcrumbs=[("Utilisateurs", None)]

    )





@users_bp.route('/create', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def create():

    """Création d'un nouvel utilisateur."""

    form = UserForm()



    if form.validate_on_submit():

        # Vérifie les limites du plan

        if current_user.role == 'school_admin':

            school = current_user.school

            if school and school.plan:

                if form.role.data == 'teacher':

                    nb = User.query.filter_by(school_id=school.id, role='teacher').count()

                    if nb >= school.plan.max_enseignants:

                        flash(f'Limite d\'enseignants atteinte ({school.plan.max_enseignants}).', 'danger')

                        return render_template('users/create.html', form=form)

                elif form.role.data == 'student':

                    nb = User.query.filter_by(school_id=school.id, role='student').count()

                    if nb >= school.plan.max_eleves:

                        flash(f'Limite d\'élèves atteinte ({school.plan.max_eleves}).', 'danger')

                        return render_template('users/create.html', form=form)



        user = User(

            prenom=form.prenom.data.strip(),

            nom=form.nom.data.strip(),

            email=form.email.data.strip().lower(),

            telephone=form.telephone.data.strip() if form.telephone.data else None,

            role=form.role.data,

            school_id=form.school_id.data if form.role.data != 'super_admin' else None,

            actif=form.actif.data,

        )

        user.set_password(form.password.data)

        db.session.add(user)

        db.session.commit()



        flash(f'Utilisateur "{user.nom_complet}" créé.', 'success')

        return redirect(url_for('users.list'))



    # Pré-remplit l'école pour school_admin

    if current_user.role == 'school_admin' and not form.is_submitted():

        form.school_id.data = current_user.school_id



    return render_template('users/create.html', form=form, utilisateur=None,

                          breadcrumbs=[("Utilisateurs", url_for('users.list')), ("Création", None)])





@users_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def edit(user_id):

    """Modification d'un utilisateur."""

    user = db.session.get(User, user_id)

    if not user:

        flash('Utilisateur introuvable.', 'danger')

        return redirect(url_for('users.list'))



    # Sécurité : un admin d'école ne peut modifier que les utilisateurs de son école

    if current_user.role == 'school_admin' and user.school_id != current_user.school_id:

        flash('Accès non autorisé.', 'danger')

        return redirect(url_for('users.list'))



    # Un super_admin ne peut pas être modifié par un school_admin

    if current_user.role == 'school_admin' and user.is_super_admin:

        flash('Vous ne pouvez pas modifier un Super Administrateur.', 'danger')

        return redirect(url_for('users.list'))



    form = UserEditForm(obj=user)

    form.set_user_id(user_id)



    if form.validate_on_submit():

        user.prenom = form.prenom.data.strip()

        user.nom = form.nom.data.strip()

        user.email = form.email.data.strip().lower()

        user.telephone = form.telephone.data.strip() if form.telephone.data else None



        # Le super admin peut changer le rôle et l'école

        if current_user.is_super_admin:

            user.role = form.role.data

            user.school_id = form.school_id.data if form.role.data != 'super_admin' else None



        user.actif = form.actif.data



        # Mot de passe changé seulement si fourni

        if form.password.data:

            user.set_password(form.password.data)



        db.session.commit()

        flash(f'Utilisateur "{user.nom_complet}" mis Ã  jour.', 'success')

        return redirect(url_for('users.list'))



    if not form.is_submitted():

        if current_user.is_super_admin:

            form.school_id.data = user.school_id



    return render_template('users/create.html', form=form, utilisateur=user,

                          breadcrumbs=[("Utilisateurs", url_for('users.list')), ("Modification", None)])





@users_bp.route('/<int:user_id>/toggle', methods=['POST'])

@role_required('super_admin', 'school_admin')

def toggle_active(user_id):

    """Active/désactive un utilisateur."""


    user = db.session.get(User, user_id)

    if not user:

        flash('Utilisateur introuvable.', 'danger')

        return redirect(url_for('users.list'))



    if current_user.role == 'school_admin' and user.school_id != current_user.school_id:

        flash('Accès non autorisé.', 'danger')

        return redirect(url_for('users.list'))



    if user.id == current_user.id:

        flash('Vous ne pouvez pas désactiver votre propre compte.', 'warning')

        return redirect(url_for('users.list'))



    user.actif = not user.actif

    db.session.commit()



    etat = 'activé' if user.actif else 'désactivé'

    flash(f'Utilisateur "{user.nom_complet}" {etat}.', 'info')

    return redirect(url_for('users.list'))





@users_bp.route('/<int:user_id>/delete', methods=['POST'])

@role_required('super_admin', 'school_admin')

def delete(user_id):

    """Supprime un utilisateur."""


    user = db.session.get(User, user_id)

    if not user:

        flash('Utilisateur introuvable.', 'danger')

        return redirect(url_for('users.list'))



    if current_user.role == 'school_admin' and user.school_id != current_user.school_id:

        flash('Accès non autorisé.', 'danger')

        return redirect(url_for('users.list'))



    if user.id == current_user.id:

        flash('Vous ne pouvez pas supprimer votre propre compte.', 'warning')

        return redirect(url_for('users.list'))



    if user.is_super_admin and current_user.role != 'super_admin':

        flash('Vous ne pouvez pas supprimer un Super Administrateur.', 'danger')

        return redirect(url_for('users.list'))



    nom = user.nom_complet

    db.session.delete(user)

    db.session.commit()

    flash(f'Utilisateur "{nom}" supprimé.', 'info')

    return redirect(url_for('users.list'))





@users_bp.route('/profile', methods=['GET', 'POST'])

@login_required

def profile():

    """Profil de l'utilisateur connecté — avec changement de mot de passe et avatar."""

    form = ChangePasswordForm()



    if request.method == 'POST':

        # Gestion upload avatar (indépendant du changement de mot de passe)

        avatar = request.files.get('avatar')

        if avatar and avatar.filename:

            filename = secure_filename(avatar.filename)

            ext = filename.rsplit('.', 1)[-1].lower()

            if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):

                unique_name = f'user_{current_user.id}_{datetime.utcnow().timestamp():.0f}.{ext}'

                avatar_dir = os.path.join(current_app.static_folder, 'uploads', 'avatars')

                os.makedirs(avatar_dir, exist_ok=True)

                avatar_path = os.path.join(avatar_dir, unique_name)

                avatar.save(avatar_path)

                # Supprimer l'ancien avatar si remplacement

                if current_user.photo:

                    old_path = os.path.join(current_app.static_folder, current_user.photo.lstrip('/'))

                    if os.path.exists(old_path):

                        os.remove(old_path)

                current_user.photo = f'/static/uploads/avatars/{unique_name}'

                db.session.commit()

                flash('Photo de profil mise Ã  jour.', 'success')

                return redirect(url_for('users.profile'))



        # Changement de mot de passe

        if form.validate_on_submit():

            if not current_user.check_password(form.current_password.data):

                flash('Mot de passe actuel incorrect.', 'danger')

            else:

                current_user.set_password(form.new_password.data)

                db.session.commit()

                flash('Mot de passe changé avec succès.', 'success')

                return redirect(url_for('users.profile'))



    return render_template('users/profile.html', form=form,

                          csrf_token=generate_csrf(),

                          breadcrumbs=[("Mon Profil", None)])





