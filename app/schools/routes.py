import os
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import current_user
from app.schools import schools_bp
from app.schools.forms import SchoolForm
from app.models import db
from app.models.school import School
from app.models.subscription import Plan, Subscription
from app.models.user import User
from app.auth.decorators import role_required, school_admin_required
from datetime import datetime
from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@schools_bp.route('/')
@role_required('super_admin')
def list():
    """Liste paginée des écoles avec recherche et filtres."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    filtre_statut = request.args.get('statut', '').strip()
    filtre_plan = request.args.get('plan_id', '', type=int)

    query = School.query

    if search:
        query = query.filter(
            db.or_(
                School.nom.ilike(f'%{search}%'),
                School.code.ilike(f'%{search}%'),
                School.ville.ilike(f'%{search}%'),
            )
        )

    if filtre_statut:
        query = query.filter(School.statut == filtre_statut)

    if filtre_plan:
        query = query.filter(School.plan_id == filtre_plan)

    query = query.order_by(School.created_at.desc())
    pagination = query.paginate(page=page, per_page=current_app.config['ITEMS_PER_PAGE'], error_out=False)
    ecoles = pagination.items
    plans = Plan.query.filter_by(actif=True).all()

    return render_template(
        'schools/list.html',
        ecoles=ecoles,
        pagination=pagination,
        search=search,
        filtre_statut=filtre_statut,
        filtre_plan=filtre_plan,
        plans=plans,
    )


@schools_bp.route('/create', methods=['GET', 'POST'])
@role_required('super_admin')
def create():
    """Création d'une nouvelle école."""
    form = SchoolForm()
    if form.validate_on_submit():
        school = School(
            nom=(form.nom.data or '').strip(),
            code=(form.code.data or '').strip().upper(),
            type_ecole=form.type_ecole.data or None,
            adresse=(form.adresse.data or '').strip() or None,
            ville=(form.ville.data or '').strip() or None,
            pays=form.pays.data,
            telephone=(form.telephone.data or '').strip() or None,
            email=(form.email.data or '').strip().lower() or None,
            site_web=(form.site_web.data or '').strip() or None,
            devise=form.devise.data,
            langue=form.langue.data,
            fuseau_horaire=form.fuseau_horaire.data,
            plan_id=form.plan_id.data,
            statut='active',
        )

        # Upload du logo
        if form.logo.data and allowed_file(form.logo.data.filename):
            filename = secure_filename(f"{school.code}_{form.logo.data.filename}")
            logo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'logos')
            os.makedirs(logo_path, exist_ok=True)
            form.logo.data.save(os.path.join(logo_path, filename))
            school.logo = f'logos/{filename}'

        db.session.add(school)
        db.session.flush()

        # Créer l'abonnement
        plan = db.session.get(Plan, form.plan_id.data)
        if plan:
            subscription = Subscription(
                school_id=school.id,
                plan_id=plan.id,
                date_debut=datetime.utcnow(),
                statut='active',
            )
            db.session.add(subscription)

        db.session.commit()
        flash(f'École "{school.nom}" créée avec succès !', 'success')
        return redirect(url_for('schools.detail', school_id=school.id))

    return render_template('schools/create.html', form=form, ecole=None)


@schools_bp.route('/<int:school_id>')
@role_required('super_admin', 'school_admin')
def detail(school_id):
    """Détail d'une école avec statistiques."""
    school = db.session.get(School, school_id)
    if not school:
        flash('École introuvable.', 'danger')
        return redirect(url_for('schools.list'))

    # Vérifie que le school_admin ne voit que son école
    if current_user.role == 'school_admin' and current_user.school_id != school_id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('dashboard.index'))

    subscription = Subscription.query.filter_by(
        school_id=school_id, statut='active'
    ).order_by(Subscription.created_at.desc()).first()

    return render_template(
        'schools/detail.html',
        ecole=school,
        subscription=subscription,
    )


@schools_bp.route('/<int:school_id>/edit', methods=['GET', 'POST'])
@role_required('super_admin', 'school_admin')
def edit(school_id):
    """Modification des informations d'une école."""
    school = db.session.get(School, school_id)
    if not school:
        flash('École introuvable.', 'danger')
        return redirect(url_for('schools.list'))

    if current_user.role == 'school_admin' and current_user.school_id != school_id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('dashboard.index'))

    form = SchoolForm(obj=school)
    form.set_school_id(school_id)

    if form.validate_on_submit():
        school.nom = (form.nom.data or '').strip()
        school.code = (form.code.data or '').strip().upper()
        school.type_ecole = form.type_ecole.data or None
        school.adresse = (form.adresse.data or '').strip() or None
        school.ville = (form.ville.data or '').strip() or None
        school.pays = form.pays.data
        school.telephone = (form.telephone.data or '').strip() or None
        school.email = ((form.email.data or '').strip().lower() or None) if form.email.data else None
        school.site_web = ((form.site_web.data or '').strip() or None) if form.site_web.data else None
        school.devise = form.devise.data
        school.langue = form.langue.data
        school.fuseau_horaire = form.fuseau_horaire.data

        # Changement de plan
        if current_user.role == 'super_admin' and form.plan_id.data != school.plan_id:
            # Désactive l'ancien abonnement
            active_subs = Subscription.query.filter_by(school_id=school_id, statut='active').all()
            for sub in active_subs:
                sub.statut = 'expiree'
            # Crée le nouveau
            new_sub = Subscription(
                school_id=school_id,
                plan_id=form.plan_id.data,
                date_debut=datetime.utcnow(),
                statut='active',
            )
            db.session.add(new_sub)
            school.plan_id = form.plan_id.data

        # Upload du nouveau logo
        if form.logo.data and allowed_file(form.logo.data.filename):
            filename = secure_filename(f"{school.code}_{form.logo.data.filename}")
            logo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'logos')
            os.makedirs(logo_path, exist_ok=True)
            form.logo.data.save(os.path.join(logo_path, filename))
            school.logo = f'logos/{filename}'

        db.session.commit()
        flash(f'École "{school.nom}" mise à jour.', 'success')
        return redirect(url_for('schools.detail', school_id=school_id))

    # Pré-remplit le plan
    if not form.is_submitted():
        form.plan_id.data = school.plan_id

    return render_template('schools/create.html', form=form, ecole=school)


@schools_bp.route('/<int:school_id>/suspend', methods=['POST'])
@role_required('super_admin')
def suspend(school_id):
    """Suspension d'une école."""

    school = db.session.get(School, school_id)
    if not school:
        flash('École introuvable.', 'danger')
        return redirect(url_for('schools.list'))

    school.statut = 'suspendue'
    db.session.commit()
    flash(f'École "{school.nom}" suspendue.', 'warning')
    return redirect(url_for('schools.detail', school_id=school_id))


@schools_bp.route('/<int:school_id>/activate', methods=['POST'])
@role_required('super_admin')
def activate(school_id):
    """Réactivation d'une école."""

    school = db.session.get(School, school_id)
    if not school:
        flash('École introuvable.', 'danger')
        return redirect(url_for('schools.list'))

    school.statut = 'active'
    db.session.commit()
    flash(f'École "{school.nom}" réactivée.', 'success')
    return redirect(url_for('schools.detail', school_id=school_id))
