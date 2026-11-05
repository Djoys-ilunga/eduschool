import io
import os
import json
import zipfile

from datetime import datetime, date

from flask import render_template, redirect, url_for, flash, request, current_app, send_file, jsonify

from flask_login import current_user, login_required

from app.academic import academic_bp

from app.academic.forms import AcademicYearForm, ClassForm, SubjectForm, ClassSubjectForm, ClassSubjectEditForm

from app.models import db

from app.utils.audit import log_action
from app.utils.helpers import _get_school_id

from app.models.academic import AcademicYear, Class, Subject, ClassSubject, Trimester, Period, Deliberation
from app.models.assignment import Assignment, Submission
from app.models.student import StudentProfile, StudentEnrollment, StudentParent, StudentBulletinAccess

from app.auth.decorators import role_required, school_admin_required

from flask_wtf.csrf import generate_csrf, validate_csrf





def _get_active_year_id(school_id=None):
    """Retourne l'ID de l'annee scolaire active (session ou derniere active)."""
    from flask import session
    if not school_id:
        school_id = _get_school_id()
    if not school_id:
        return None
    # Priorite: session > derniere annee active de l'ecole
    if 'active_year_id' in session and session.get('active_school_id') == school_id:
        year = db.session.get(AcademicYear, session['active_year_id'])
        if year and year.school_id == school_id:
            return year.id
    # Fallback: derniere annee active
    year = AcademicYear.query.filter_by(school_id=school_id, statut='active').order_by(AcademicYear.date_debut.desc()).first()
    if year:
        return year.id
    # Dernier recours: n'importe quelle annee
    year = AcademicYear.query.filter_by(school_id=school_id).order_by(AcademicYear.date_debut.desc()).first()
    return year.id if year else None


def _build_trimestres_json(form):

    """Construit le JSON des trimestres depuis le formulaire."""

    trimestres = []

    trimestres_data = [

        ('1er Trimestre', form.t1_debut.data, form.t1_fin.data),

        ('2eme Trimestre', form.t2_debut.data, form.t2_fin.data),

        ('3eme Trimestre', form.t3_debut.data, form.t3_fin.data),

    ]

    for nom, debut, fin in trimestres_data:

        t = {'nom': nom}

        if debut:

            t['debut'] = str(debut)

        if fin:

            t['fin'] = str(fin)

        trimestres.append(t)

    return json.dumps(trimestres)





def _prefill_trimestres(form, year):

    """Pre-remplit les champs trimestres depuis l'objet AcademicYear."""

    trimestres = year.trimestres  # property qui parse le JSON

    mapping = [

        ('t1_debut', 't1_fin'),

        ('t2_debut', 't2_fin'),

        ('t3_debut', 't3_fin'),

    ]

    for i, (champ_debut, champ_fin) in enumerate(mapping):

        if i < len(trimestres):

            t = trimestres[i]

            if t.get('debut'):

                val = t['debut']

                getattr(form, champ_debut).data = date.fromisoformat(val) if isinstance(val, str) else val

            if t.get('fin'):

                val = t['fin']

                getattr(form, champ_fin).data = date.fromisoformat(val) if isinstance(val, str) else val


@academic_bp.route('/set-academic-year', methods=['POST'])
def set_academic_year():
    """Definit l'annee scolaire active dans la session."""

    from flask import session
    year_id = request.form.get('year_id', type=int)
    school_id = _get_school_id()
    if year_id:
        year = db.session.get(AcademicYear, year_id)
        if year and (current_user.is_super_admin or year.school_id == school_id):
            session['active_year_id'] = year_id
            session['active_school_id'] = year.school_id
            flash(f'Annee scolaire: {year.nom}', 'success')
    return redirect(url_for('dashboard.index'))


@academic_bp.route('/academic-years')

@role_required('super_admin', 'school_admin')

def list_years():

    """Liste des annees scolaires."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    years = AcademicYear.query.filter_by(school_id=school_id).order_by(AcademicYear.date_debut.desc()).all()



    return render_template('academic/years_list.html', years=years, school_id=school_id,

                          breadcrumbs=[("Années Scolaires", None)])





@academic_bp.route('/academic-years/create', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def create_year():

    """Creation d'une annee scolaire."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    form = AcademicYearForm()

    form.set_ids(school_id=school_id)



    if form.validate_on_submit():

        # Empecher la creation si une annee active existe deja

        existing_active = AcademicYear.query.filter_by(

            school_id=school_id, statut='active'

        ).first()

        if existing_active and form.statut.data == 'active':

            flash(f'Une annee scolaire active existe deja : "{existing_active.nom}". '

                  f'Veuillez d\'abord la cloturer avant d\'en creer une nouvelle.', 'warning')

            return render_template('academic/years_create.html', form=form, year=None, school_id=school_id,

                              breadcrumbs=[("Années Scolaires", url_for('academic.list_years', school_id=school_id)), ("Création", None)])



        year = AcademicYear(

            school_id=school_id,

            nom=form.nom.data.strip(),

            date_debut=form.date_debut.data,

            date_fin=form.date_fin.data,

            statut=form.statut.data,

            trimestres_json=_build_trimestres_json(form),

        )

        db.session.add(year)

        db.session.flush()  # get year.id



        # Auto-generer divisions + periodes selon le type d'ecole

        from app.models.academic import Trimester, Period

        from app.models.school import School

        from datetime import timedelta



        school = db.session.get(School, school_id)

        nb_div = school.nb_divisions if school else 3

        cycle = school.cycle if school else 'trimestre'

        prefix = 'S' if cycle == 'semestre' else 'T'

        div_label = 'Semestre' if cycle == 'semestre' else 'Trimestre'



        debut = form.date_debut.data

        duree_totale = (form.date_fin.data - debut).days

        duree_div = duree_totale // nb_div



        for dnum in range(1, nb_div + 1):

            d_debut = debut + timedelta(days=(dnum - 1) * duree_div)

            d_fin = debut + timedelta(days=dnum * duree_div - 1) if dnum < nb_div else form.date_fin.data

            nom_div = f'{dnum}er {div_label}' if dnum == 1 else f'{dnum}eme {div_label}'

            div = Trimester(

                school_id=school_id,

                academic_year_id=year.id,

                numero=dnum,

                nom=nom_div,

                date_debut=d_debut,

                date_fin=d_fin,

                coefficient=1.0,

            )

            db.session.add(div)

            db.session.flush()



            duree_periode = (d_fin - d_debut).days // len(Period.default_periods_for_division(school, dnum))

            for pnum, pdata in enumerate(Period.default_periods_for_division(school, dnum), 1):

                p_debut = d_debut + timedelta(days=(pnum - 1) * duree_periode)

                p_fin = d_debut + timedelta(days=pnum * duree_periode - 1) if pnum < len(Period.default_periods_for_division(school, dnum)) else d_fin

                period = Period(

                    trimester_id=div.id,

                    numero=pnum,

                    nom=pdata['nom'],

                    date_debut=p_debut,

                    date_fin=p_fin,

                    coefficient=pdata['coefficient'],

                    type_evaluation=pdata['type_evaluation'],

                )

                db.session.add(period)



        db.session.commit()

        log_action('create_year', table_name='academic_years', record_id=year.id,

                  details=f'Annee scolaire "{year.nom}" (ecole #{school_id})')

        flash(f'Annee scolaire "{year.nom}" creee avec {nb_div} {div_label.lower()}s.', 'success')

        return redirect(url_for('academic.list_years', school_id=school_id))



    return render_template('academic/years_create.html', form=form, year=None, school_id=school_id,

                          breadcrumbs=[("Années Scolaires", url_for('academic.list_years', school_id=school_id)), ("Création", None)])





@academic_bp.route('/academic-years/<int:year_id>/edit', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def edit_year(year_id):

    """Modification d'une annee scolaire."""

    year = db.session.get(AcademicYear, year_id)

    if not year:

        flash('Annee scolaire introuvable.', 'danger')

        return redirect(url_for('academic.list_years', school_id=_get_school_id()))



    school_id = year.school_id

    form = AcademicYearForm(obj=year)

    form.set_ids(year_id=year_id, school_id=school_id)



    if form.validate_on_submit():

        year.nom = form.nom.data.strip()

        year.date_debut = form.date_debut.data

        year.date_fin = form.date_fin.data

        year.statut = form.statut.data

        year.trimestres_json = _build_trimestres_json(form)

        db.session.commit()

        flash(f'Annee scolaire "{year.nom}" mise a jour.', 'success')

        return redirect(url_for('academic.list_years', school_id=school_id))



    if not form.is_submitted():

        _prefill_trimestres(form, year)



    return render_template('academic/years_create.html', form=form, year=year, school_id=school_id,

                          breadcrumbs=[("Années Scolaires", url_for('academic.list_years', school_id=school_id)), ("Modification", None)])






@role_required('super_admin', 'school_admin')



@academic_bp.route('/academic-years/<int:year_id>/delete', methods=['POST'])
def delete_year(year_id):

    """Suppression d'une annee scolaire."""


    year = db.session.get(AcademicYear, year_id)

    if not year:

        flash('Annee scolaire introuvable.', 'danger')

        return redirect(url_for('academic.list_years', school_id=_get_school_id()))



    if year.classes:

        flash(f'Impossible de supprimer : {len(year.classes)} classe(s) associee(s).', 'danger')

        return redirect(url_for('academic.list_years', school_id=year.school_id))



    nom = year.nom

    db.session.delete(year)

    db.session.commit()

    flash(f'Annee scolaire "{nom}" supprimee.', 'info')

    return redirect(url_for('academic.list_years', school_id=year.school_id))





@academic_bp.route('/academic-years/<int:year_id>/close', methods=['POST'])

@role_required('super_admin', 'school_admin')

def close_year(year_id):

    """Cloture d'une annee scolaire — empeche nouvelles notes et inscriptions."""

    year = db.session.get(AcademicYear, year_id)

    if not year:

        flash('Annee scolaire introuvable.', 'danger')

        return redirect(url_for('academic.list_years', school_id=_get_school_id()))



    if year.statut not in ('active',):

        flash(f'Impossible de cloturer : l\'annee est deja {year.statut}.', 'warning')

        return redirect(url_for('academic.list_years', school_id=year.school_id))



    year.statut = 'closee'

    db.session.commit()

    log_action('close_year', table_name='academic_years', record_id=year.id,

              details=f'Annee scolaire "{year.nom}" cloturee')

    flash(f'Annee scolaire "{year.nom}" cloturee. Nouvelles notes et inscriptions bloquées.', 'success')

    return redirect(url_for('academic.list_years', school_id=year.school_id))





@academic_bp.route('/academic-years/<int:year_id>/reopen', methods=['POST'])

@role_required('super_admin', 'school_admin')

def reopen_year(year_id):

    """Reouverture d'une annee scolaire cloturee."""

    year = db.session.get(AcademicYear, year_id)

    if not year:

        flash('Annee scolaire introuvable.', 'danger')

        return redirect(url_for('academic.list_years', school_id=_get_school_id()))



    if year.statut not in ('closee',):

        flash(f'Impossible de rouvrir : l\'annee est {year.statut}.', 'warning')

        return redirect(url_for('academic.list_years', school_id=year.school_id))



    year.statut = 'active'

    db.session.commit()

    log_action('reopen_year', table_name='academic_years', record_id=year.id,

              details=f'Annee scolaire "{year.nom}" reouverte')

    flash(f'Annee scolaire "{year.nom}" reouverte avec succes.', 'success')

    return redirect(url_for('academic.list_years', school_id=year.school_id))





# ============================================================

# PASSATION D'ANNEE SCOLAIRE

# ============================================================

PROMOTION_LEVELS = ['6eme', '5eme', '4eme', '3eme', '2nde', '1ere', 'Terminale']

# Normalisation: enlever accents et espaces pour comparaison robuste
import re as _re
def _normalize_level(lvl):
    if not lvl:
        return None
    import unicodedata
    n = unicodedata.normalize('NFD', lvl.strip().lower())
    n = ''.join(c for c in n if unicodedata.category(c) != 'Mn')  # enlever accents
    n = _re.sub(r'(\d)\s+(eme|ere|nde)', r'', n)  # "6 eme" -> "6eme"
    n = n.replace(' ', '')
    return n



def _get_next_level(current_level):
    """Retourne le niveau suivant dans la progression scolaire."""
    if not current_level:
        return None
    nl = _normalize_level(current_level)
    if not nl:
        return None
    # 1. PROMOTION_LEVELS — match exact uniquement
    for i, lvl in enumerate(PROMOTION_LEVELS):
        if _normalize_level(lvl) == nl:
            return PROMOTION_LEVELS[i + 1] if i + 1 < len(PROMOTION_LEVELS) else None
    # 2. Fallback numerique (ex: '2eme' -> '3eme', '2eme annee' -> '3eme annee')
    digits = ''.join(c for c in current_level.strip() if c.isdigit())
    if digits:
        n = int(digits)
        return current_level.replace(digits, str(n + 1), 1)
    return None


def _infer_level_from_class_name(class_name):
    """Tente de deduire le niveau a partir du nom de la classe."""
    if not class_name:
        return None
    nl = _normalize_level(class_name)
    if not nl:
        return None
    # 1. Match exact
    for lvl in PROMOTION_LEVELS:
        if _normalize_level(lvl) == nl:
            return lvl
    # 2. Match partiel (ex: '1ere annee' -> '1ere')
    for lvl in PROMOTION_LEVELS:
        nl_lvl = _normalize_level(lvl)
        if nl_lvl and nl_lvl in nl:
            return lvl
    # 3. Numerique: si le nom contient un chiffre + suffixe reconnaissable
    digits = ''.join(c for c in class_name if c.isdigit())
    if digits:
        return class_name.strip()
    return None


@academic_bp.route('/promote', methods=['GET', 'POST'])
@role_required('super_admin', 'school_admin')
def promote_students():
    """Assistant de passation d'annee scolaire.
    
    GET: Affiche le formulaire de configuration.
    POST: Execute la passation (duplication classes, promotion eleves, duplication matieres et frais).
    """
    school_id = _get_school_id()
    if not school_id:
        flash('Veuillez selectionner une ecole.', 'warning')
        return redirect(url_for('dashboard.index'))

    years = AcademicYear.query.filter_by(school_id=school_id).order_by(AcademicYear.date_debut.desc()).all()
    active_year_id = _get_active_year_id(school_id)

    if request.method == 'GET':
        # --- GET: Afficher le formulaire ---
        source_year_id = request.args.get('source_year_id', active_year_id, type=int)

        # Calculer l'annee suggeree
        suggested_next_year = ''
        if source_year_id:
            sy = db.session.get(AcademicYear, source_year_id)
            if sy and sy.nom:
                parts = sy.nom.split('-')
                if parts and parts[0].isdigit():
                    suggested_next_year = f"{parts[0]}-{int(parts[0]) + 1}" if len(parts) == 1 else f"{int(parts[0])+1}-{int(parts[1])+1}" if len(parts) > 1 and parts[1].isdigit() else sy.nom

        # Classes de l'annee source
        source_classes = []
        class_mapping = []
        if source_year_id:
            source_classes = Class.query.filter_by(
                school_id=school_id, academic_year_id=source_year_id, actif=True
            ).order_by(Class.nom).all()

            # Generer le mapping: classe source -> classe destination (preview)
            for sc in source_classes:
                current_level = sc.niveau or _infer_level_from_class_name(sc.nom)
                next_level = _get_next_level(current_level)
                if next_level and current_level:
                    # Remplacer le niveau dans le nom
                    dest_name = sc.nom.replace(current_level, next_level, 1) if current_level in sc.nom else f"{next_level} {sc.nom}"
                else:
                    dest_name = sc.nom  # garder le meme nom si pas de promotion possible

                class_mapping.append({
                    'source_class': sc,
                    'source_name': sc.nom,
                    'source_level': current_level,
                    'dest_name': dest_name,
                    'dest_level': next_level,
                    'is_terminale': not next_level,
                    'enrollment_count': StudentEnrollment.query.filter_by(class_id=sc.id, statut='actif').count(),
                    'repeat_candidates': StudentEnrollment.query.filter_by(class_id=sc.id, statut='redouble').count(),
                })

        all_school_classes = Class.query.filter_by(school_id=school_id).order_by(Class.nom).all()

        return render_template('academic/promote.html',
                               years=years,
                               source_year_id=source_year_id,
                               active_year_id=active_year_id,
                               class_mapping=class_mapping,
                               school_id=school_id,
                               suggested_next_year=suggested_next_year,
                               all_school_classes=all_school_classes,
                               breadcrumbs=[("Passation d'année", None)])

    # --- POST: Executer la passation ---
    source_year_id = request.form.get('source_year_id', type=int)
    dest_year_name = request.form.get('dest_year_name', '').strip()
    dest_year_id = request.form.get('dest_year_id', type=int)
    dest_year_start = request.form.get('dest_year_start', '').strip()
    dest_year_end = request.form.get('dest_year_end', '').strip()

    # Options
    duplicate_classes = request.form.get('duplicate_classes') == '1'
    promote_students_flag = request.form.get('promote_students') == '1'
    duplicate_subjects = request.form.get('duplicate_subjects') == '1'
    duplicate_fees = request.form.get('duplicate_fees') == '1'
    create_year = request.form.get('create_year') == '1'

    # Validation
    if not source_year_id:
        flash('Veuillez selectionner une annee source.', 'danger')
        return redirect(url_for('academic.promote_students', school_id=school_id))

    source_year = db.session.get(AcademicYear, source_year_id)
    if not source_year or source_year.school_id != school_id:
        flash('Annee source invalide.', 'danger')
        return redirect(url_for('academic.promote_students', school_id=school_id))

    # Transaction: tout ou rien
    try:
        # --- Etape 1: Creer/valider l'annee destination ---
        log_steps = []
        dest_year = None

        if dest_year_id:
            dest_year = db.session.get(AcademicYear, dest_year_id)
            if not dest_year or dest_year.school_id != school_id:
                flash('Annee destination invalide.', 'danger')
                return redirect(url_for('academic.promote_students', school_id=school_id,
                                       source_year_id=source_year_id))
            log_steps.append(f"✓ Année destination existante: {dest_year.nom}")
        elif create_year and dest_year_name:
            if not dest_year_start or not dest_year_end:
                flash('Les dates de debut et fin sont requises pour creer une nouvelle annee.', 'danger')
                return redirect(url_for('academic.promote_students', school_id=school_id,
                                       source_year_id=source_year_id))
            try:
                date_debut = datetime.strptime(dest_year_start, '%Y-%m-%d').date()
                date_fin = datetime.strptime(dest_year_end, '%Y-%m-%d').date()
            except ValueError:
                flash('Format de date invalide.', 'danger')
                return redirect(url_for('academic.promote_students', school_id=school_id,
                                       source_year_id=source_year_id))

            # Verifier qu'une annee avec ce nom n'existe pas deja
            existing = AcademicYear.query.filter_by(school_id=school_id, nom=dest_year_name).first()
            if existing:
                flash(f'Une annee scolaire "{dest_year_name}" existe deja.', 'warning')
                return redirect(url_for('academic.promote_students', school_id=school_id,
                                       source_year_id=source_year_id))

            dest_year = AcademicYear(
                school_id=school_id,
                nom=dest_year_name,
                date_debut=date_debut,
                date_fin=date_fin,
                statut='active',
                trimestres_json=source_year.trimestres_json,  # Copier la structure des trimestres
            )
            db.session.add(dest_year)
            db.session.flush()
            log_steps.append(f"✓ Nouvelle année créée: {dest_year.nom}")

            # Auto-generer divisions + periodes comme dans create_year()
            from app.models.school import School
            from datetime import timedelta
            school = db.session.get(School, school_id)
            nb_div = school.nb_divisions if school else 3
            cycle = school.cycle if school else 'trimestre'
            div_label = 'Semestre' if cycle == 'semestre' else 'Trimestre'
            debut = date_debut
            duree_totale = (date_fin - debut).days
            duree_div = duree_totale // max(nb_div, 1)
            for dnum in range(1, nb_div + 1):
                d_debut = debut + timedelta(days=(dnum - 1) * duree_div)
                d_fin = debut + timedelta(days=dnum * duree_div - 1) if dnum < nb_div else date_fin
                nom_div = f'{dnum}er {div_label}' if dnum == 1 else f'{dnum}eme {div_label}'
                div = Trimester(
                    school_id=school_id,
                    academic_year_id=dest_year.id,
                    numero=dnum,
                    nom=nom_div,
                    date_debut=d_debut,
                    date_fin=d_fin,
                    coefficient=1.0,
                )
                db.session.add(div)
                db.session.flush()
                duree_periode = (d_fin - d_debut).days // max(len(Period.default_periods_for_division(school, dnum)), 1)
                for pnum, pdata in enumerate(Period.default_periods_for_division(school, dnum), 1):
                    p_debut = d_debut + timedelta(days=(pnum - 1) * duree_periode)
                    p_fin = d_debut + timedelta(days=pnum * duree_periode - 1) if pnum < len(Period.default_periods_for_division(school, dnum)) else d_fin
                    period = Period(
                        trimester_id=div.id,
                        numero=pnum,
                        nom=pdata['nom'],
                        date_debut=p_debut,
                        date_fin=p_fin,
                        coefficient=pdata['coefficient'],
                        type_evaluation=pdata['type_evaluation'],
                    )
                    db.session.add(period)
            log_steps.append(f"  ↳ {nb_div} {div_label.lower()}s generes automatiquement")
        else:
            flash('Veuillez selectionner ou creer une annee destination.', 'danger')
            return redirect(url_for('academic.promote_students', school_id=school_id,
                                   source_year_id=source_year_id))

        # --- Etape 2: Dupliquer les classes ---
        classes_created = 0
        class_id_map = {}  # source_class_id -> new_class_id

        if duplicate_classes:
            source_classes = Class.query.filter_by(
                school_id=school_id, academic_year_id=source_year_id, actif=True
            ).order_by(Class.nom).all()

            included_class_ids = request.form.getlist('include_class')

            for sc in source_classes:
                # Ne pas dupliquer si une classe avec le meme nom existe deja dans l'annee destination
                existing_class = Class.query.filter_by(
                    school_id=school_id, academic_year_id=dest_year.id, nom=sc.nom
                ).first()
                if existing_class:
                    class_id_map[sc.id] = existing_class.id
                    continue

                # Verifier si cette classe est incluse
                if included_class_ids and str(sc.id) not in included_class_ids:
                    continue

                new_class = Class(
                    school_id=school_id,
                    academic_year_id=dest_year.id,
                    nom=sc.nom,
                    niveau=sc.niveau,
                    section=sc.section,
                    capacite_max=sc.capacite_max,
                    salle=sc.salle,
                    titulaire_id=sc.titulaire_id,
                    actif=True,
                )
                db.session.add(new_class)
                db.session.flush()
                class_id_map[sc.id] = new_class.id
                classes_created += 1

            log_steps.append(f"✓ {classes_created} classe(s) dupliquee(s)")

        # --- Gestion des classes terminales (finalistes) ---
        terminal_class_ids = [int(x) for x in request.form.getlist('terminal_class')]
        students_graduated = 0
        students_failed_term = 0
        if terminal_class_ids and promote_students_flag:
            # Parcourir toutes les inscriptions actives des classes terminales
            term_enrollments = StudentEnrollment.query.filter(
                StudentEnrollment.class_id.in_(terminal_class_ids),
                StudentEnrollment.statut == 'actif'
            ).all()
            for te in term_enrollments:
                sp = te.student_profile
                if not sp:
                    continue
                fail_key = f'fail_{sp.id}'
                has_failed = request.form.get(fail_key) == '1'
                if has_failed:
                    # L'eleve echoue — reste en redoublement dans la meme classe
                    te.statut = 'redouble'
                    students_failed_term += 1
                else:
                    # L'eleve reussit — diplome
                    te.statut = 'termine'
                    te.date_fin = datetime.utcnow().date()
                    # Marquer le profil comme diplome pour archivage
                    sp.statut = 'diplome'
                    students_graduated += 1
            if students_graduated > 0:
                log_steps.append(f"🎓 {students_graduated} eleve(s) diplome(s)")
            if students_failed_term > 0:
                log_steps.append(f"🔁 {students_failed_term} eleve(s) de terminale en echec")

        # --- Etape 3: Promouvoir les eleves ---
        students_promoted = 0
        students_repeated = 0

        if promote_students_flag:
            if not class_id_map:
                flash("Aucune classe destination. Cochez 'Dupliquer les classes' pour creer les classes automatiquement.", 'warning')
            for sc_id, new_class_id in class_id_map.items():
                source_class = db.session.get(Class, sc_id)
                if not source_class:
                    continue

                # Recuperer les eleves actifs de la classe source
                enrollments = StudentEnrollment.query.filter_by(
                    class_id=sc_id, statut='actif'
                ).all()

                # Determiner la classe destination (renommee si besoin)
                dest_class_name_key = f'dest_name_{sc_id}'
                dest_class_name = request.form.get(dest_class_name_key, '').strip()

                # Mettre a jour le nom de la classe destination si renommee
                new_class_obj = db.session.get(Class, new_class_id)
                if new_class_obj and dest_class_name and dest_class_name != source_class.nom:
                    new_class_obj.nom = dest_class_name
                    new_class_obj.niveau = _infer_level_from_class_name(dest_class_name) or _get_next_level(source_class.niveau)

                for enrollment in enrollments:
                    sp = enrollment.student_profile
                    if not sp:
                        continue

                    # Verifier si l'eleve a deja une inscription dans la nouvelle annee
                    existing_enrollment = StudentEnrollment.query.filter_by(
                        student_profile_id=sp.id, academic_year_id=dest_year.id
                    ).first()
                    if existing_enrollment:
                        continue

                    # Determiner si l'eleve redouble (checkbox individuelle)
                    repeat_key = f'repeat_{sp.id}'
                    is_repeating = request.form.get(repeat_key) == '1'

                    # Pour les eleves qui redoublent, trouver la classe du meme niveau
                    if is_repeating:
                        # Chercher une classe du meme niveau dans l'annee destination
                        same_level_class = Class.query.filter_by(
                            school_id=school_id,
                            academic_year_id=dest_year.id,
                            niveau=source_class.niveau,
                            actif=True
                        ).first()
                        target_class_id = same_level_class.id if same_level_class else new_class_id
                        students_repeated += 1
                    else:
                        target_class_id = new_class_id

                    new_enrollment = StudentEnrollment(
                        student_profile_id=sp.id,
                        class_id=target_class_id,
                        academic_year_id=dest_year.id,
                        school_id=school_id,
                        date_inscription=datetime.utcnow().date(),
                        statut='redouble' if is_repeating else 'actif',
                        numero_ordre=enrollment.numero_ordre,
                    )
                    db.session.add(new_enrollment)
                    # Marquer l'ancienne inscription comme terminee
                    enrollment.statut = 'termine'
                    enrollment.date_fin = datetime.utcnow().date()
                    students_promoted += 1

            log_steps.append(f"✓ {students_promoted} eleve(s) promu(s) dont {students_repeated} redoublant(s)")

        # --- Etape 4: Dupliquer les matieres (ClassSubject) ---
        subjects_duplicated = 0

        if duplicate_subjects and class_id_map:
            for sc_id, new_class_id in class_id_map.items():
                class_subjects = ClassSubject.query.filter_by(class_id=sc_id).all()
                for cs in class_subjects:
                    # Verifier si l'association existe deja
                    existing_cs = ClassSubject.query.filter_by(
                        class_id=new_class_id, subject_id=cs.subject_id
                    ).first()
                    if existing_cs:
                        continue

                    new_cs = ClassSubject(
                        class_id=new_class_id,
                        subject_id=cs.subject_id,
                        teacher_id=cs.teacher_id,
                        coefficient=cs.coefficient,
                        heures_par_semaine=cs.heures_par_semaine,
                        groupe=cs.groupe,
                    )
                    db.session.add(new_cs)
                    subjects_duplicated += 1

            log_steps.append(f"✓ {subjects_duplicated} matiere(s) dupliquee(s)")

        # --- Etape 5: Dupliquer les frais (Fee) ---
        fees_duplicated = 0

        if duplicate_fees and class_id_map:
            from app.models.finance import Fee
            for sc_id, new_class_id in class_id_map.items():
                fees = Fee.query.filter_by(
                    class_id=sc_id, academic_year_id=source_year_id
                ).all()
                for f in fees:
                    # Verifier si le frais existe deja
                    existing_fee = Fee.query.filter_by(
                        fee_type_id=f.fee_type_id,
                        class_id=new_class_id,
                        academic_year_id=dest_year.id
                    ).first()
                    if existing_fee:
                        continue

                    new_fee = Fee(
                        school_id=school_id,
                        fee_type_id=f.fee_type_id,
                        class_id=new_class_id,
                        academic_year_id=dest_year.id,
                        montant=f.montant,
                        devise=f.devise,
                        echeance=f.echeance,
                    )
                    db.session.add(new_fee)
                    fees_duplicated += 1

            log_steps.append(f"✓ {fees_duplicated} frais duplique(s)")

        # Commit final
        db.session.commit()

        # Log d'audit
        log_action('promote_year', table_name='academic_years', record_id=dest_year.id,
                   details=f'Passation {source_year.nom} -> {dest_year.nom}: '
                           f'{classes_created} classes, {students_promoted} eleves, '
                           f'{subjects_duplicated} matieres, {fees_duplicated} frais')

        # Message de succes
        msg = f'Passation terminee ! {classes_created} classes, {students_promoted} eleves promus'
        if students_repeated > 0:
            msg += f', {students_repeated} redoublants'
        if students_graduated > 0:
            msg += f', {students_graduated} diplomes'
        if students_failed_term > 0:
            msg += f', {students_failed_term} echecs terminale'
        msg += f', {subjects_duplicated} matieres, {fees_duplicated} frais.'
        flash(msg, 'success')

        # Rediriger vers la liste des annees avec les resultats
        return redirect(url_for('academic.list_years', school_id=school_id))

    except Exception as e:
        db.session.rollback()
        flash(f'Erreur lors de la passation: {str(e)}. Toutes les modifications ont ete annulees.', 'danger')
        current_app.logger.error(f'Promote error: {e}', exc_info=True)
        return redirect(url_for('academic.promote_students', school_id=school_id,
                               source_year_id=source_year_id))


# ============================================================

# CLASSES

# ============================================================



@academic_bp.route('/classes')

@role_required('super_admin', 'school_admin')

def list_classes():

    """Liste des classes."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    year_id = request.args.get('year_id', None, type=int) or _get_active_year_id(school_id)

    q = request.args.get('q', '').strip()

    show_archived = request.args.get('archived', '0') == '1'



    query = Class.query.filter_by(school_id=school_id)

    if year_id:

        query = query.filter_by(academic_year_id=year_id)

    if q:

        query = query.filter(Class.nom.ilike(f'%{q}%'))

    # Filtrer actives vs archivees
    query = query.filter_by(actif=not show_archived)



    classes = query.order_by(Class.academic_year_id.desc(), Class.nom).all()

    years = AcademicYear.query.filter_by(school_id=school_id).order_by(AcademicYear.date_debut.desc()).all()



    return render_template('academic/classes_list.html', classes=classes, years=years,

                          year_id=year_id, q=q, show_archived=show_archived, school_id=school_id,

                          breadcrumbs=[("Classes", None)])





@academic_bp.route('/classes/create', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def create_class():

    """Creation d'une classe."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    form = ClassForm()

    form.load_choices(school_id)



    if form.validate_on_submit():

        # Verifier que l'annee scolaire selectionnee n'est pas cloturee

        annee_concernee = db.session.get(AcademicYear, form.academic_year_id.data)

        if not annee_concernee:

            flash('Annee scolaire introuvable.', 'danger')

            return render_template('academic/classes_create.html', form=form, classe=None, school_id=school_id,

                                  breadcrumbs=[("Classes", url_for('academic.list_classes', school_id=school_id)), ("Création", None)])

        if annee_concernee.statut in ('closee', 'close'):

            flash(f'Impossible de creer une classe : l\'annee scolaire "{annee_concernee.nom}" est cloturee.', 'danger')

            return render_template('academic/classes_create.html', form=form, classe=None, school_id=school_id,

                                  breadcrumbs=[("Classes", url_for('academic.list_classes', school_id=school_id)), ("Création", None)])



        classe = Class(

            school_id=school_id,

            academic_year_id=form.academic_year_id.data,

            nom=form.nom.data.strip(),

            niveau=form.niveau.data.strip() if form.niveau.data else None,

            section=form.section.data.strip() if form.section.data else None,

            capacite_max=form.capacite_max.data or None,

            salle=form.salle.data.strip() if form.salle.data else None,

            titulaire_id=form.titulaire_id.data or None,

        )

        db.session.add(classe)

        db.session.commit()

        log_action('create_class', table_name='classes', record_id=classe.id,

                  details=f'Classe "{classe.nom}" (ecole #{school_id})')

        flash(f'Classe "{classe.nom}" creee.', 'success')

        return redirect(url_for('academic.list_classes', school_id=school_id))



    return render_template('academic/classes_create.html', form=form, classe=None, school_id=school_id,

                          breadcrumbs=[("Classes", url_for('academic.list_classes', school_id=school_id)), ("Création", None)])





@academic_bp.route('/classes/<int:class_id>/edit', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def edit_class(class_id):

    """Modification d'une classe."""

    classe = db.session.get(Class, class_id)

    if not classe:

        flash('Classe introuvable.', 'danger')

        return redirect(url_for('academic.list_classes', school_id=_get_school_id()))



    school_id = classe.school_id

    form = ClassForm(obj=classe)

    form.load_choices(school_id)

    form.set_class_id(class_id)



    if form.validate_on_submit():

        classe.academic_year_id = form.academic_year_id.data

        classe.nom = form.nom.data.strip()

        classe.niveau = form.niveau.data.strip() if form.niveau.data else None

        classe.section = form.section.data.strip() if form.section.data else None

        classe.capacite_max = form.capacite_max.data or None

        classe.salle = form.salle.data.strip() if form.salle.data else None

        classe.titulaire_id = form.titulaire_id.data or None

        db.session.commit()

        flash(f'Classe "{classe.nom}" mise a jour.', 'success')

        return redirect(url_for('academic.list_classes', school_id=school_id))



    if not form.is_submitted():

        form.academic_year_id.data = classe.academic_year_id

        form.titulaire_id.data = classe.titulaire_id



    return render_template('academic/classes_create.html', form=form, classe=classe, school_id=school_id,

                          breadcrumbs=[("Classes", url_for('academic.list_classes', school_id=school_id)), ("Modification", None)])





@academic_bp.route('/classes/<int:class_id>/delete', methods=['POST'])

@role_required('super_admin', 'school_admin')

def delete_class(class_id):

    """Suppression d'une classe."""


    classe = db.session.get(Class, class_id)

    if not classe:

        flash('Classe introuvable.', 'danger')

        return redirect(url_for('academic.list_classes', school_id=_get_school_id()))



    if classe.matieres:

        flash(f'Impossible de supprimer : {len(classe.matieres)} matiere(s) associee(s).', 'danger')

        return redirect(url_for('academic.list_classes', school_id=classe.school_id))



    nom = classe.nom

    db.session.delete(classe)

    db.session.commit()

    flash(f'Classe "{nom}" supprimee.', 'info')

    return redirect(url_for('academic.list_classes', school_id=classe.school_id))



@academic_bp.route('/classes/<int:class_id>/archive', methods=['POST'])

@role_required('super_admin', 'school_admin')

def archive_class(class_id):

    """Archive une classe: tous les eleves actifs passent en 'termine', la classe devient inactive."""

    classe = db.session.get(Class, class_id)

    if not classe:

        flash('Classe introuvable.', 'danger')

        return redirect(url_for('academic.list_classes', school_id=_get_school_id()))



    if not classe.actif:

        flash(f'La classe "{classe.nom}" est deja archivee.', 'warning')

        return redirect(url_for('academic.list_classes', school_id=classe.school_id))



    # Passer tous les eleves actifs en 'termine'

    enrollments = StudentEnrollment.query.filter_by(

        class_id=class_id, statut='actif'

    ).all()

    nb_eleves = 0

    today = datetime.utcnow().date()

    for enrollment in enrollments:

        enrollment.statut = 'termine'

        enrollment.date_fin = today

        nb_eleves += 1



    # Desactiver la classe

    classe.actif = False

    db.session.commit()

    log_action('archive_class', table_name='classes', record_id=classe.id,

              details=f'Classe "{classe.nom}" archivee — {nb_eleves} eleve(s) termines')

    flash(f'Classe "{classe.nom}" archivee. {nb_eleves} eleve(s) passes en "termine".', 'success')

    return redirect(url_for('academic.list_classes', school_id=classe.school_id))



@academic_bp.route('/classes/<int:class_id>/unarchive', methods=['POST'])

@role_required('super_admin', 'school_admin')

def unarchive_class(class_id):

    """Restaurer une classe archivee (la reactive sans toucher aux eleves)."""

    classe = db.session.get(Class, class_id)

    if not classe:

        flash('Classe introuvable.', 'danger')

        return redirect(url_for('academic.list_classes', school_id=_get_school_id()))



    if classe.actif:

        flash(f'La classe "{classe.nom}" est deja active.', 'warning')

        return redirect(url_for('academic.list_classes', school_id=classe.school_id, archived='1'))



    classe.actif = True

    db.session.commit()

    log_action('unarchive_class', table_name='classes', record_id=classe.id,

              details=f'Classe "{classe.nom}" restauree')

    flash(f'Classe "{classe.nom}" restauree (active). Les eleves restent en l\'etat.', 'success')

    return redirect(url_for('academic.list_classes', school_id=classe.school_id, archived='1'))





# ============================================================

# MATIERES

# ============================================================



@academic_bp.route('/subjects')

@role_required('super_admin', 'school_admin')

def list_subjects():

    """Catalogue des matieres."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    filtre_cat = request.args.get('categorie', '').strip()

    q = request.args.get('q', '').strip()



    query = Subject.query.filter_by(school_id=school_id)

    if filtre_cat:

        query = query.filter_by(categorie=filtre_cat)

    if q:

        query = query.filter(Subject.nom.ilike(f'%{q}%'))



    subjects = query.order_by(Subject.categorie, Subject.nom).all()



    return render_template('academic/subjects_list.html', subjects=subjects,

                          filtre_cat=filtre_cat, q=q, school_id=school_id,

                          breadcrumbs=[("Matières", None)])





@academic_bp.route('/subjects/create', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def create_subject():

    """Creation d'une matiere."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    form = SubjectForm()

    form.set_ids(school_id=school_id)



    if form.validate_on_submit():

        subject = Subject(

            school_id=school_id,

            nom=form.nom.data.strip(),

            code=form.code.data.strip().upper() if form.code.data else None,

            description=form.description.data.strip() if form.description.data else None,

            categorie=form.categorie.data or None,

            actif=form.actif.data,

        )

        db.session.add(subject)

        db.session.commit()

        flash(f'Matiere "{subject.nom}" creee.', 'success')

        return redirect(url_for('academic.list_subjects', school_id=school_id))



    return render_template('academic/subjects_create.html', form=form, subject=None, school_id=school_id,

                          breadcrumbs=[("Matières", url_for('academic.list_subjects', school_id=school_id)), ("Création", None)])





@academic_bp.route('/subjects/<int:subject_id>/edit', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def edit_subject(subject_id):

    """Modification d'une matiere."""

    subject = db.session.get(Subject, subject_id)

    if not subject:

        flash('Matiere introuvable.', 'danger')

        return redirect(url_for('academic.list_subjects', school_id=_get_school_id()))



    school_id = subject.school_id

    form = SubjectForm(obj=subject)

    form.set_ids(subject_id=subject_id, school_id=school_id)



    if form.validate_on_submit():

        subject.nom = form.nom.data.strip()

        subject.code = form.code.data.strip().upper() if form.code.data else None

        subject.description = form.description.data.strip() if form.description.data else None

        subject.categorie = form.categorie.data or None

        subject.actif = form.actif.data

        db.session.commit()

        flash(f'Matiere "{subject.nom}" mise a jour.', 'success')

        return redirect(url_for('academic.list_subjects', school_id=school_id))



    return render_template('academic/subjects_create.html', form=form, subject=subject, school_id=school_id,

                          breadcrumbs=[("Matières", url_for('academic.list_subjects', school_id=school_id)), ("Modification", None)])





@academic_bp.route('/subjects/<int:subject_id>/delete', methods=['POST'])

@role_required('super_admin', 'school_admin')

def delete_subject(subject_id):

    """Suppression d'une matiere."""


    subject = db.session.get(Subject, subject_id)

    if not subject:

        flash('Matiere introuvable.', 'danger')

        return redirect(url_for('academic.list_subjects', school_id=_get_school_id()))



    if subject.classes_associees:

        flash(f'Impossible de supprimer : {len(subject.classes_associees)} classe(s) associee(s).', 'danger')

        return redirect(url_for('academic.list_subjects', school_id=subject.school_id))



    nom = subject.nom

    db.session.delete(subject)

    db.session.commit()

    flash(f'Matiere "{nom}" supprimee.', 'info')

    return redirect(url_for('academic.list_subjects', school_id=subject.school_id))





# ============================================================

# ASSOCIATION CLASSES - MATIERES

# ============================================================



@academic_bp.route('/classes/<int:class_id>/subjects')

@role_required('super_admin', 'school_admin')

def class_subjects(class_id):

    """Gerer les matieres d'une classe."""

    classe = db.session.get(Class, class_id)

    if not classe:

        flash('Classe introuvable.', 'danger')

        return redirect(url_for('academic.list_classes', school_id=_get_school_id()))



    school_id = classe.school_id

    class_subjects = ClassSubject.query.filter_by(class_id=class_id).order_by(ClassSubject.id).all()

    existing_ids = [cs.subject_id for cs in class_subjects]



    form = ClassSubjectForm()

    form.load_choices(school_id, exclude_ids=existing_ids)



    return render_template('academic/class_subjects.html',

                          classe=classe, class_subjects=class_subjects,

                          form=form, school_id=school_id,

                          breadcrumbs=[("Classes", url_for('academic.list_classes', school_id=school_id)), (classe.nom, None)])





@academic_bp.route('/classes/<int:class_id>/subjects/add', methods=['POST'])

@role_required('super_admin', 'school_admin')

def add_class_subject(class_id):

    """Ajouter une matiere a une classe."""

    classe = db.session.get(Class, class_id)

    if not classe:

        flash('Classe introuvable.', 'danger')

        return redirect(url_for('academic.list_classes', school_id=_get_school_id()))



    school_id = classe.school_id

    existing_ids = [cs.subject_id for cs in ClassSubject.query.filter_by(class_id=class_id).all()]

    form = ClassSubjectForm()

    form.load_choices(school_id, exclude_ids=existing_ids)



    if form.validate_on_submit():

        cs = ClassSubject(

            class_id=class_id,

            subject_id=form.subject_id.data,

            teacher_id=form.teacher_id.data or None,

            coefficient=float(form.coefficient.data),

            heures_par_semaine=float(form.heures_par_semaine.data) if form.heures_par_semaine.data else None,

            groupe=form.groupe.data.strip() if form.groupe.data else None,

        )

        db.session.add(cs)

        db.session.commit()

        flash('Matiere ajoutee a la classe.', 'success')



    return redirect(url_for('academic.class_subjects', class_id=class_id))





@academic_bp.route('/class-subjects/<int:cs_id>/edit', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def edit_class_subject(cs_id):

    """Modifier une association classe-matiere."""

    cs = db.session.get(ClassSubject, cs_id)

    if not cs:

        flash('Association introuvable.', 'danger')

        return redirect(url_for('academic.list_classes', school_id=_get_school_id()))



    classe = db.session.get(Class, cs.class_id)

    form = ClassSubjectEditForm(obj=cs)

    form.load_teachers(classe.school_id)



    if form.validate_on_submit():

        cs.teacher_id = form.teacher_id.data or None

        cs.coefficient = float(form.coefficient.data)

        cs.heures_par_semaine = float(form.heures_par_semaine.data) if form.heures_par_semaine.data else None

        cs.groupe = form.groupe.data.strip() if form.groupe.data else None

        db.session.commit()

        flash(f'Association mise a jour.', 'success')

        return redirect(url_for('academic.class_subjects', class_id=cs.class_id))



    if not form.is_submitted():

        form.coefficient.data = str(cs.coefficient)

        if cs.heures_par_semaine:

            form.heures_par_semaine.data = str(cs.heures_par_semaine)



    return render_template('academic/class_subject_edit.html', form=form, cs=cs, classe=classe,

                          breadcrumbs=[("Classes", url_for('academic.list_classes', school_id=classe.school_id)),

                                      (classe.nom, url_for('academic.class_subjects', class_id=cs.class_id)),

                                      ("Modifier", None)])





@academic_bp.route('/class-subjects/<int:cs_id>/delete', methods=['POST'])

@role_required('super_admin', 'school_admin')

def delete_class_subject(cs_id):

    """Retirer une matiere d'une classe."""


    cs = db.session.get(ClassSubject, cs_id)

    if not cs:

        flash('Association introuvable.', 'danger')

        return redirect(url_for('academic.list_classes', school_id=_get_school_id()))



    class_id = cs.class_id

    db.session.delete(cs)

    db.session.commit()

    flash('Matiere retiree de la classe.', 'info')

    return redirect(url_for('academic.class_subjects', class_id=class_id))






# ============================================================
# MES CLASSES (ENSEIGNANT)
# ============================================================



@academic_bp.route('/my-classes')
@role_required('teacher')
def my_classes():
    """Page Mes classes pour l'enseignant - liste ses ClassSubject avec details."""
    school_id = current_user.school_id
    if not school_id:
        flash('Aucune ecole associee a votre compte.', 'warning')
        return redirect(url_for('dashboard.index'))

    matieres = ClassSubject.query.filter_by(
        teacher_id=current_user.id
    ).order_by(ClassSubject.id).all()

    return render_template('academic/my_classes.html',
                          matieres=matieres, school_id=school_id,
                          breadcrumbs=[("Mes classes", None)])



# ============================================================

# EMPLOI DU TEMPS

# ============================================================



from app.models.timetable import Timetable

from app.academic.forms import TimetableForm

from collections import defaultdict





@academic_bp.route('/timetable')

@role_required('super_admin', 'school_admin', 'teacher', 'student', 'parent')

def view_timetable():

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    class_id = request.args.get('class_id', None, type=int)

    teacher_id = request.args.get('teacher_id', None, type=int)

    year_id = request.args.get('year_id', None, type=int) or _get_active_year_id(school_id)



    # Auto-detect: student sees their own class timetable

    if not class_id and current_user.role in ('student', 'parent'):

        from app.models.student import StudentProfile, StudentEnrollment, StudentParent

        
        if current_user.role == 'student':
            profile = StudentProfile.query.filter_by(user_id=current_user.id).first()
        else:  # parent
            lien = StudentParent.query.filter_by(parent_id=current_user.id).first()
            profile = lien.student_profile if lien else None

        if profile:

            enrollment = StudentEnrollment.query.filter_by(student_profile_id=profile.id, statut='actif').first()

            if enrollment:

                class_id = enrollment.class_id



    if current_user.role == 'teacher':

        teacher_id = current_user.id

        # Teacher sees only their assigned classes

        if not class_id:

            from app.models.academic import ClassSubject

            teacher_cs = ClassSubject.query.filter_by(teacher_id=current_user.id).all()

            teacher_class_ids = list(set(cs.class_id for cs in teacher_cs))

            if len(teacher_class_ids) == 1:

                class_id = teacher_class_ids[0]



    if not year_id:

        annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

        year_id = annee.id if annee else None



    query = Timetable.query.filter_by(school_id=school_id)

    if year_id:

        query = query.filter_by(academic_year_id=year_id)

    if class_id:

        query = query.filter_by(class_id=class_id)

    if teacher_id:

        query = query.filter_by(teacher_id=teacher_id)



    creneaux = query.order_by(Timetable.jour, Timetable.heure_debut).all()



    # Organiser en grille jour x creneau

    jours = Timetable.jours_semaine()

    creneaux_list = sorted(set((c.heure_debut, c.heure_fin) for c in creneaux),

                           key=lambda x: x[0])

    if not creneaux_list:

        creneaux_list = Timetable.creneaux_horaires_defaut()



    grille = {}

    for jour in jours:

        grille[jour] = {}

        for hd, hf in creneaux_list:

            grille[jour][(hd, hf)] = None



    for c in creneaux:

        key = (c.heure_debut, c.heure_fin)

        if c.jour in grille and key in grille[c.jour]:

            grille[c.jour][key] = c



    year_id = _get_active_year_id(school_id)
    classes = Class.query.filter_by(school_id=school_id, actif=True, academic_year_id=year_id).order_by(Class.nom).all()

    years = AcademicYear.query.filter_by(school_id=school_id).order_by(AcademicYear.date_debut.desc()).all()

    from app.models.user import User

    teachers_all = User.query.filter_by(school_id=school_id, role='teacher', actif=True).order_by(User.nom).all()



    return render_template('academic/timetable.html',

                          jours=jours, creneaux_list=creneaux_list, grille=grille,

                          classes=classes, years=years, teachers=teachers_all,

                          class_id=class_id, teacher_id=teacher_id, year_id=year_id,

                          school_id=school_id)





@academic_bp.route('/timetable/manage')

@role_required('super_admin', 'school_admin')

def manage_timetable():

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    class_id = request.args.get('class_id', None, type=int)

    year_id = request.args.get('year_id', None, type=int) or _get_active_year_id(school_id)



    form = TimetableForm()

    form.load_choices(school_id)



    if class_id:

        form.class_id.data = class_id

        creneaux = Timetable.query.filter_by(

            school_id=school_id, class_id=class_id,

            academic_year_id=year_id

        ).order_by(Timetable.jour, Timetable.heure_debut).all()

    else:

        creneaux = []



    classes = Class.query.filter_by(school_id=school_id, actif=True, academic_year_id=year_id).order_by(Class.nom).all()

    years = AcademicYear.query.filter_by(school_id=school_id).order_by(AcademicYear.date_debut.desc()).all()



    return render_template('academic/timetable_manage.html',

                          form=form, creneaux=creneaux,

                          classes=classes, years=years,

                          class_id=class_id, year_id=year_id,

                          school_id=school_id)





@academic_bp.route('/timetable/add', methods=['POST'])

@role_required('super_admin', 'school_admin')

def add_entry():

    school_id = _get_school_id()

    form = TimetableForm()

    form.load_choices(school_id)



    if form.validate_on_submit():

        conflict = Timetable.query.filter_by(

            class_id=form.class_id.data,

            jour=form.jour.data,

            heure_debut=form.heure_debut.data

        ).first()

        if conflict:

            flash('Ce creneau est deja occupe pour cette classe.', 'danger')

        else:

            annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

            entry = Timetable(

                school_id=school_id,

                academic_year_id=annee.id if annee else None,

                class_id=form.class_id.data,

                subject_id=form.subject_id.data,

                teacher_id=form.teacher_id.data or None,

                jour=form.jour.data,

                heure_debut=form.heure_debut.data,

                heure_fin=form.heure_fin.data,

                salle=form.salle.data.strip() if form.salle.data else None,

            )

            db.session.add(entry)

            db.session.commit()

            flash('Creneau ajoute.', 'success')



    return redirect(url_for('academic.manage_timetable',

                           class_id=form.class_id.data,

                           school_id=school_id))





@academic_bp.route('/timetable/<int:entry_id>/delete', methods=['POST'])

@role_required('super_admin', 'school_admin')


def delete_entry(entry_id):

    entry = db.session.get(Timetable, entry_id)

    class_id = entry.class_id if entry else None

    if entry:

        db.session.delete(entry)

        db.session.commit()

        flash('Creneau supprime.', 'info')

    return redirect(url_for('academic.manage_timetable',

                           class_id=class_id,

                           school_id=_get_school_id()))





# ============================================================

# NOTES

# ============================================================



from app.models.grade import Grade

from app.academic.forms import GradeForm





@academic_bp.route('/grades')

@role_required('super_admin', 'school_admin', 'teacher')

def list_grades():

    """Saisie des notes — selection classe."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    class_id = request.args.get('class_id', None, type=int)

    cs_id = request.args.get('class_subject_id', None, type=int)

    trimestre = request.args.get('trimestre', 1, type=int)

    q = request.args.get('q', '').strip()



    year_id = _get_active_year_id(school_id)



    # Get school info for labels

    from app.models.school import School

    school = db.session.get(School, school_id)

    cycle = school.cycle if school else 'trimestre'

    div_label = 'Semestre' if cycle == 'semestre' else 'Trimestre'

    nb_div = school.nb_divisions if school else 3



    notes = []

    form = GradeForm()

    form.load_choices(school_id, class_id, trimestre=trimestre)  # Pass trimestre for cascade



    if class_id and cs_id:

        from app.models.user import User
        from app.models.student import StudentEnrollment, StudentProfile

        students_q = StudentEnrollment.query.filter_by(class_id=class_id, statut='actif')\
            .join(StudentProfile).join(User)

        if q:

            students_q = students_q.filter(

                db.or_(User.nom.ilike(f'%{q}%'), User.prenom.ilike(f'%{q}%'))

            )

        students = students_q.order_by(User.nom, User.prenom).all()



        notes_q = Grade.query.filter_by(

            class_subject_id=cs_id, trimestre=trimestre

        )

        if q:

            notes_q = notes_q.join(StudentProfile, Grade.student_profile_id == StudentProfile.id)\
                             .join(User, StudentProfile.user_id == User.id)\
                             .filter(db.or_(User.nom.ilike(f'%{q}%'), User.prenom.ilike(f'%{q}%')))

        notes = notes_q.order_by(Grade.created_at.desc()).all()

    else:

        students = []



    classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()

    cs_list = ClassSubject.query.filter_by(class_id=class_id).all() if class_id else []


    # Fallback sans JS: toutes les matieres et periodes de l'ecole

    from app.models.academic import Subject

    all_subjects = Subject.query.filter_by(school_id=school_id, actif=True).order_by(Subject.nom).all()

    all_periods = Period.query.join(Trimester).filter(

        Trimester.school_id == school_id

    ).order_by(Trimester.numero, Period.numero).all()


    return render_template('grades/entry.html',

                          form=form, notes=notes, students=students,

                          classes=classes, cs_list=cs_list,

                          all_subjects=all_subjects, all_periods=all_periods,

                          class_id=class_id, cs_id=cs_id, trimestre=trimestre,

                          q=q, school_id=school_id, div_label=div_label, nb_div=nb_div,

                          breadcrumbs=[("Saisie des Notes", None)])





@academic_bp.route('/grades/add', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin', 'teacher')

def add_grade():

    school_id = _get_school_id()

    form = GradeForm()

    class_id = request.args.get('class_id', None, type=int)

    form.load_choices(school_id, class_id)

    trimestre_num = request.args.get('trimestre', 1, type=int)


    # Helper pour charger le contexte complet (fallback serveur sans JS)

    def _grade_context(school_id, class_id, cs_id, trimestre_num, q=''):

        from app.models.school import School

        from app.models.academic import Subject

        school = db.session.get(School, school_id)

        cycle = school.cycle if school else 'trimestre'

        div_label = 'Semestre' if cycle == 'semestre' else 'Trimestre'

        nb_div = school.nb_divisions if school else 3

        classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()

        cs_list = ClassSubject.query.filter_by(class_id=class_id).all() if class_id else []

        all_subjects = Subject.query.filter_by(school_id=school_id, actif=True).order_by(Subject.nom).all()

        all_periods = Period.query.join(Trimester).filter(

            Trimester.school_id == school_id

        ).order_by(Trimester.numero, Period.numero).all()

        return dict(

            form=form, notes=[], students=[], classes=classes, cs_list=cs_list,

            all_subjects=all_subjects, all_periods=all_periods,

            class_id=class_id, cs_id=cs_id, trimestre=trimestre_num,

            q=q, school_id=school_id, div_label=div_label, nb_div=nb_div,

            breadcrumbs=[("Saisie des Notes", None)]

        )


    # GET: pre-remplir les selecteurs avec toutes les options (fallback sans JS)

    if request.method == 'GET':

        return render_template('grades/entry.html',

                              **_grade_context(school_id, class_id, form.class_subject_id.data, trimestre_num))


    if form.validate_on_submit():

        # Verifier que l'annee scolaire active n'est pas cloturee

        annee_active = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

        if not annee_active:

            flash('Aucune annee scolaire active. Veuillez d\'abord creer une annee scolaire.', 'danger')

            return redirect(url_for('academic.list_years', school_id=school_id))



        # Securite: convertir valeur en float avec try/except

        try:

            valeur = float(form.valeur.data)

        except (ValueError, TypeError):

            flash('La note doit etre un nombre valide.', 'danger')

            # Re-afficher le formulaire au lieu de rediriger

            classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()

            cs_list = ClassSubject.query.filter_by(class_id=class_id).all() if class_id else []

            notes = Grade.query.filter_by(class_subject_id=form.class_subject_id.data, trimestre=trimestre_num).order_by(Grade.created_at.desc()).all()

            from app.models.school import School

            school = db.session.get(School, school_id)

            cycle = school.cycle if school else 'trimestre'

            div_label = 'Semestre' if cycle == 'semestre' else 'Trimestre'

            nb_div = school.nb_divisions if school else 3

            return render_template('grades/entry.html',

                                  form=form, notes=notes, students=[], classes=classes, cs_list=cs_list,

                                  class_id=class_id, cs_id=form.class_subject_id.data, trimestre=trimestre_num,

                                  q='', school_id=school_id, div_label=div_label, nb_div=nb_div,

                                  breadcrumbs=[("Saisie des Notes", None)])



        # Conversion note_max

        try:

            note_max = float(form.note_max.data) if form.note_max.data else 20.0

        except (ValueError, TypeError):

            note_max = 20.0



        # Validation metier cote serveur

        if note_max <= 0:

            flash('La note maximale doit etre superieure a 0.', 'danger')

            return redirect(url_for('academic.list_grades',

                                   class_id=class_id,

                                   class_subject_id=form.class_subject_id.data,

                                   trimestre=trimestre_num,

                                   school_id=school_id))



        if valeur < 0 or valeur > note_max:

            flash(f'La note doit etre comprise entre 0 et {note_max}.', 'danger')

            return redirect(url_for('academic.list_grades',

                                   class_id=class_id,

                                   class_subject_id=form.class_subject_id.data,

                                   trimestre=trimestre_num,

                                   school_id=school_id))



        annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

        # Deriver le trimestre depuis la periode selectionnee

        period = db.session.get(Period, form.period_id.data) if form.period_id.data else None

        trimestre_num = period.trimestre.numero if period else trimestre_num

        grade = Grade(

            student_profile_id=form.student_profile_id.data,

            class_subject_id=form.class_subject_id.data,

            teacher_id=current_user.id if current_user.role == 'teacher' else None,

            school_id=school_id,

            academic_year_id=annee.id if annee else None,

            type_note=form.type_note.data,

            trimestre=trimestre_num,

            period_id=form.period_id.data,

            valeur=valeur,

            note_max=note_max,

            date_evaluation=form.date_evaluation.data,

            commentaire=form.commentaire.data.strip() if form.commentaire.data else None,

        )

        db.session.add(grade)

        db.session.commit()

        log_action('add_grade', table_name='grades', record_id=grade.id,

                  details=f'Note {grade.valeur}/{grade.note_max} — T{trimestre_num}, eleve #{grade.student_profile_id}')

        flash(f'Note enregistree — T{trimestre_num}, {period.nom if period else ""}.', 'success')



    return redirect(url_for('academic.list_grades',

                           class_id=class_id,

                           class_subject_id=form.class_subject_id.data,

                           trimestre=trimestre_num,

                           school_id=school_id))





@academic_bp.route('/grades/batch', methods=['POST'])

@role_required('super_admin', 'school_admin', 'teacher')

def batch_grades():

    """Saisie de plusieurs notes en une seule requete (JSON).

    Recoit: [{student_id, cs_id, period_id, valeur, type_note}]

    Retourne: JSON avec le resume (ok, errors, total).

    """

    # Protection CSRF pour requetes JSON
    from flask_wtf.csrf import validate_csrf
    try:
        validate_csrf(request.headers.get('X-CSRFToken', ''))
    except Exception:
        return {'ok': False, 'error': 'Token CSRF invalide'}, 400

    school_id = _get_school_id()

    if not school_id:

        return {'ok': False, 'error': 'Ecole non trouvee'}, 400



    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

    if not annee:

        return {'ok': False, 'error': 'Aucune annee scolaire active. Creez d\'abord une annee scolaire.'}, 400



    data = request.get_json(silent=True)

    if not data or not isinstance(data, list):

        return {'ok': False, 'error': 'JSON attendu: [{student_id, cs_id, period_id, valeur, type_note}]'}, 400



    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

    imported = 0

    errors = []



    for i, entry in enumerate(data):

        student_id = entry.get('student_id')

        cs_id = entry.get('cs_id')

        period_id = entry.get('period_id')

        valeur_raw = entry.get('valeur')

        type_note = entry.get('type_note', 'devoir')



        # Validation

        row_errs = []

        if not student_id:

            row_errs.append('student_id manquant')

        if not cs_id:

            row_errs.append('cs_id manquant')



        try:

            valeur = float(valeur_raw) if valeur_raw is not None else None

        except (ValueError, TypeError):

            row_errs.append(f'valeur invalide: {valeur_raw}')

            valeur = None



        if valeur is None:

            row_errs.append('valeur manquante')

        elif valeur < 0 or valeur > 20:

            row_errs.append(f'valeur hors limites: {valeur} (attendu 0-20)')



        if row_errs:

            errors.append({'index': i, 'entry': entry, 'errors': row_errs})

            continue



        # Verifier que l'eleve et le class_subject existent

        from app.models.student import StudentProfile

        student = db.session.get(StudentProfile, student_id)

        if not student:

            errors.append({'index': i, 'entry': entry, 'errors': [f'Eleve #{student_id} introuvable']})

            continue



        cs = db.session.get(ClassSubject, cs_id)

        if not cs:

            errors.append({'index': i, 'entry': entry, 'errors': [f'ClassSubject #{cs_id} introuvable']})

            continue



        # Deriver le trimestre depuis la periode

        period = db.session.get(Period, period_id) if period_id else None

        trimestre_num = period.trimestre.numero if period else 1



        grade = Grade(

            student_profile_id=student_id,

            class_subject_id=cs_id,

            teacher_id=current_user.id if current_user.role == 'teacher' else None,

            school_id=school_id,

            academic_year_id=annee.id if annee else None,

            type_note=type_note,

            trimestre=trimestre_num,

            period_id=period_id,

            valeur=valeur,

            note_max=20.0,

        )

        db.session.add(grade)

        imported += 1



    db.session.commit()



    return {

        'ok': True,

        'total': len(data),

        'imported': imported,

        'errors': errors,

        'summary': f'{imported}/{len(data)} notes enregistrees, {len(errors)} erreurs.'

    }





@academic_bp.route('/grades/<int:grade_id>/delete', methods=['POST'])

@role_required('super_admin', 'school_admin', 'teacher')


def delete_grade(grade_id):

    grade = db.session.get(Grade, grade_id)

    cs_id = grade.class_subject_id if grade else None

    if grade:

        db.session.delete(grade)

        db.session.commit()

        flash('Note supprimee.', 'info')

    return redirect(url_for('academic.list_grades',

                           class_subject_id=cs_id,

                           trimestre=request.args.get('trimestre', 1),

                           school_id=_get_school_id()))





# --- RELEVE ELEVE ---



@academic_bp.route('/grades/releve')

@role_required('super_admin', 'school_admin', 'teacher', 'parent', 'student')

def releve():

    """Releve de notes d'un eleve."""

    school_id = _get_school_id() or current_user.school_id

    active_year_id = _get_active_year_id(school_id)

    if not school_id:

        flash('Aucune ecole associee.', 'warning')

        return redirect(url_for('dashboard.index'))



    profile_id = request.args.get('profile_id', None, type=int)



    from app.models.student import StudentProfile

    if current_user.role == 'student':

        
        if current_user.role == 'student':
            profile = StudentProfile.query.filter_by(user_id=current_user.id).first()
        else:  # parent
            lien = StudentParent.query.filter_by(parent_id=current_user.id).first()
            profile = lien.student_profile if lien else None

        profile_id = profile.id if profile else None

    elif current_user.role == 'parent':

        profile_id = request.args.get('profile_id', None, type=int)



    if not profile_id:

        if current_user.role in ('student', 'parent'):

            flash('Aucun eleve selectionne.', 'warning')

            return redirect(url_for('dashboard.index'))

        flash('Veuillez selectionner un eleve.', 'warning')

        return redirect(url_for('students.list', school_id=school_id))



    profile = db.session.get(StudentProfile, profile_id)

    if not profile:

        flash('Eleve introuvable.', 'danger')

        return redirect(url_for('students.list', school_id=school_id))



    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

    enrollment = StudentEnrollment.query.filter_by(

        student_profile_id=profile_id, statut='actif'

    ).first()



    if not enrollment:

        flash('Aucune inscription active.', 'warning')

        return redirect(url_for('students.detail', profile_id=profile_id))



    class_id = enrollment.class_id

    year_id = enrollment.academic_year_id



    releve_data = []

    total_coef = 0.0

    total_pondere = 0.0



    for trimestre in [1, 2, 3]:

        matieres = []

        cs_list = ClassSubject.query.filter_by(class_id=class_id).order_by(ClassSubject.id).all()

        for cs in cs_list:

            moyenne = Grade.moyenne_eleve_matiere_trimestre(profile_id, cs.id, trimestre)

            notes_list = Grade.query.filter_by(

                student_profile_id=profile_id, class_subject_id=cs.id, trimestre=trimestre

            ).order_by(Grade.type_note, Grade.date_evaluation).all()

            matieres.append({

                'subject': cs.subject,

                'coefficient': cs.coefficient,

                'moyenne': moyenne,

                'notes': notes_list,

            })

            if moyenne is not None and trimestre == 1:  # Total only for T1 display, actual calc is per-trimestre

                pass



        mg = Grade.moyenne_generale_trimestre(profile_id, trimestre, year_id)

        releve_data.append({'trimestre': trimestre, 'matieres': matieres, 'moyenne_generale': mg})



    return render_template('grades/releve.html',

                          profile=profile, releve_data=releve_data,

                          enrollment=enrollment, school_id=school_id)





# ============================================================

# BULLETINS & DELIBERATIONS

# ============================================================



def _compute_bulletin_v1(class_id, trimestre):

    """Compatibilite: appelle la V2 avec trimester_id."""

    bulletin_data = _compute_bulletin(class_id, trimester_id=trimestre)

    if not bulletin_data or not bulletin_data.get('students'):

        return [], []

    cs_list = ClassSubject.query.filter_by(class_id=class_id).order_by(ClassSubject.id).all()

    bulletins = []

    for sr in bulletin_data['students']:

        user = sr['student']

        eleve = {

            'profile': sr.get('student_profile'),

            'eleve': user,

            'matieres': [],

            'moyenne_generale': sr['moyenne_generale'],

            'total_coef': sum(s['cs'].coefficient for s in sr['subjects'] if s['avg'] is not None),

            'total_points': (sr['moyenne_generale'] or 0) * sum(s['cs'].coefficient for s in sr['subjects'] if s['avg'] is not None),

            'decision': sr['appreciation'] if sr['moyenne_generale'] >= 10 else ('A repriser' if sr['moyenne_generale'] >= 8 else 'Redouble' if sr['moyenne_generale'] >= 5 else 'Exclu'),

            'decision_class': 'success' if sr['moyenne_generale'] >= 10 else ('warning' if sr['moyenne_generale'] >= 8 else 'danger' if sr['moyenne_generale'] >= 5 else 'dark'),

            'rang': sr['rank'],

        }

        for subj in sr['subjects']:

            eleve['matieres'].append({

                'subject': subj['subject'],

                'coefficient': subj['cs'].coefficient,

                'moyenne': subj['avg'],

                'nb_notes': len(subj['grades']),

            })

        bulletins.append(eleve)

    return bulletins, cs_list





@academic_bp.route('/bulletin')

@role_required('super_admin', 'school_admin')

def bulletin_list():

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))

    classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()

    classes_data = []

    for c in classes:

        nb_eleves = StudentEnrollment.query.filter_by(class_id=c.id, statut='actif').count()

        classes_data.append({'classe': c, 'nb_eleves': nb_eleves})

    return render_template('grades/bulletin_list.html', classes_data=classes_data, school_id=school_id,

                          breadcrumbs=[("Bulletins", None)])





@academic_bp.route('/bulletin/<int:class_id>/<int:trimestre>')

@role_required('super_admin', 'school_admin', 'teacher')

def bulletin_class(class_id, trimestre):

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))

    classe = db.session.get(Class, class_id)

    if not classe:

        flash('Classe introuvable.', 'danger')

        return redirect(url_for('academic.bulletin_list', school_id=school_id))

    bulletins, cs_list = _compute_bulletin_v1(class_id, trimestre)

    return render_template('grades/bulletin.html', classe=classe, trimestre=trimestre,

                          bulletins=bulletins, cs_list=cs_list, school_id=school_id)





@academic_bp.route('/bulletin/<int:class_id>/<int:trimestre>/pdf')

@role_required('super_admin', 'school_admin')

def bulletin_print(class_id, trimestre):

    school_id = _get_school_id()

    classe = db.session.get(Class, class_id)

    if not classe:

        flash('Classe introuvable.', 'danger')

        return redirect(url_for('academic.bulletin_list', school_id=school_id))

    bulletins, cs_list = _compute_bulletin_v1(class_id, trimestre)

    from datetime import datetime

    return render_template('grades/bulletin_print.html',

                          classe=classe, trimestre=trimestre,

                          bulletins=bulletins, cs_list=cs_list,

                          school_id=school_id, now=datetime.utcnow())



# ============================================================

# CONSEIL DE CLASSE / DELIBERATION

# ============================================================



@academic_bp.route('/deliberation')

@role_required('super_admin', 'school_admin')

def deliberation_list():

    """Liste des classes pour acceder aux deliberations."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))

    year_id = _get_active_year_id(school_id)

    classes = Class.query.filter_by(school_id=school_id, actif=True)

    if year_id:

        classes = classes.filter_by(academic_year_id=year_id)

    classes = classes.order_by(Class.nom).all()

    trimesters = Trimester.query.filter_by(school_id=school_id)

    if year_id:

        trimesters = trimesters.filter_by(academic_year_id=year_id)

    trimesters = trimesters.order_by(Trimester.numero).all()

    annee = AcademicYear.query.get(year_id) if year_id else None

    return render_template('academic/deliberation_list.html',

                          classes=classes, trimesters=trimesters,

                          annee=annee, school_id=school_id)





@academic_bp.route('/deliberation/<int:class_id>/<int:trimester_id>')

@role_required('super_admin', 'school_admin')

def deliberation_page(class_id, trimester_id):

    """Page de deliberation pour une classe et un trimestre."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    classe = db.session.get(Class, class_id)

    if not classe:

        flash('Classe introuvable.', 'danger')

        return redirect(url_for('academic.deliberation_list', school_id=school_id))



    trimester = db.session.get(Trimester, trimester_id)

    if not trimester:

        flash('Trimestre introuvable.', 'danger')

        return redirect(url_for('academic.deliberation_list', school_id=school_id))



    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()



    # Charger ou creer la deliberation

    deliberation = Deliberation.query.filter_by(

        class_id=class_id, trimester_id=trimester_id

    ).first()

    decisions_existantes = deliberation.decisions if deliberation else {}

    # Matieres a reprendre (repechage) existantes
    matieres_repechage_existantes = {}
    if deliberation and deliberation.matieres_repechage:
        try:
            matieres_repechage_existantes = json.loads(deliberation.matieres_repechage)
        except (json.JSONDecodeError, TypeError):
            matieres_repechage_existantes = {}

    # Calculer les bulletins

    bulletins, cs_list = _compute_bulletin_v1(class_id, trimester.numero)



    # Pour chaque eleve, calculer la decision automatique et fusionner avec les decisions enregistrees

    for b in bulletins:

        sp = b['profile']

        sid = str(sp.id)

        mg = b.get('moyenne_generale')

        # Decision automatique

        if mg is None:

            auto_decision = 'passe'

        elif mg >= 16:

            auto_decision = 'felicitations'

        elif mg >= 14:

            auto_decision = 'encouragement'

        elif mg >= 10:

            auto_decision = 'passe'

        elif mg >= 8:

            auto_decision = 'avertissement'

        else:

            auto_decision = 'redouble'

        b['auto_decision'] = auto_decision

        # Decision enregistree (ou auto)

        b['decision_actuelle'] = decisions_existantes.get(sid, auto_decision)



    return render_template('academic/deliberation.html',

                          classe=classe, trimester=trimester,

                          bulletins=bulletins, cs_list=cs_list,

                          deliberation=deliberation,

                          decisions_possibles=Deliberation.DECISIONS,

                          matieres_repechage_existantes=matieres_repechage_existantes,

                          school_id=school_id,

                          csrf_token=generate_csrf())





@academic_bp.route('/deliberation/save', methods=['POST'])

@role_required('super_admin', 'school_admin')

def deliberation_save():

    """Enregistre les decisions du conseil de classe."""

    # Protection CSRF pour requetes JSON
    from flask_wtf.csrf import validate_csrf
    try:
        validate_csrf(request.headers.get('X-CSRFToken', ''))
    except Exception:
        return {'success': False, 'error': 'Token CSRF invalide'}, 400

    school_id = _get_school_id()

    if not school_id:

        return {'ok': False, 'error': 'Ecole non trouvee'}, 400



    data = request.get_json(silent=True)

    if not data:

        return {'ok': False, 'error': 'JSON attendu'}, 400



    class_id = data.get('class_id')

    trimester_id = data.get('trimester_id')

    decisions = data.get('decisions', {})  # {"<student_id>": "<decision>"}
    matieres_repechage = data.get('matieres_repechage', {})  # {"<student_id>": [<subject_id>, ...]}



    if not class_id or not trimester_id:

        return {'ok': False, 'error': 'class_id et trimester_id requis'}, 400



    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

    if not annee:

        return {'ok': False, 'error': 'Aucune annee scolaire active'}, 400



    # Valider les decisions

    valid_decisions = [d[0] for d in Deliberation.DECISIONS]

    filtered = {}

    for sid, dec in decisions.items():

        if dec in valid_decisions:

            filtered[sid] = dec

    # Filtrer les matieres_repechage: ne garder que les etudiants avec decision=repechage
    filtered_matieres = {}
    for sid, matieres in matieres_repechage.items():
        if filtered.get(sid) == 'repechage' and isinstance(matieres, list) and matieres:
            filtered_matieres[sid] = [int(m) for m in matieres]



    deliberation = Deliberation.query.filter_by(

        class_id=class_id, trimester_id=trimester_id

    ).first()



    if deliberation:

        deliberation.decisions = filtered

        deliberation.matieres_repechage_dict = filtered_matieres

        deliberation.statut = data.get('statut', 'valide')

        deliberation.date_deliberation = datetime.utcnow()

        deliberation.created_by = current_user.id

    else:

        deliberation = Deliberation(

            school_id=school_id,

            academic_year_id=annee.id,

            class_id=class_id,

            trimester_id=trimester_id,

            statut=data.get('statut', 'valide'),

            date_deliberation=datetime.utcnow(),

            created_by=current_user.id,

            decision_json=json.dumps(filtered),

            matieres_repechage=json.dumps(filtered_matieres) if filtered_matieres else None,

        )

        db.session.add(deliberation)



    db.session.commit()

    # Notifier les parents des eleves concernes
    annonces_parents = 0
    if filtered:
        classe = db.session.get(Class, class_id)
        trimester_obj = db.session.get(Trimester, trimester_id)
        trimestre_label = trimester_obj.nom if trimester_obj else 'trimestre'
        
        from app.models.announcement import Announcement
        
        for sid_str, decision in filtered.items():
            sid = int(sid_str)
            sp = db.session.get(StudentProfile, sid)
            if not sp or not sp.user:
                continue
            
            eleve_nom = f'{sp.user.prenom} {sp.user.nom}'
            classe_nom = classe.nom if classe else 'N/A'
            
            bulletin_data = _compute_bulletin(class_id, trimester_id=trimester_id, filter_student_id=sid)
            mg = 0
            rang = 0
            total = 0
            if bulletin_data and bulletin_data.get('students'):
                sr = bulletin_data['students'][0]
                mg = sr['moyenne_generale']
                total = bulletin_data['total_eleves']
                rang = sr['rank']
            
            decision_labels = dict(Deliberation.DECISIONS)
            decision_label = decision_labels.get(decision, decision)
            
            if decision == 'passe':
                ligne_decision = 'Félicitations, votre enfant passe en classe supérieure.'
            elif decision == 'redouble':
                ligne_decision = 'Votre enfant est invité à redoubler. Un entretien avec le titulaire est recommandé.'
            elif decision == 'avertissement':
                ligne_decision = 'Votre enfant passe avec avertissement. Un suivi renforcé est nécessaire.'
            elif decision == 'encouragement':
                ligne_decision = 'Félicitations, votre enfant reçoit les encouragements du conseil de classe.'
            elif decision == 'felicitations':
                ligne_decision = 'Félicitations, votre enfant reçoit les félicitations du conseil de classe.'
            elif decision == 'repechage':
                # Construire la liste des matieres a reprendre
                matieres_ids = filtered_matieres.get(sid_str, [])
                matieres_lines = []
                if matieres_ids and bulletin_data and bulletin_data.get('students'):
                    sr = bulletin_data['students'][0]
                    for subj in sr['subjects']:
                        if subj['cs'].subject_id in matieres_ids:
                            note = subj['avg'] if subj['avg'] is not None else 'N/A'
                            matieres_lines.append(f'  - {subj["subject"].nom} (moyenne: {note}/20)')
                if matieres_lines:
                    ligne_decision = (
                        'Votre enfant est autorisé à repasser les épreuves suivantes :\n'
                        + '\n'.join(matieres_lines) +
                        '\n\nVotre enfant devra repasser ces épreuves avant la rentrée prochaine.'
                    )
                else:
                    ligne_decision = 'Votre enfant est autorisé à repasser certaines épreuves avant la rentrée prochaine.'
            else:
                ligne_decision = f'Décision : {decision_label}.'
            
            contenu = (
                'Cher Parent/Tuteur,\n\n'
                f'Le conseil de classe du {trimestre_label} s\'est tenu ce jour.\n\n'
                f'Concernant votre enfant {eleve_nom} en classe de {classe_nom} :\n'
                f'- Moyenne générale : {mg}/20\n'
                f'- Rang : {rang}/{total}\n'
                f'- Décision : {decision_label}\n\n'
                f'{ligne_decision}\n\n'
                'La Direction'
            )
            
            liens = StudentParent.query.filter_by(student_profile_id=sid).all()
            for lien in liens:
                parent = lien.parent
                if not parent:
                    continue
                
                annonce = Announcement(
                    school_id=school_id,
                    author_id=current_user.id,
                    academic_year_id=annee.id,
                    titre=f'Décision du conseil de classe — {eleve_nom}',
                    contenu=contenu,
                    priorite='importante',
                    target_user_ids=json.dumps([parent.id]),
                    published=True,
                )
                db.session.add(annonce)
                annonces_parents += 1
        
        if annonces_parents > 0:
            db.session.commit()

    log_action('deliberation_save', table_name='deliberations', record_id=deliberation.id,
              details=f'Deliberation classe #{class_id} T{trimester_id} — {len(filtered)} decisions')

    message = f'{len(filtered)} décisions sauvegardées'
    if annonces_parents > 0:
        message += f', {annonces_parents} parent(s) notifié(s).'
    else:
        message += '.'
    return {'ok': True, 'message': message, 'id': deliberation.id}


@academic_bp.route('/deliberation/<int:class_id>/<int:trimester_id>/decision')

@role_required('super_admin', 'school_admin')

def deliberation_get_decision(class_id, trimester_id):

    """Retourne la decision pour un eleve (API AJAX)."""

    student_id = request.args.get('student_id', type=int)

    if not student_id:

        return {'decision': None}



    deliberation = Deliberation.query.filter_by(

        class_id=class_id, trimester_id=trimester_id

    ).first()



    if deliberation:

        decision = deliberation.decisions.get(str(student_id))

        return {'decision': decision, 'statut': deliberation.statut}

    return {'decision': None, 'statut': None}





# ============================================================

# GESTION TRIMESTRES/SEMESTRES & PERIODES

# ============================================================



from flask_wtf import FlaskForm

from wtforms import StringField, FloatField, DateField, SelectField, SubmitField, FieldList, FormField, HiddenField

from wtforms.validators import DataRequired, Optional, NumberRange, Length





class PeriodSubForm(FlaskForm):

    period_id = HiddenField()

    nom = StringField('Nom', validators=[DataRequired(), Length(max=50)])

    date_debut = DateField('Debut', validators=[DataRequired()])

    date_fin = DateField('Fin', validators=[DataRequired()])

    coefficient = FloatField('Coef', validators=[DataRequired(), NumberRange(min=0.1, max=10)])

    type_evaluation = SelectField('Type', choices=[

        ('continue', 'Continue'), ('composition', 'Composition'), ('examen', 'Examen'),

    ])

    csrf_token = HiddenField()  # will be handled by the parent form





@academic_bp.route('/div-periods')

@role_required('super_admin', 'school_admin')

def manage_periods():

    """Gestion des trimestres/semestres et leurs periodes."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    from app.models.school import School

    school = db.session.get(School, school_id)

    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()



    if not annee:

        flash('Aucune annee scolaire active.', 'warning')

        year_id = None

        divisions = []

    else:

        year_id = annee.id

        divisions = Trimester.query.filter_by(academic_year_id=year_id).order_by(Trimester.numero).all()



    return render_template('academic/periods/manage.html',

                          school=school, annee=annee, divisions=divisions,

                          school_id=school_id,

                          breadcrumbs=[("Périodes", None)])





@academic_bp.route('/div-periods/<int:div_id>/edit', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def edit_periods(div_id):

    """Edition des periodes d'un trimestre/semestre."""

    school_id = _get_school_id()

    division = db.session.get(Trimester, div_id)

    if not division:

        flash('Division introuvable.', 'danger')

        return redirect(url_for('academic.manage_periods', school_id=school_id))



    from app.models.school import School

    school = db.session.get(School, school_id)

    div_label = school.division_label if school else 'Trimestre'



    # Generate CSRF token for raw form

    from flask_wtf.csrf import generate_csrf

    csrf_token = generate_csrf()



    if request.method == 'POST':
        # Validation CSRF
        from flask_wtf.csrf import validate_csrf
        try:
            validate_csrf(request.form.get('csrf_token', ''))
        except Exception:
            flash('Token CSRF invalide. Reessayez.', 'danger')
            return redirect(url_for('academic.manage_periods', school_id=school_id))

        # Update division name and dates

        division.nom = request.form.get('div_nom', division.nom)

        try:

            division.date_debut = DateField().process_formdata([request.form.get('div_debut')]) or division.date_debut

            division.date_fin = DateField().process_formdata([request.form.get('div_fin')]) or division.date_fin

        except Exception:

            pass

        # Update existing periods

        for period in division.periodes:

            pfx = f'p{period.id}_'

            new_nom = request.form.get(f'{pfx}nom')

            new_debut = request.form.get(f'{pfx}debut')

            new_fin = request.form.get(f'{pfx}fin')

            new_coef = request.form.get(f'{pfx}coef')

            new_type = request.form.get(f'{pfx}type')

            if new_nom:

                period.nom = new_nom

            if new_debut:

                try:

                    from datetime import datetime

                    period.date_debut = datetime.strptime(new_debut, '%Y-%m-%d').date()

                except Exception:

                    pass

            if new_fin:

                try:

                    period.date_fin = datetime.strptime(new_fin, '%Y-%m-%d').date()

                except Exception:

                    pass

            if new_coef:

                try:

                    period.coefficient = float(new_coef)

                except Exception:

                    pass

            if new_type:

                period.type_evaluation = new_type



        # Add new period

        new_nom = request.form.get('new_nom')

        if new_nom:

            new_debut = request.form.get('new_debut', '')

            new_fin = request.form.get('new_fin', '')

            new_coef = request.form.get('new_coef', '1')

            new_type = request.form.get('new_type', 'continue')

            try:

                from datetime import datetime

                new_num = max([p.numero for p in division.periodes] or [0]) + 1

                p = Period(

                    trimester_id=div_id,

                    numero=new_num,

                    nom=new_nom,

                    date_debut=datetime.strptime(new_debut, '%Y-%m-%d').date() if new_debut else division.date_debut,

                    date_fin=datetime.strptime(new_fin, '%Y-%m-%d').date() if new_fin else division.date_fin,

                    coefficient=float(new_coef),

                    type_evaluation=new_type,

                )

                db.session.add(p)

            except Exception as e:

                flash(f'Erreur nouvelle periode: {e}', 'danger')



        # Delete periods marked for removal

        to_delete = request.form.getlist('delete_periods')

        for pid in to_delete:

            period = db.session.get(Period, int(pid))

            if period:

                db.session.delete(period)



        db.session.commit()

        flash(f'Periodes de "{division.nom}" mises a jour.', 'success')

        return redirect(url_for('academic.manage_periods', school_id=school_id))



    return render_template('academic/periods/edit.html',

                          division=division, school=school,

                          div_label=div_label, school_id=school_id,

                          csrf_token=csrf_token,

                          breadcrumbs=[("Périodes", url_for('academic.manage_periods', school_id=school_id)), (division.nom, None)])



# ============================================================

# BULLETINS PAR PERIODE / TRIMESTRE / SEMESTRE

# ============================================================



from sqlalchemy import func





@academic_bp.route('/bulletin/period/<int:period_id>')

@role_required('super_admin', 'school_admin', 'teacher')

def bulletin_period(period_id):

    """Bulletin d'une periode pour une classe."""

    school_id = _get_school_id()

    period = db.session.get(Period, period_id)

    if not period:

        flash('Periode introuvable.', 'danger')

        return redirect(url_for('academic.manage_periods', school_id=school_id))



    trimester = period.trimestre

    from app.models.school import School

    school = db.session.get(School, school_id)

    div_label = school.division_label if school else 'Trimestre'



    class_id = request.args.get('class_id', None, type=int)

    selected_class = db.session.get(Class, class_id) if class_id else None



    if current_user.role == 'teacher':

        classes = Class.query.filter_by(school_id=school_id).join(

            ClassSubject, ClassSubject.class_id == Class.id

        ).filter(ClassSubject.teacher_id == current_user.id).distinct().all()

    else:

        classes = Class.query.filter_by(school_id=school_id).all()



    bulletin_data = None

    if selected_class:

        bulletin_data = _compute_bulletin(selected_class.id, period_id=period_id)



    return render_template('academic/bulletin/view.html',

                          period=period, trimester=trimester,

                          school=school, div_label=div_label,

                          classes=classes, selected_class=selected_class,

                          bulletin=bulletin_data, school_id=school_id)





@academic_bp.route('/bulletin/trimester/<int:trimester_id>')

@role_required('super_admin', 'school_admin', 'teacher')

def bulletin_trimester(trimester_id):

    """Bulletin d'un trimestre/semestre entier pour une classe."""

    school_id = _get_school_id()

    trimester = db.session.get(Trimester, trimester_id)

    if not trimester:

        flash('Division introuvable.', 'danger')

        return redirect(url_for('academic.manage_periods', school_id=school_id))



    from app.models.school import School

    school = db.session.get(School, school_id)

    div_label = school.division_label if school else 'Trimestre'



    class_id = request.args.get('class_id', None, type=int)

    selected_class = db.session.get(Class, class_id) if class_id else None



    if current_user.role == 'teacher':

        classes = Class.query.filter_by(school_id=school_id).join(

            ClassSubject, ClassSubject.class_id == Class.id

        ).filter(ClassSubject.teacher_id == current_user.id).distinct().all()

    else:

        classes = Class.query.filter_by(school_id=school_id).all()



    bulletin_data = None

    if selected_class:

        bulletin_data = _compute_bulletin(selected_class.id, trimester_id=trimester_id)



    return render_template('academic/bulletin/view.html',

                          period=None, trimester=trimester,

                          school=school, div_label=div_label,

                          classes=classes, selected_class=selected_class,

                          bulletin=bulletin_data, school_id=school_id)





@academic_bp.route('/bulletin/mes-bulletins')

@role_required('student')

def mes_bulletins():

    """Eleve consulte ses propres bulletins."""

    student = current_user.student_profile

    if not student:

        flash('Profil eleve introuvable.', 'danger')

        return redirect(url_for('dashboard.index'))



    return _student_bulletins(student)





@academic_bp.route('/bulletin/enfant/<int:enfant_id>')

@role_required('parent')

def bulletin_enfant(enfant_id):

    """Parent consulte le bulletin d'un enfant."""

    # Verifier que l'enfant appartient bien au parent

    sp = StudentProfile.query.get(enfant_id)

    if not sp:

        flash('Eleve introuvable.', 'danger')

        return redirect(url_for('dashboard.index'))



    # Check parent is linked to this child

    link = StudentParent.query.filter_by(parent_id=current_user.id, student_profile_id=sp.id).first()

    if not link:

        flash('Acces refuse.', 'danger')

        return redirect(url_for('dashboard.index'))



    return _student_bulletins(sp)





def _student_bulletins(student):

    """Affiche les bulletins disponibles pour un eleve."""

    # Trouver l'inscription active

    from app.models.student import StudentEnrollment

    enrollment = StudentEnrollment.query.filter_by(

        student_profile_id=student.id, statut='actif'

    ).first()

    if not enrollment:

        flash('Aucune inscription active.', 'warning')

        return redirect(url_for('dashboard.index'))



    school_id = enrollment.school_id

    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()



    if not annee:

        flash('Aucune annee scolaire active.', 'warning')

        divisions = []

        periods = []

    else:

        divisions = Trimester.query.filter_by(academic_year_id=annee.id).order_by(Trimester.numero).all()

        periods = Period.query.join(Trimester).filter(

            Trimester.academic_year_id == annee.id

        ).order_by(Trimester.numero, Period.numero).all()



    from app.models.school import School

    school = db.session.get(School, school_id)

    div_label = school.division_label if school else 'Trimestre'



    # Pre-compute bulletin for each period and trimester

    bulletins_period = {}

    for p in periods:

        bulletins_period[p.id] = _compute_bulletin(

            enrollment.class_id,

            period_id=p.id,

            filter_student_id=student.id

        )



    bulletins_div = {}

    for d in divisions:

        bulletins_div[d.id] = _compute_bulletin(

            enrollment.class_id,

            trimester_id=d.id,

            filter_student_id=student.id

        )



    return render_template('academic/bulletin/student.html',

                          student=student, enrollment=enrollment,

                          school=school, annee=annee,

                          div_label=div_label, divisions=divisions,

                          periods=periods,

                          bulletins_period=bulletins_period,

                          bulletins_div=bulletins_div,

                          school_id=school_id)





def _compute_bulletin(class_id, period_id=None, trimester_id=None, filter_student_id=None):

    """

    Calcule les moyennes par matiere et par eleve.

    - period_id: bulletin d'une periode

    - trimester_id: bulletin d'un trimestre entier (toutes les periodes combinées)

    - filter_student_id: pour un seul eleve

    Returns:

        {

            'students': [

                {

                    'student': StudentProfile,

                    'subjects': [

                        {'subject': Subject, 'cs': ClassSubject, 'avg': float, 'grades': [...], 'max': float},

                    ],

                    'moyenne_generale': float,

                    'rank': int,

                    'appreciation': str

                }

            ],

            'periods': [Period, ...] (if trimester bulletin),

            'total_points': float,

            'max_possible': float

        }

    """

    # Get all class subjects

    class_subjects = ClassSubject.query.filter_by(class_id=class_id).order_by(ClassSubject.id).all()



    # Get all enrolled students

    from app.models.student import StudentEnrollment

    enrollments = StudentEnrollment.query.filter_by(class_id=class_id, statut='actif').all()

    students = [(e.student_profile, e.student) for e in enrollments]  # (StudentProfile, User)

    if filter_student_id:

        students = [(sp, user) for sp, user in students if sp.id == filter_student_id]

    if not students:

        return None



    # Get periods

    if trimester_id:

        periods = Period.query.filter_by(trimester_id=trimester_id).order_by(Period.numero).all()

    elif period_id:

        period = db.session.get(Period, period_id)

        periods = [period] if period else []

    else:

        return None



    if not periods:

        return None



    student_results = []



    for sp, user in students:

        subject_results = []



        for cs in class_subjects:

            # Get all grades for this student/subject/period(s)

            query = Grade.query.filter(

                Grade.student_profile_id == sp.id,

                Grade.class_subject_id == cs.id,

                Grade.period_id.in_([p.id for p in periods])

            )



            grades = query.order_by(Grade.date_evaluation).all()



            if not grades:

                subject_results.append({

                    'subject': cs.subject,

                    'cs': cs,

                    'avg': None,

                    'grades': [],

                    'total': 0,

                    'max': 20,

                })

                continue



            # Compute weighted average

            total_weighted = 0.0

            total_weight = 0.0

            grade_details = []

            for g in grades:

                # Use the period's coefficient as weight

                p_coef = 1.0

                if g.period and g.period.coefficient:

                    p_coef = g.period.coefficient

                weighted = g.valeur * p_coef

                max_w = g.note_max * p_coef

                total_weighted += weighted

                total_weight += p_coef

                grade_details.append({

                    'valeur': g.valeur,

                    'max': g.note_max,

                    'coef': p_coef,

                    'date': g.date_evaluation.strftime('%d/%m') if g.date_evaluation else '',

                    'type': g.type_note,

                    'commentaire': g.commentaire or ''

                })



            avg = round(total_weighted / total_weight, 2) if total_weight > 0 else 0

            max_note = round(max(g.note_max for g in grades), 2) if grades else 20



            subject_results.append({

                'subject': cs.subject,

                'cs': cs,

                'avg': avg,

                'grades': grade_details,

                'total': round(total_weighted, 2),

                'max': max_note,

            })



        # Calculate general average

        valid_subjects = [s for s in subject_results if s['avg'] is not None]

        if valid_subjects:

            total_weighted_avg = sum(s['avg'] * s['cs'].coefficient for s in valid_subjects)

            total_coef = sum(s['cs'].coefficient for s in valid_subjects)

            moyenne = round(total_weighted_avg / total_coef, 2) if total_coef > 0 else 0

        else:

            moyenne = 0



        student_results.append({

            'student': user,

            'student_profile': sp,

            'subjects': subject_results,

            'moyenne_generale': moyenne,

        })



    # Sort by moyenne and assign ranks

    student_results.sort(key=lambda x: x['moyenne_generale'], reverse=True)

    for i, sr in enumerate(student_results):

        sr['rank'] = i + 1

        moy = sr['moyenne_generale']

        if moy >= 16:

            sr['appreciation'] = 'Tres Bien'

        elif moy >= 14:

            sr['appreciation'] = 'Bien'

        elif moy >= 12:

            sr['appreciation'] = 'Assez Bien'

        elif moy >= 10:

            sr['appreciation'] = 'Passable'

        else:

            sr['appreciation'] = 'Insuffisant'



    return {

        'students': student_results,

        'periods': periods,

        'total_eleves': len(student_results),

        'total_subjects': len(class_subjects),

    }





@academic_bp.route('/bulletins')

@role_required('super_admin', 'school_admin', 'teacher')

def bulletins():

    """Page d'accueil des bulletins - liste les periodes/trimestres disponibles."""

    school_id = _get_school_id()

    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

    if not annee:

        flash('Aucune annee scolaire active.', 'warning')

        return redirect(url_for('dashboard.index'))



    from app.models.school import School

    school = db.session.get(School, school_id)

    div_label = school.division_label if school else 'Trimestre'



    divisions = Trimester.query.filter_by(academic_year_id=annee.id).order_by(Trimester.numero).all()



    # Get classes for filter

    if current_user.role == 'teacher':

        classes = Class.query.filter_by(school_id=school_id).join(

            ClassSubject, ClassSubject.class_id == Class.id

        ).filter(ClassSubject.teacher_id == current_user.id).distinct().all()

    else:

        classes = Class.query.filter_by(school_id=school_id).all()



    return render_template('academic/bulletin/list.html',

                          school=school, annee=annee, div_label=div_label,

                          divisions=divisions, classes=classes, school_id=school_id,

                          breadcrumbs=[("Bulletins", None)])



@academic_bp.route('/bulletins-parent')

@role_required('parent')

def bulletins_parent():

    """Parent: liste des enfants pour acceder aux bulletins."""

    enfants_links = StudentParent.query.filter_by(parent_id=current_user.id).all()

    enfants = [link.student_profile for link in enfants_links if link.student_profile]

    if not enfants:

        flash('Aucun enfant associe.', 'warning')

        return redirect(url_for('dashboard.index'))



    # Pre-compute active enrollments

    enfants_data = []

    for enfant in enfants:

        enrollment = StudentEnrollment.query.filter_by(

            student_profile_id=enfant.id, statut='actif'

        ).first()

        enfants_data.append({'profile': enfant, 'enrollment': enrollment})



    return render_template('academic/bulletin/parent.html',

                          parent=current_user, enfants_data=enfants_data)





# ============================================================

# ABSENCES & RETARDS

# ============================================================



from app.models.attendance import Attendance





@academic_bp.route('/attendance')

@role_required('super_admin', 'school_admin', 'teacher')

def list_attendance():

    """Liste des absences/retards filtrable par classe."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    class_id = request.args.get('class_id', None, type=int)

    year_id = _get_active_year_id(school_id)



    query = Attendance.query.filter_by(school_id=school_id)

    if class_id:

        query = query.filter_by(class_id=class_id)

    if year_id:

        query = query.filter_by(academic_year_id=year_id)



    attendances = query.order_by(Attendance.date.desc(), Attendance.created_at.desc()).limit(200).all()



    classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()

    from datetime import date as date_type

    from app.models.user import User

    from flask_wtf.csrf import generate_csrf

    # Eleves filtres par classe si une classe est selectionnee, tries alphabetiquement
    if class_id:
        from app.models.student import StudentEnrollment as SE2
        student_ids = db.session.query(SE2.student_profile_id).filter_by(class_id=class_id, statut='actif').all()
        profile_ids = [s[0] for s in student_ids]
        students = User.query.join(StudentProfile, User.id == StudentProfile.user_id)\
            .filter(User.school_id == school_id, User.role == 'student', User.actif == True,
                    StudentProfile.id.in_(profile_ids))\
            .order_by(User.nom, User.prenom).all()
    else:
        students = User.query.filter_by(school_id=school_id, role='student', actif=True).order_by(User.nom, User.prenom).all()



    return render_template('academic/attendance/list.html',

                          attendances=attendances, classes=classes,

                          students=students, class_id=class_id,

                          school_id=school_id, today=date_type.today(),

                          csrf_token=generate_csrf(),

                          breadcrumbs=[("Absences & Retards", None)])





@academic_bp.route('/attendance/add', methods=['POST'])

@role_required('super_admin', 'school_admin', 'teacher')

def add_attendance():

    """Marquer une absence/retard/exclusion."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))




    # Validation CSRF
    from flask_wtf.csrf import validate_csrf
    try:
        validate_csrf(request.form.get('csrf_token', ''))
    except Exception:
        flash('Token CSRF invalide. Reessayez.', 'danger')
        return redirect(url_for('dashboard.index'))

    from datetime import date as date_type



    student_profile_id = request.form.get('student_profile_id', type=int)

    date_str = request.form.get('date', '').strip()

    type_a = request.form.get('type', 'absence')

    motif = request.form.get('motif', '').strip() or None

    class_id = request.form.get('class_id', type=int) or None



    if not student_profile_id:

        flash('Veuillez selectionner un eleve.', 'danger')

        return redirect(url_for('academic.list_attendance', school_id=school_id))



    try:

        date_val = date_type.fromisoformat(date_str) if date_str else date_type.today()

    except ValueError:

        date_val = date_type.today()



    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()



    att = Attendance(

        student_profile_id=student_profile_id,

        school_id=school_id,

        academic_year_id=annee.id if annee else None,

        class_id=class_id,

        date=date_val,

        type=type_a,

        motif=motif,

        created_by=current_user.id,

    )

    db.session.add(att)

    db.session.commit()

    flash(f'{att.type_label} enregistree.', 'success')

    return redirect(url_for('academic.list_attendance', school_id=school_id, class_id=class_id))





@academic_bp.route('/attendance/<int:attendance_id>/toggle', methods=['POST'])

@role_required('super_admin', 'school_admin', 'teacher')

def toggle_attendance(attendance_id):

    """Basculer justifie / non justifie."""


    att = db.session.get(Attendance, attendance_id)

    if not att:

        flash('Absence introuvable.', 'danger')

        return redirect(url_for('academic.list_attendance', school_id=_get_school_id()))



    att.justifie = not att.justifie

    db.session.commit()

    flash(f'Absence marquee comme {att.statut_label}.', 'info')

    return redirect(url_for('academic.list_attendance', school_id=att.school_id, class_id=att.class_id))





@academic_bp.route('/attendance/<int:attendance_id>/delete', methods=['POST'])

@role_required('super_admin', 'school_admin', 'teacher')

def delete_attendance(attendance_id):

    """Supprimer une absence."""


    att = db.session.get(Attendance, attendance_id)

    school_id = att.school_id if att else _get_school_id()

    class_id = att.class_id if att else None

    if att:

        db.session.delete(att)

        db.session.commit()

        flash('Absence supprimee.', 'info')

    return redirect(url_for('academic.list_attendance', school_id=school_id, class_id=class_id))






# ============================================================

# ABSENCES PARENT (LECTURE SEULE)

# ============================================================

@academic_bp.route('/attendance/parent')
@role_required('parent')
def parent_attendance():
    """Absences des enfants d'un parent — lecture seule."""
    school_id = current_user.school_id
    if not school_id:
        flash('Aucune ecole associee.', 'warning')
        return redirect(url_for('dashboard.index'))

    from app.models.student import StudentProfile, StudentEnrollment, StudentParent
    from app.models.user import User

    # Recuperer les enfants du parent connecte
    liens = StudentParent.query.filter_by(parent_id=current_user.id).all()
    child_profile_ids = [l.student_profile_id for l in liens]

    if not child_profile_ids:
        flash('Aucun enfant associe a votre compte.', 'info')
        return redirect(url_for('dashboard.parent'))

    # Recuperer les absences de tous ses enfants
    query = Attendance.query.filter(
        Attendance.student_profile_id.in_(child_profile_ids),
        Attendance.school_id == school_id
    )

    year_id = _get_active_year_id(school_id)
    if year_id:
        query = query.filter_by(academic_year_id=year_id)

    attendances = query.order_by(Attendance.date.desc(), Attendance.created_at.desc()).all()

    # Grouper par enfant pour affichage clair
    enfants_absences = {}
    for lien in liens:
        profile = lien.student_profile
        if not profile:
            continue
        enrollment = StudentEnrollment.query.filter_by(
            student_profile_id=profile.id, statut='actif'
        ).first()
        enfants_absences[profile.id] = {
            'profile': profile,
            'enrollment': enrollment,
            'absences': [],
        }
    for att in attendances:
        if att.student_profile_id in enfants_absences:
            enfants_absences[att.student_profile_id]['absences'].append(att)

    return render_template('academic/attendance/parent.html',
                          enfants_absences=enfants_absences,
                          total_absences=len(attendances),
                          school_id=school_id,
                          breadcrumbs=[("Absences de mes enfants", None)])



# ============================================================

# PDF BULLETIN GENERATION

# ============================================================



from app.utils.pdf_bulletin import generate_bulletin_pdf, generate_student_bulletin_pdf
from app.utils.helpers import _get_school_id





@academic_bp.route('/academic/bulletin/pdf/<type>/<int:id>')

@role_required('super_admin', 'school_admin', 'teacher')

def bulletin_pdf(type, id):

    """Generate PDF bulletin for a class (period or trimester)."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    from app.models.school import School

    school = db.session.get(School, school_id)

    class_id = request.args.get('class_id', None, type=int)



    if not class_id:

        flash('Veuillez selectionner une classe.', 'warning')

        if type == 'period':

            return redirect(url_for('academic.bulletin_period', period_id=id, school_id=school_id))

        else:

            return redirect(url_for('academic.bulletin_trimester', trimester_id=id, school_id=school_id))



    selected_class = db.session.get(Class, class_id)

    if not selected_class:

        flash('Classe introuvable.', 'danger')

        return redirect(url_for('academic.manage_periods', school_id=school_id))



    if type == 'period':

        period = db.session.get(Period, id)

        if not period:

            flash('Periode introuvable.', 'danger')

            return redirect(url_for('academic.manage_periods', school_id=school_id))

        trimester = period.trimestre

        bulletin_data = _compute_bulletin(selected_class.id, period_id=id)

    elif type == 'trimester':

        trimester = db.session.get(Trimester, id)

        if not trimester:

            flash('Division introuvable.', 'danger')

            return redirect(url_for('academic.manage_periods', school_id=school_id))

        period = None

        bulletin_data = _compute_bulletin(selected_class.id, trimester_id=id)

    else:

        flash('Type invalide.', 'danger')

        return redirect(url_for('academic.manage_periods', school_id=school_id))



    if not bulletin_data:

        flash('Aucune donnee de bulletin disponible.', 'warning')

        if type == 'period':

            return redirect(url_for('academic.bulletin_period', period_id=id, school_id=school_id, class_id=class_id))

        else:

            return redirect(url_for('academic.bulletin_trimester', trimester_id=id, school_id=school_id, class_id=class_id))



    pdf_bytes = generate_bulletin_pdf(bulletin_data, school, period=period, trimester=trimester)



    # Build a clean filename

    div_label = school.division_short

    if period:

        filename = f'Bulletin_{selected_class.nom}_{div_label}{trimester.numero}_{period.nom}.pdf'

    else:

        filename = f'Bulletin_{selected_class.nom}_{div_label}{trimester.numero}.pdf'

    filename = filename.replace(' ', '_').replace('/', '-')



    return send_file(

        io.BytesIO(pdf_bytes),

        mimetype='application/pdf',

        as_attachment=True,

        download_name=filename,

    )





@academic_bp.route('/academic/bulletin/pdf-student/<int:student_id>/<int:div_id>')

@role_required('super_admin', 'school_admin', 'teacher')

def bulletin_pdf_student(student_id, div_id):

    """Generate individual student PDF bulletin.

    div_id can be a period_id or trimester_id (auto-detected).

    """

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))



    from app.models.school import School

    school = db.session.get(School, school_id)



    # Get student profile

    sp = db.session.get(StudentProfile, student_id)

    if not sp:

        flash('Eleve introuvable.', 'danger')

        return redirect(url_for('students.list', school_id=school_id))



    # Find active enrollment

    enrollment = StudentEnrollment.query.filter_by(

        student_profile_id=sp.id, statut='actif'

    ).first()

    if not enrollment:

        flash('Aucune inscription active.', 'warning')

        return redirect(url_for('students.detail', profile_id=sp.id))



    # Auto-detect: try period first, then trimester

    period = db.session.get(Period, div_id)

    trimester = None

    is_period = False



    if period:

        is_period = True

        trimester = period.trimestre

        bulletin_data = _compute_bulletin(

            enrollment.class_id, period_id=div_id, filter_student_id=sp.id

        )

    else:

        trimester = db.session.get(Trimester, div_id)

        if trimester:

            bulletin_data = _compute_bulletin(

                enrollment.class_id, trimester_id=div_id, filter_student_id=sp.id

            )

        else:

            flash('Periode ou division introuvable.', 'danger')

            return redirect(url_for('academic.mes_bulletins'))



    if not bulletin_data or not bulletin_data.get('students'):

        flash('Aucune note disponible pour cet eleve.', 'warning')

        return redirect(url_for('academic.mes_bulletins'))



    pdf_bytes = generate_bulletin_pdf(bulletin_data, school, period=period, trimester=trimester)



    div_label = school.division_short

    student_name = f'{sp.user.prenom}_{sp.user.nom}'.replace(' ', '_')

    if is_period:

        filename = f'Bulletin_{student_name}_{div_label}{trimester.numero}_{period.nom}.pdf'

    else:

        filename = f'Bulletin_{student_name}_{div_label}{trimester.numero}.pdf'

    filename = filename.replace(' ', '_').replace('/', '-')



    return send_file(

        io.BytesIO(pdf_bytes),

        mimetype='application/pdf',

        as_attachment=True,

        download_name=filename,

    )



# ============================================================
# CENTRE D'EXPORT UNIFIÉ
# ============================================================

def _export_style():
    """Retourne les styles Excel standards pour les exports."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="2B579A", end_color="2B579A", fill_type="solid")
    header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    cell_alignment = Alignment(vertical='center')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    alt_fill = PatternFill(start_color="EBF1F8", end_color="EBF1F8", fill_type="solid")
    return header_font, header_fill, header_alignment, cell_alignment, thin_border, alt_fill


def _apply_excel_style(ws, headers, data_rows, col_widths=None):
    """Applique le style standardise a une feuille Excel."""
    header_font, header_fill, h_align, c_align, border, alt_fill = _export_style()

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = h_align

    for row_idx, row_data in enumerate(data_rows, 2):
        for col, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.border = border
            cell.alignment = c_align
            if row_idx % 2 == 0:
                cell.fill = alt_fill

    if col_widths is None:
        for col_cells in ws.columns:
            max_len = max((len(str(c.value or '')) for c in col_cells), default=10)
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 3, 35)
    else:
        from openpyxl.utils import get_column_letter
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = 'A2'


@academic_bp.route('/exports')
@role_required('super_admin', 'school_admin', 'teacher')
def exports_center():
    """Centre d'export — choix du type et filtres."""
    school_id = _get_school_id()
    if not school_id:
        flash('Veuillez selectionner une ecole.', 'warning')
        return redirect(url_for('dashboard.index'))

    year_id = _get_active_year_id(school_id)
    classes = Class.query.filter_by(school_id=school_id, actif=True, academic_year_id=year_id).order_by(Class.nom).all()
    years = AcademicYear.query.filter_by(school_id=school_id).order_by(AcademicYear.date_debut.desc()).all()
    subjects = Subject.query.filter_by(school_id=school_id, actif=True).order_by(Subject.nom).all()
    trimesters = Trimester.query.filter_by(school_id=school_id, academic_year_id=year_id).order_by(Trimester.numero).all()

    from app.models.finance import FeeType
    fee_types = FeeType.query.filter_by(school_id=school_id, actif=True).order_by(FeeType.nom).all()

    return render_template('academic/exports.html',
                          classes=classes, years=years, subjects=subjects,
                          trimesters=trimesters, fee_types=fee_types,
                          school_id=school_id, year_id=year_id,
                          breadcrumbs=[("Centre d'Export", None)])


# ============================================================
# EXPORT ÉLÈVES
# ============================================================

@academic_bp.route('/export/students')
@role_required('super_admin', 'school_admin')
def export_students():
    """Exporte la liste des eleves avec filtres.
    Filtres: class_id (optionnel), year_id (optionnel)
    Colonnes: Matricule, Nom, Prenom, Sexe, Date Naissance, Classe, Contact Parent
    """
    import openpyxl
    school_id = _get_school_id()
    class_id = request.args.get('class_id', type=int)
    year_id = request.args.get('year_id', type=int) or _get_active_year_id(school_id)

    query = StudentProfile.query.join(
        StudentEnrollment, StudentProfile.id == StudentEnrollment.student_profile_id
    ).filter(StudentEnrollment.statut == 'actif')

    if class_id:
        query = query.filter(StudentEnrollment.class_id == class_id)
    if year_id:
        query = query.filter(StudentEnrollment.academic_year_id == year_id)

    enrollments = query.order_by(StudentProfile.id).all()

    if not enrollments:
        flash('Aucun eleve a exporter.', 'warning')
        return redirect(url_for('academic.exports_center', school_id=school_id))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Eleves"

    headers = ['Matricule', 'Nom', 'Prenom', 'Sexe', 'Date Naissance', 'Classe', 'Contact Parent']
    data_rows = []

    for sp in enrollments:
        user = sp.user
        enrollment = StudentEnrollment.query.filter_by(
            student_profile_id=sp.id, statut='actif'
        ).first()
        parent_link = StudentParent.query.filter_by(student_profile_id=sp.id).first()
        contact = ''
        if parent_link and parent_link.parent:
            contact = parent_link.parent.telephone or parent_link.parent.email or ''

        data_rows.append([
            sp.matricule or '',
            user.nom if user else '',
            user.prenom if user else '',
            sp.sexe or '',
            sp.date_naissance.strftime('%d/%m/%Y') if sp.date_naissance else '',
            enrollment.classe.nom if enrollment else '',
            contact,
        ])

    _apply_excel_style(ws, headers, data_rows)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    classe_nom = f"_{Class.query.get(class_id).nom}" if class_id else ""
    filename = f"Liste_Eleves{classe_nom.replace(' ', '_')}.xlsx"
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)


# ============================================================
# EXPORT NOTES (DÉTAILLÉ)
# ============================================================

@academic_bp.route('/export/grades')
@role_required('super_admin', 'school_admin', 'teacher')
def export_grades():
    """Exporte le releve detaille des notes avec filtres.
    Filtres: class_id, period_id, subject_id (tous optionnels)
    Colonnes: Matricule, Eleve, Classe, Matiere, Note/20, Note Max, Periode, Date
    """
    import openpyxl
    school_id = _get_school_id()
    class_id = request.args.get('class_id', type=int)
    period_id = request.args.get('period_id', type=int)
    subject_id = request.args.get('subject_id', type=int)

    query = Grade.query.filter_by(school_id=school_id).join(
        Grade.class_subject
    ).join(
        ClassSubject.classe
    )

    if class_id:
        query = query.filter(ClassSubject.class_id == class_id)
    if period_id:
        query = query.filter(Grade.period_id == period_id)
    if subject_id:
        query = query.filter(ClassSubject.subject_id == subject_id)

    grades = query.order_by(Grade.student_profile_id, Grade.class_subject_id, Grade.date_evaluation).all()

    if not grades:
        flash('Aucune note a exporter.', 'warning')
        return redirect(url_for('academic.exports_center', school_id=school_id))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Notes"

    headers = ['Matricule', 'Eleve', 'Classe', 'Matiere', 'Note/20', 'Note Max', 'Periode', 'Date']
    data_rows = []

    for g in grades:
        sp = g.student_profile
        user = sp.user if sp else None
        cs = g.class_subject
        classe = cs.classe if cs else None
        period = db.session.get(Period, g.period_id) if g.period_id else None
        period_nom = period.nom if period else f"T{g.trimestre}"

        data_rows.append([
            sp.matricule if sp else '',
            f"{user.prenom} {user.nom}" if user else '',
            classe.nom if classe else '',
            cs.subject.nom if cs and cs.subject else '',
            round(g.valeur, 2),
            round(g.note_max, 2),
            period_nom,
            g.date_evaluation.strftime('%d/%m/%Y') if g.date_evaluation else '',
        ])

    _apply_excel_style(ws, headers, data_rows)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = "Releve_Notes.xlsx"
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)


# ============================================================
# EXPORT BULLETINS (SYNTHÈSE PAR CLASSE)
# ============================================================

@academic_bp.route('/export/bulletins')
@role_required('super_admin', 'school_admin', 'teacher')
def export_bulletins():
    """Exporte la synthese des bulletins par classe.
    Filtres: class_id (obligatoire), trimester_id (optionnel)
    Colonnes: Matricule, Eleve, Classe, Moyenne Generale, Rang, Decision
    """
    import openpyxl
    from app.models.academic import Trimester
    school_id = _get_school_id()
    class_id = request.args.get('class_id', type=int)
    trimester_id = request.args.get('trimester_id', type=int)

    # Auto-detect class if not provided
    if not class_id:
        first_class = Class.query.filter_by(school_id=school_id).order_by(Class.nom).first()
        if not first_class:
            flash('Aucune classe disponible.', 'warning')
            return redirect(url_for('academic.exports_center', school_id=school_id))
        class_id = first_class.id

    # Auto-detect trimester if not provided
    if not trimester_id:
        first_trimester = Trimester.query.filter_by(school_id=school_id).order_by(Trimester.numero).first()
        trimester_id = first_trimester.id if first_trimester else None

    bulletin_data = _compute_bulletin(class_id, trimester_id=trimester_id)

    if not bulletin_data or not bulletin_data.get('students'):
        flash('Aucune donnee de bulletin disponible.', 'warning')
        return redirect(url_for('academic.exports_center', school_id=school_id))

    classe = db.session.get(Class, class_id)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bulletins"

    headers = ['Matricule', 'Eleve', 'Classe', 'Moyenne Generale', 'Rang', 'Decision']
    data_rows = []

    for sr in bulletin_data['students']:
        user = sr['student']
        sp = sr['student_profile']
        mg = sr['moyenne_generale']
        rang = f"{sr['rank']}/{bulletin_data['total_eleves']}"
        decision = sr['appreciation']

        data_rows.append([
            sp.matricule if sp else '',
            f"{user.prenom} {user.nom}" if user else '',
            classe.nom if classe else '',
            mg,
            rang,
            decision,
        ])

    _apply_excel_style(ws, headers, data_rows)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    trimester = db.session.get(Trimester, trimester_id) if trimester_id else None
    div_suffix = f"_T{trimester.numero}" if trimester else ""
    filename = f"Bulletins_{classe.nom.replace(' ', '_')}{div_suffix}.xlsx"
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)


# ============================================================
# IMPORT ÉLÈVES (BULK)
# ============================================================

IMPORT_COLUMNS = [
    'matricule', 'nom', 'prenom', 'date_naissance', 'sexe',
    'classe', 'adresse', 'email_eleve',
    'nom_parent', 'prenom_parent', 'telephone_parent', 'email_parent',
    'relation_parent'
]

IMPORT_COLUMNS_FRIENDLY = {
    'matricule': 'Matricule (laissez vide pour auto)',
    'nom': 'Nom eleve *',
    'prenom': 'Prenom eleve *',
    'date_naissance': 'Date naissance (AAAA-MM-JJ)',
    'sexe': 'Sexe (M/F)',
    'classe': 'Classe (ex: 6eme A) *',
    'adresse': 'Adresse',
    'email_eleve': 'Email eleve',
    'nom_parent': 'Nom parent/tuteur *',
    'prenom_parent': 'Prenom parent/tuteur',
    'telephone_parent': 'Telephone parent',
    'email_parent': 'Email parent',
    'relation_parent': 'Lien (pere/mere/tuteur)',
}


def _auto_matricule(school_id, year_id):
    """Genere un matricule unique: ANNEE-ECOLE-0001"""
    year = db.session.get(AcademicYear, year_id)
    year_suffix = str(year.date_debut.year)[-2:] if year and year.date_debut else datetime.utcnow().strftime('%y')
    prefix = f"{year_suffix}{school_id:03d}"
    dernier = StudentProfile.query.filter(
        StudentProfile.matricule.like(f"{prefix}-%")
    ).order_by(StudentProfile.matricule.desc()).first()
    if dernier and dernier.matricule:
        try:
            num = int(dernier.matricule.split('-')[-1]) + 1
        except (ValueError, IndexError):
            num = 1
    else:
        num = 1
    return f"{prefix}-{num:04d}"


def _generate_password(length=10):
    """Genere un mot de passe aleatoire lisible."""
    import secrets
    import string
    chars = string.ascii_letters + string.digits
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(length))
        if any(c.isupper() for c in pwd) and any(c.islower() for c in pwd) and any(c.isdigit() for c in pwd):
            return pwd


def _normalize_string(s):
    """Normalise une chaine pour comparaison (minuscule, sans accents, sans espaces doubles)."""
    if not s:
        return ''
    import unicodedata
    s = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('ASCII')
    return ' '.join(s.lower().split())


@academic_bp.route('/import-students', methods=['GET', 'POST'])
@role_required('super_admin', 'school_admin')
def import_students():
    """Import en masse d'eleves avec creation automatique des comptes."""
    import openpyxl
    from app.models.user import User
    from werkzeug.security import generate_password_hash

    school_id = _get_school_id()
    year_id = _get_active_year_id(school_id)
    annee = db.session.get(AcademicYear, year_id)

    if not annee or annee.statut != 'active':
        flash("Aucune annee scolaire active. Creez-en une d'abord.", 'danger')
        return redirect(url_for('academic.list_years', school_id=school_id))

    # Liste des classes pour le formulaire
    classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()

    if request.method == 'GET':
        return render_template('academic/import_students.html',
                              classes=classes, annee=annee, school_id=school_id, year_id=year_id,
                              breadcrumbs=[("Import Eleves", None)],
                              default_password='',
                              preview=None, credentials=None)

    # --- POST: traitement ---
    default_class_id = request.form.get('default_class_id', type=int)
    default_password = request.form.get('default_password', '').strip()
    confirm = request.form.get('confirm') == '1'

    if 'file' not in request.files:
        flash('Aucun fichier selectionne.', 'danger')
        return redirect(url_for('academic.import_students', school_id=school_id))

    fichier = request.files['file']
    if not fichier.filename:
        flash('Aucun fichier selectionne.', 'danger')
        return redirect(url_for('academic.import_students', school_id=school_id))

    # Validation extension
    ext = fichier.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('xlsx', 'xls', 'csv'):
        flash('Format non supporte. Utilisez .xlsx ou .csv.', 'danger')
        return redirect(url_for('academic.import_students', school_id=school_id))

    # Taille max 10MB
    fichier.seek(0, 2)
    size = fichier.tell()
    fichier.seek(0)
    if size > 10 * 1024 * 1024:
        flash('Fichier trop volumineux (max 10MB).', 'danger')
        return redirect(url_for('academic.import_students', school_id=school_id))

    # Parser le fichier
    try:
        if ext == 'csv':
            import csv, io
            content = fichier.read().decode('utf-8-sig')
            rows = list(csv.DictReader(io.StringIO(content)))
        else:
            wb = openpyxl.load_workbook(fichier, read_only=True, data_only=True)
            ws = wb.active
            headers = [str(c.value).strip().lower() if c.value else '' for c in next(ws.iter_rows(min_row=1, max_row=1))]
            rows = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                if all(v is None or str(v).strip() == '' for v in row):
                    continue
                rows.append(dict(zip(headers, [str(v).strip() if v is not None else '' for v in row])))
    except Exception as e:
        flash(f'Erreur de lecture du fichier: {e}', 'danger')
        return redirect(url_for('academic.import_students', school_id=school_id))

    if not rows:
        flash('Fichier vide.', 'warning')
        return redirect(url_for('academic.import_students', school_id=school_id))

    # Map des colonnes (flexible: francais ou anglais, avec ou sans accents)
    col_map = {}
    sample_keys = list(rows[0].keys()) if rows else []
    for key in IMPORT_COLUMNS:
        for h in sample_keys:
            h_norm = _normalize_string(h).replace(' ', '_').replace('*', '')
            if h_norm == key or key in h_norm or h_norm in key:
                col_map[key] = h
                break

    # Verifier les colonnes obligatoires
    missing = []
    for req in ['nom', 'prenom', 'classe']:
        if req not in col_map:
            missing.append(IMPORT_COLUMNS_FRIENDLY[req])
    if missing:
        flash(f'Colonnes obligatoires manquantes: {", ".join(missing)}. '
              f'Telechargez le template.', 'danger')
        return redirect(url_for('academic.import_students', school_id=school_id))

    # Charger toutes les classes et profils existants pour lookup rapide
    classes_by_name = {}
    for c in Class.query.filter_by(school_id=school_id).all():
        classes_by_name[_normalize_string(c.nom)] = c

    # Charger TOUS les profils de cette ecole pour la dedup
    existing_profiles = {}
    all_profiles = StudentProfile.query.join(
        StudentEnrollment, StudentProfile.id == StudentEnrollment.student_profile_id
    ).filter(
        StudentEnrollment.school_id == school_id,
        StudentEnrollment.academic_year_id == year_id
    ).all()
    for sp in all_profiles:
        if sp.matricule:
            existing_profiles[sp.matricule.lower().strip()] = sp
        key = (_normalize_string(sp.user.nom if sp.user else ''),
               _normalize_string(sp.user.prenom if sp.user else ''))
        if key[0] and key[1]:
            existing_profiles[key] = sp

    # Analyse des lignes
    preview = {'new_students': [], 'existing_students': [], 'errors': [],
               'new_parents': 0, 'existing_parents': 0,
               'total': len(rows), 'classes_not_found': set()}

    for i, row in enumerate(rows, start=2):
        try:
            nom = row.get(col_map.get('nom', ''), '').strip()
            prenom = row.get(col_map.get('prenom', ''), '').strip()
            matricule = row.get(col_map.get('matricule', ''), '').strip() if 'matricule' in col_map else ''
            date_naiss_str = row.get(col_map.get('date_naissance', ''), '').strip() if 'date_naissance' in col_map else ''
            sexe = row.get(col_map.get('sexe', ''), '').strip().upper() if 'sexe' in col_map else ''
            classe_nom = row.get(col_map.get('classe', ''), '').strip()
            adresse = row.get(col_map.get('adresse', ''), '').strip() if 'adresse' in col_map else ''
            email_eleve = row.get(col_map.get('email_eleve', ''), '').strip().lower() if 'email_eleve' in col_map else ''
            nom_parent = row.get(col_map.get('nom_parent', ''), '').strip() if 'nom_parent' in col_map else ''
            prenom_parent = row.get(col_map.get('prenom_parent', ''), '').strip() if 'prenom_parent' in col_map else ''
            tel_parent = row.get(col_map.get('telephone_parent', ''), '').strip() if 'telephone_parent' in col_map else ''
            email_parent = row.get(col_map.get('email_parent', ''), '').strip().lower() if 'email_parent' in col_map else ''
            relation_parent = row.get(col_map.get('relation_parent', ''), '').strip().lower() if 'relation_parent' in col_map else 'tuteur'

            if not nom or not prenom:
                preview['errors'].append(f"Ligne {i}: Nom ou prenom manquant")
                continue

            # Trouver la classe
            classe_norm = _normalize_string(classe_nom)
            if not classe_nom:
                if default_class_id:
                    classe = db.session.get(Class, default_class_id)
                else:
                    preview['errors'].append(f"Ligne {i}: Classe manquante et aucune classe par defaut")
                    continue
            else:
                classe = classes_by_name.get(classe_norm)

            if not classe:
                preview['classes_not_found'].add(classe_nom)
                preview['errors'].append(f"Ligne {i}: Classe '{classe_nom}' introuvable")
                continue

            # Chercher l'eleve existant
            existing_sp = None
            if matricule:
                existing_sp = existing_profiles.get(matricule.lower().strip())
            if not existing_sp:
                key = (_normalize_string(nom), _normalize_string(prenom))
                existing_sp = existing_profiles.get(key)

            # Parser date
            date_naissance = None
            if date_naiss_str:
                for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y', '%Y/%m/%d']:
                    try:
                        date_naissance = datetime.strptime(date_naiss_str, fmt).date()
                        break
                    except ValueError:
                        continue

            row_data = {
                'row': i, 'nom': nom, 'prenom': prenom,
                'matricule': matricule, 'date_naissance': date_naissance,
                'sexe': sexe if sexe in ('M', 'F') else '',
                'classe': classe.nom, 'class_id': classe.id,
                'adresse': adresse,
                'email_eleve': email_eleve,
                'nom_parent': nom_parent, 'prenom_parent': prenom_parent,
                'tel_parent': tel_parent, 'email_parent': email_parent,
                'relation_parent': relation_parent or 'tuteur',
            }

            if existing_sp:
                # Verifier si deja inscrit dans cette classe cette annee
                already = StudentEnrollment.query.filter_by(
                    student_profile_id=existing_sp.id,
                    class_id=classe.id,
                    academic_year_id=year_id
                ).first()
                row_data['status'] = 'deja_inscrit' if already else 'maj_classe'
                row_data['existing_profile_id'] = existing_sp.id
                preview['existing_students'].append(row_data)
            else:
                row_data['status'] = 'nouveau'
                preview['new_students'].append(row_data)
                if nom_parent:
                    preview['new_parents'] += 1
                elif tel_parent or email_parent:
                    preview['existing_parents'] += 1

        except Exception as e:
            preview['errors'].append(f"Ligne {i}: Erreur inattendue - {e}")

    # --- Si confirmation ---
    if confirm:
        if preview['errors']:
            flash(f"{len(preview['errors'])} erreurs. Corrigez le fichier et reessayez.", 'danger')
            return render_template('academic/import_students.html',
                                  classes=classes, annee=annee, school_id=school_id, year_id=year_id,
                                  breadcrumbs=[("Import Eleves", None)],
                                  preview=preview, credentials=None)

        credentials = []
        try:
            for row_data in preview['new_students']:
                with db.session.begin_nested():
                    # 1. Creer l'utilisateur parent si necessaire
                    parent_user = None
                    if row_data['nom_parent']:
                        parent_login = row_data.get('tel_parent') or row_data.get('email_parent') or \
                                      f"parent_{_normalize_string(row_data['nom_parent']).replace(' ', '_')}"
                        parent_email = row_data.get('email_parent') or f"{parent_login}@parent.local"
                        parent_user = User.query.filter(
                            (User.email == parent_email) |
                            (User.telephone == row_data.get('tel_parent'))
                        ).filter(User.role == 'parent').first()

                        if not parent_user:
                            parent_pwd = default_password or _generate_password()
                            parent_user = User(
                                email=parent_email,
                                nom=row_data['nom_parent'],
                                prenom=row_data['prenom_parent'] or '',
                                telephone=row_data.get('tel_parent') or '',
                                role='parent',
                                school_id=school_id,
                                created_at=datetime.utcnow()
                            )
                            parent_user.set_password(parent_pwd)
                            db.session.add(parent_user)
                            db.session.flush()
                            credentials.append({
                                'type': 'parent',
                                'nom': f"{row_data['nom_parent']} {row_data['prenom_parent']}",
                                'login': parent_email,
                                'password': parent_pwd,
                                'enfant': f"{row_data['nom']} {row_data['prenom']}"
                            })

                    # 2. Creer l'utilisateur eleve
                    matricule = row_data['matricule'] or _auto_matricule(school_id, year_id)
                    email_eleve = row_data.get('email_eleve') or f"{matricule.lower()}@eleve.local"
                    login_eleve = row_data.get('email_eleve') or matricule  # Login = email si fourni, sinon matricule

                    eleve_user = User(
                        email=email_eleve,
                        nom=row_data['nom'],
                        prenom=row_data['prenom'],
                        telephone='',
                        role='student',
                        school_id=school_id,
                        created_at=datetime.utcnow()
                    )
                    eleve_pwd = default_password or _generate_password()
                    eleve_user.set_password(eleve_pwd)
                    db.session.add(eleve_user)
                    db.session.flush()

                    # 3. Creer StudentProfile
                    sp = StudentProfile(
                        user_id=eleve_user.id,
                        matricule=matricule,
                        date_naissance=row_data['date_naissance'],
                        sexe=row_data['sexe'] if row_data['sexe'] in ('M', 'F') else None,
                        adresse_famille=row_data['adresse'],
                        date_inscription=datetime.utcnow().date(),
                        statut='inscrit'
                    )
                    db.session.add(sp)
                    db.session.flush()

                    # 4. Inscription
                    enrollment = StudentEnrollment(
                        student_profile_id=sp.id,
                        class_id=row_data['class_id'],
                        academic_year_id=year_id,
                        school_id=school_id,
                        statut='actif'
                    )
                    db.session.add(enrollment)

                    # 5. Lien parent-eleve
                    if parent_user:
                        lien = StudentParent(
                            parent_id=parent_user.id,
                            student_profile_id=sp.id,
                            relation=row_data['relation_parent'],
                            est_tuteur_principal=True
                        )
                        db.session.add(lien)

                    # 6. Acces bulletin
                    access = StudentBulletinAccess(student_profile_id=sp.id, parent_access=True)
                    db.session.add(access)

                    credentials.append({
                        'type': 'eleve',
                        'nom': f"{row_data['nom']} {row_data['prenom']}",
                        'login': login_eleve,
                        'password': eleve_pwd,
                        'classe': row_data['classe']
                    })

            # Mise a jour des eleves existants (changement de classe)
            for row_data in preview['existing_students']:
                if row_data['status'] == 'maj_classe':
                    existing = db.session.get(StudentProfile, row_data['existing_profile_id'])
                    if existing:
                        old_enroll = StudentEnrollment.query.filter_by(
                            student_profile_id=existing.id,
                            academic_year_id=year_id
                        ).first()
                        if old_enroll:
                            old_enroll.class_id = row_data['class_id']
                            old_enroll.statut = 'actif'

            db.session.commit()
            flash(f'Import termine: {len(preview["new_students"])} nouveaux eleves, '
                  f'{len([s for s in preview["existing_students"] if s["status"]=="maj_classe"])} classes mises a jour.', 'success')

            return render_template('academic/import_students.html',
                                  classes=classes, annee=annee, school_id=school_id, year_id=year_id,
                                  breadcrumbs=[("Import Eleves", None)],
                                  preview=preview, credentials=credentials)

        except Exception as e:
            db.session.rollback()
            flash(f'Erreur lors de l\'import: {e}. Aucune donnee modifiee (rollback).', 'danger')
            return render_template('academic/import_students.html',
                                  classes=classes, annee=annee, school_id=school_id, year_id=year_id,
                                  breadcrumbs=[("Import Eleves", None)],
                                  preview=preview, credentials=None)

    # --- Preview ---
    return render_template('academic/import_students.html',
                          classes=classes, annee=annee, school_id=school_id, year_id=year_id,
                          breadcrumbs=[("Import Eleves", None)],
                          preview=preview, credentials=None)


@academic_bp.route('/import-students/template')
@role_required('super_admin', 'school_admin')
def download_import_template():
    """Telecharge le template Excel pour l'import d'eleves."""
    import openpyxl, io
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Eleves"

    # En-tetes
    header_fill = PatternFill(start_color="2B579A", end_color="2B579A", fill_type="solid")
    header_font = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    wrap = Alignment(wrap_text=True, vertical='center')

    col_names = [IMPORT_COLUMNS_FRIENDLY[k] for k in IMPORT_COLUMNS]
    for ci, name in enumerate(col_names, start=1):
        cell = ws.cell(row=1, column=ci, value=name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = wrap

    # Exemples
    exemples = [
        ['', 'MUTEBA', 'Gloire', '2010-05-15', 'M', '6eme A', '12 Av. Lumumba', 'gloire.muteba@email.com',
         'MUTEBA', 'Jean', '0991234567', 'jean.muteba@email.com', 'pere'],
        ['', 'KASONGO', 'Marie', '2011-08-22', 'F', '5eme B', '45 Bd Kasa-Vubu', '',
         'KASONGO', 'Therese', '0819876543', '', 'mere'],
        ['EL-2024-001', 'LUKUSA', 'David', '2009-03-10', 'M', '4eme A', '', 'david.lukusa@email.com',
         'LUKUSA', 'Paul', '0851122334', 'paul.lukusa@email.com', 'pere'],
    ]
    for ri, row_data in enumerate(exemples, start=2):
        for ci, val in enumerate(row_data, start=1):
            ws.cell(row=ri, column=ci, value=val)

    # Largeurs
    widths = [18, 15, 15, 15, 8, 15, 20, 28, 15, 15, 15, 30, 12]
    for ci, w in enumerate(widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = w

    # Feuille d'aide
    ws2 = wb.create_sheet("Aide")
    ws2.cell(row=1, column=1, value="AIDE - Import Eleves").font = Font(bold=True, size=14)
    instructions = [
        "1. Remplissez les colonnes selon vos donnees.",
        "2. Colonnes avec * sont obligatoires.",
        "3. Matricule vide = genere automatiquement.",
        "4. Classe doit correspondre EXACTEMENT au nom dans le systeme (ex: '6eme A').",
        "5. Si l'eleve existe deja (meme nom+prenom), sa classe sera mise a jour.",
        "6. Si un parent avec le meme telephone/email existe, il sera relie.",
        "7. Les comptes (eleve + parent) sont crees automatiquement.",
        "8. Apres import, vous recevrez la liste des identifiants generes.",
        "",
        "FORMATS ACCEPTES:",
        "- Date naissance: 2010-05-15 ou 15/05/2010 ou 15-05-2010",
        "- Sexe: M ou F",
        "- Telephone: chiffres uniquement",
    ]
    for ri, instr in enumerate(instructions, start=2):
        ws2.cell(row=ri, column=1, value=instr)
    ws2.column_dimensions['A'].width = 80

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    as_attachment=True, download_name='Template_Import_Eleves.xlsx')


# ============================================================
# DEVOIRS / ASSIGNMENTS — Gestion par le professeur
# ============================================================

@academic_bp.route('/devoirs')
@login_required
@role_required('super_admin', 'school_admin', 'teacher')
def devoirs_list():
    """Liste des devoirs avec filtres par classe."""
    school_id = _get_school_id()
    if not school_id and current_user.role == 'super_admin':
        flash('Veuillez selectionner une ecole.', 'warning')
        return redirect(url_for('schools.list'))
    page = request.args.get('page', 1, type=int)
    class_filter = request.args.get('class_id', 0, type=int)

    query = Assignment.query.filter_by(school_id=school_id)

    # Filtre par annee scolaire (actif par defaut, mais selectable)
    year_filter = request.args.get('year_id', None, type=int)
    if year_filter is None:
        year_filter = _get_active_year_id(school_id)
    if year_filter:
        query = query.filter_by(academic_year_id=year_filter)

    # Enseignant : voir ses devoirs seulement
    if current_user.role == 'teacher':
        query = query.filter_by(teacher_id=current_user.id)

    if class_filter:
        query = query.filter_by(class_id=class_filter)

    query = query.order_by(Assignment.created_at.desc())
    pagination = query.paginate(page=page, per_page=15, error_out=False)
    assignments = pagination.items

    classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()
    all_years = AcademicYear.query.filter_by(school_id=school_id).order_by(AcademicYear.date_debut.desc()).all()

    return render_template('academic/devoirs/list.html',
                          assignments=assignments, pagination=pagination,
                          classes=classes, class_filter=class_filter,
                          year_filter=year_filter, all_years=all_years)


@academic_bp.route('/devoirs/create', methods=['GET', 'POST'])
@login_required
@role_required('super_admin', 'school_admin', 'teacher')
def devoirs_create():
    """Créer un nouveau devoir."""
    school_id = _get_school_id()
    if not school_id and current_user.role == 'super_admin':
        flash('Veuillez selectionner une ecole.', 'warning')
        return redirect(url_for('schools.list'))

    # Pour les enseignants, pré-remplir leurs classes/matières
    teacher_classes = []
    teacher_subjects = []
    if current_user.role == 'teacher':
        teacher_classes = Class.query.join(
            ClassSubject, Class.id == ClassSubject.class_id
        ).filter(
            Class.school_id == school_id,
            ClassSubject.teacher_id == current_user.id,
            Class.actif == True
        ).order_by(Class.nom).all()
    else:
        teacher_classes = Class.query.filter_by(
            school_id=school_id, actif=True
        ).order_by(Class.nom).all()

    if request.method == 'POST':
        titre = request.form.get('titre', '').strip()
        description = request.form.get('description', '').strip()
        class_id = request.form.get('class_id', type=int)
        subject_id = request.form.get('subject_id', type=int) or None
        date_limite_str = request.form.get('date_limite', '')
        max_points = request.form.get('max_points', type=float) or None
        authorise_retard = request.form.get('authorise_retard') == '1'

        # Validation
        errors = []
        if not titre:
            errors.append('Le titre est requis.')
        if not class_id:
            errors.append('La classe est requise.')
        if not date_limite_str:
            errors.append('La date limite est requise.')
        else:
            try:
                date_limite = datetime.strptime(date_limite_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                errors.append('Format de date invalide.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            # Reconstruire les matieres pour le template
            all_subjects_fb = Subject.query.filter_by(school_id=school_id, actif=True).order_by(Subject.nom).all()
            class_subjects_fb = ClassSubject.query.filter(ClassSubject.class_id.in_([c.id for c in teacher_classes])).all()
            all_class_subjects_fb = []
            for cs in class_subjects_fb:
                for s in all_subjects_fb:
                    if s.id == cs.subject_id:
                        all_class_subjects_fb.append({
                            'class_id': cs.class_id,
                            'subject_id': cs.subject_id,
                            'subject_name': s.nom
                        })
                        break
            return render_template('academic/devoirs/create.html',
                                  classes=teacher_classes, subjects=[],
                                  all_class_subjects=all_class_subjects_fb)

        assignment = Assignment(
            school_id=school_id,
            class_id=class_id,
            academic_year_id=_get_active_year_id(school_id),
            subject_id=subject_id,
            teacher_id=current_user.id,
            titre=titre,
            description=description or None,
            date_limite=date_limite,
            authorise_retard=authorise_retard,
            max_points=max_points,
            statut='actif',
        )

        # Fichier joint du professeur
        fichier = request.files.get('fichier_joint')
        if fichier and fichier.filename:
            if not Submission.allowed_file(fichier.filename):
                flash('Type de fichier non autorise.', 'danger')
                db.session.rollback()
                return redirect(url_for('academic.devoirs_create'))
            from werkzeug.utils import secure_filename
            filename = secure_filename(fichier.filename)
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            saved_name = f"devoir_{assignment.teacher_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{ext}"
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'devoirs')
            os.makedirs(upload_dir, exist_ok=True)
            fichier.save(os.path.join(upload_dir, saved_name))
            assignment.fichier_joint = f'devoirs/{saved_name}'
            assignment.fichier_joint_nom = filename

        db.session.add(assignment)
        db.session.commit()

        log_action('devoir_created', details=f'Devoir "{titre}" crée pour classe {class_id}')
        flash(f'Devoir "{titre}" créé avec succès !', 'success')
        return redirect(url_for('academic.devoirs_list'))

    # Preparer les matieres pour le filtre par classe (rendu direct dans le HTML)
    all_class_subjects = []
    class_subs = ClassSubject.query.filter(ClassSubject.class_id.in_([c.id for c in teacher_classes])).all()
    all_subs = Subject.query.filter_by(school_id=school_id, actif=True).order_by(Subject.nom).all()
    for cs in class_subs:
        subj_name = None
        for s in all_subs:
            if s.id == cs.subject_id:
                subj_name = s.nom
                break
        if subj_name:
            all_class_subjects.append({
                'class_id': cs.class_id,
                'subject_id': cs.subject_id,
                'subject_name': subj_name
            })

    return render_template('academic/devoirs/create.html',
                          classes=teacher_classes, subjects=[],
                          all_class_subjects=all_class_subjects)


@academic_bp.route('/devoirs/<int:assignment_id>')
@login_required
@role_required('super_admin', 'school_admin', 'teacher')
def devoirs_detail(assignment_id):
    """Détail d'un devoir avec toutes les soumissions."""
    school_id = _get_school_id()
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment or assignment.school_id != school_id:
        flash('Devoir introuvable.', 'danger')
        return redirect(url_for('academic.devoirs_list'))

    if current_user.role == 'teacher' and assignment.teacher_id != current_user.id:
        flash('Accès non autorisé.', 'danger')
        return redirect(url_for('academic.devoirs_list'))

    # Liste des élèves de la classe
    from app.models.student import StudentEnrollment, StudentProfile
    enrollments = StudentEnrollment.query.filter_by(
        class_id=assignment.class_id, statut='actif'
    ).order_by(StudentEnrollment.created_at).all()

    # Dictionnaire élève -> soumission
    submissions_map = {}
    for sub in assignment.submissions:
        submissions_map[sub.student_id] = sub

    # Profiles pour matricules
    profiles_map = {}
    for enr in enrollments:
        profile = StudentProfile.query.filter_by(user_id=enr.student.id).first()
        if profile:
            profiles_map[enr.student.id] = profile

    return render_template('academic/devoirs/detail.html',
                          assignment=assignment,
                          enrollments=enrollments,
                          submissions_map=submissions_map,
                          profiles_map=profiles_map)


@academic_bp.route('/devoirs/<int:assignment_id>/note', methods=['POST'])
@login_required
@role_required('super_admin', 'school_admin', 'teacher')
def devoirs_note(assignment_id):
    """Noter une soumission."""
    school_id = _get_school_id()
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment or assignment.school_id != school_id:
        return jsonify({'error': 'Devoir introuvable'}), 404

    if current_user.role == 'teacher' and assignment.teacher_id != current_user.id:
        return jsonify({'error': 'Non autorisé'}), 403

    validate_csrf(request.form.get('csrf_token', ''))

    submission_id = request.form.get('submission_id', type=int)
    note = request.form.get('note', type=float)
    feedback = request.form.get('feedback', '').strip()

    submission = db.session.get(Submission, submission_id)
    if not submission or submission.assignment_id != assignment_id:
        return jsonify({'error': 'Soumission introuvable'}), 404

    submission.note = note
    submission.feedback = feedback or None
    submission.statut = 'note'
    db.session.commit()

    log_action('devoir_note', details=f'Soumission {submission_id} notée {note}')
    flash('Note enregistrée.', 'success')
    return redirect(url_for('academic.devoirs_detail', assignment_id=assignment_id))


@academic_bp.route('/devoirs/<int:assignment_id>/download')
@login_required
@role_required('super_admin', 'school_admin', 'teacher')
def devoirs_download(assignment_id):
    """Télécharger toutes les soumissions en ZIP."""
    school_id = _get_school_id()
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment or assignment.school_id != school_id:
        flash('Devoir introuvable.', 'danger')
        return redirect(url_for('academic.devoirs_list'))

    if not assignment.submissions:
        flash('Aucune soumission à télécharger.', 'warning')
        return redirect(url_for('academic.devoirs_detail', assignment_id=assignment_id))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for sub in assignment.submissions:
            if sub.fichier:
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], sub.fichier)
                if os.path.exists(filepath):
                    student = sub.student
                    arcname = f"{student.nom}_{student.prenom}/{sub.fichier_nom or 'fichier'}"
                    zf.write(filepath, arcname)

    buf.seek(0)
    safe_title = assignment.titre.replace(' ', '_')[:50]
    return send_file(buf, mimetype='application/zip',
                    as_attachment=True,
                    download_name=f'Soumissions_{safe_title}.zip')


@academic_bp.route('/api/class/<int:class_id>/subjects')
@login_required
@role_required('super_admin', 'school_admin', 'teacher')
def api_class_subjects(class_id):
    """API: matieres d'une classe."""
    subjects = ClassSubject.query.filter_by(class_id=class_id).join(Subject).order_by(Subject.nom).all()
    return jsonify([{'id': cs.subject_id, 'nom': cs.subject.nom} for cs in subjects])

