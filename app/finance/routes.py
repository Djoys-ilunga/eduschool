from flask import render_template, redirect, url_for, flash, request, send_file

from flask_login import current_user

from datetime import date

import io



from app.finance import finance_bp

from app.finance.forms import FeeTypeForm, FeeForm, PaymentForm

from app.models import db

from app.models.finance import FeeType, Fee, SchoolPayment

from app.models.academic import AcademicYear, Class

from app.models.student import StudentProfile, StudentEnrollment

from app.models.school import School

from app.auth.decorators import role_required

from app.utils.pdf_receipt import generate_receipt_pdf
from app.utils.helpers import _get_school_id








# ============================================================

# TYPES DE FRAIS

# ============================================================



@finance_bp.route('/types')

@role_required('super_admin', 'school_admin')

def list_fee_types():

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))

    types = FeeType.query.filter_by(school_id=school_id).order_by(FeeType.nom).all()

    return render_template('finance/fee_types.html', types=types, school_id=school_id,

                          breadcrumbs=[("Types de Frais", None)])





@finance_bp.route('/types/create', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def create_fee_type():

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('finance.list_fee_types', school_id=school_id))

    form = FeeTypeForm()

    if form.validate_on_submit():

        ft = FeeType(school_id=school_id, nom=form.nom.data, description=form.description.data.strip() if form.description.data else None)

        db.session.add(ft)

        db.session.commit()

        flash(f'Type de frais "{ft.nom}" cree.', 'success')

        return redirect(url_for('finance.list_fee_types', school_id=school_id))

    return render_template('finance/fee_type_form.html', form=form, edit=False, school_id=school_id)





@finance_bp.route('/types/<int:type_id>/edit', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def edit_fee_type(type_id):

    school_id = _get_school_id()

    ft = db.session.get(FeeType, type_id)

    if not ft:

        flash('Type introuvable.', 'danger')

        return redirect(url_for('finance.list_fee_types', school_id=school_id))

    form = FeeTypeForm(obj=ft)

    if form.validate_on_submit():

        ft.nom = form.nom.data

        ft.description = form.description.data.strip() if form.description.data else None

        db.session.commit()

        flash(f'Type mis a jour.', 'success')

        return redirect(url_for('finance.list_fee_types', school_id=school_id))

    return render_template('finance/fee_type_form.html', form=form, edit=True, ft=ft, school_id=school_id)





@finance_bp.route('/types/<int:type_id>/toggle', methods=['POST'])

@role_required('super_admin', 'school_admin')


def toggle_fee_type(type_id):

    ft = db.session.get(FeeType, type_id)

    if ft:

        ft.actif = not ft.actif

        db.session.commit()

        flash(f'Type {"active" if ft.actif else "desactive"}.', 'info')

    return redirect(url_for('finance.list_fee_types', school_id=_get_school_id()))





# ============================================================

# FRAIS (MONTANTS PAR CLASSE)

# ============================================================



@finance_bp.route('/fees')

@role_required('super_admin', 'school_admin')

def list_fees():

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))

    from app.academic.routes import _get_active_year_id
    year_id = _get_active_year_id(school_id)

    class_id = request.args.get('class_id', None, type=int)

    query = Fee.query.filter_by(school_id=school_id, academic_year_id=year_id)

    if class_id:

        query = query.filter_by(class_id=class_id)

    fees = query.order_by(Fee.created_at.desc()).all()

    classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()

    return render_template('finance/fees.html', fees=fees, classes=classes,

                          class_id=class_id, school_id=school_id,

                          breadcrumbs=[("Frais Scolaires", None)])





@finance_bp.route('/fees/create', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def create_fee():

    school_id = _get_school_id()

    form = FeeForm()

    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

    year_id = annee.id if annee else None

    form.load_choices(school_id)

    if form.validate_on_submit():

        fee = Fee(school_id=school_id, fee_type_id=form.fee_type_id.data,

                  class_id=form.class_id.data, academic_year_id=year_id if annee else None,

                  montant=form.montant.data, devise=form.devise.data,

                  echeance=form.echeance.data)

        db.session.add(fee)

        db.session.commit()

        flash(f'Frais defini : {form.montant.data:,.0f} {form.devise.data}.', 'success')

        return redirect(url_for('finance.list_fees', school_id=school_id))

    return render_template('finance/fee_form.html', form=form, edit=False, school_id=school_id)





@finance_bp.route('/fees/<int:fee_id>/delete', methods=['POST'])

@role_required('super_admin', 'school_admin')


def delete_fee(fee_id):

    fee = db.session.get(Fee, fee_id)

    if fee:

        db.session.delete(fee)

        db.session.commit()

        flash('Frais supprime.', 'info')

    return redirect(url_for('finance.list_fees', school_id=_get_school_id()))





# ============================================================

# PAIEMENTS

# ============================================================



@finance_bp.route('/payments')

@role_required('super_admin', 'school_admin')

def list_payments():

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))

    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

    year_id = annee.id if annee else None

    class_id = request.args.get('class_id', None, type=int)

    profile_id = request.args.get('profile_id', None, type=int)

    query = SchoolPayment.query.filter_by(school_id=school_id).order_by(SchoolPayment.date_paiement.desc())

    if profile_id:

        query = query.filter_by(student_profile_id=profile_id)

    if class_id:

        enroll_ids = [e.student_profile_id for e in StudentEnrollment.query.filter_by(class_id=class_id, statut='actif').all()]

        query = query.filter(SchoolPayment.student_profile_id.in_(enroll_ids))

    payments = query.limit(200).all()

    classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()

    return render_template('finance/payments.html', payments=payments, classes=classes,

                          class_id=class_id, profile_id=profile_id, school_id=school_id,

                          breadcrumbs=[("Paiements", None)])





@finance_bp.route('/payments/<int:payment_id>/receipt')

@role_required('super_admin', 'school_admin')

def payment_receipt(payment_id):

    """Generate and download a PDF receipt for a payment."""

    payment = db.session.get(SchoolPayment, payment_id)

    if not payment:

        flash('Paiement introuvable.', 'danger')

        return redirect(url_for('finance.list_payments', school_id=_get_school_id()))



    school = db.session.get(School, payment.school_id)

    if not school:

        flash('École introuvable.', 'danger')

        return redirect(url_for('finance.list_payments', school_id=_get_school_id()))



    student_user = payment.student_profile.user if payment.student_profile else None

    if not student_user:

        flash('Élève introuvable.', 'danger')

        return redirect(url_for('finance.list_payments', school_id=_get_school_id()))



    pdf_bytes = generate_receipt_pdf(payment, school, student_user, payment.fee)

    return send_file(

        io.BytesIO(pdf_bytes),

        mimetype='application/pdf',

        as_attachment=True,

        download_name=f'recu_paiement_{payment.id}.pdf',

    )





@finance_bp.route('/payments/create', methods=['GET', 'POST'])

@role_required('super_admin', 'school_admin')

def create_payment():

    school_id = _get_school_id()

    annee = AcademicYear.query.filter_by(school_id=school_id, statut='active').first()

    year_id = annee.id if annee else None

    form = PaymentForm()

    class_id = request.args.get('class_id', None, type=int)

    profile_id_preset = request.args.get('profile_id', None, type=int)

    fee_id_preset = request.args.get('fee_id', None, type=int)

    form.load_choices(school_id, class_id, year_id)

    if profile_id_preset and form.student_profile_id.choices:

        form.student_profile_id.data = profile_id_preset

    if fee_id_preset and any(choice[0] == fee_id_preset for choice in form.fee_id.choices):

        form.fee_id.data = fee_id_preset

        from app.models.finance import Fee

        fee = db.session.get(Fee, fee_id_preset)

        if fee:

            form.montant_paye.data = float(fee.montant)

    if form.validate_on_submit():

        payment = SchoolPayment(

            school_id=school_id, student_profile_id=form.student_profile_id.data,

            fee_id=form.fee_id.data, montant_paye=form.montant_paye.data,

            date_paiement=form.date_paiement.data, mode_paiement=form.mode_paiement.data,

            reference=form.reference.data.strip() if form.reference.data else None,

            recu_par=current_user.id, commentaire=form.commentaire.data.strip() if form.commentaire.data else None,

        )

        db.session.add(payment)

        db.session.commit()

        flash(f'Paiement de {form.montant_paye.data:,.0f} enregistre.', 'success')

        return redirect(url_for('finance.list_payments', school_id=school_id))

    classes = Class.query.filter_by(school_id=school_id, actif=True).order_by(Class.nom).all()

    if not form.date_paiement.data:

        form.date_paiement.data = date.today()

    return render_template('finance/payment_form.html', form=form, school_id=school_id,

                          class_id=class_id, classes=classes)





# --- PORTAL PARENT ---



@finance_bp.route('/mon-compte')

@role_required('parent')

def parent_account():

    """Portail parent : etat des frais par enfant, groupes par devise."""

    from app.models.student import StudentParent

    from datetime import date as dt_date

    annee = AcademicYear.query.filter_by(school_id=current_user.school_id, statut='active').first()

    year_id = annee.id if annee else None

    liens = StudentParent.query.filter_by(parent_id=current_user.id).all()

    enfants_data = []

    for lien in liens:

        profile = lien.student_profile

        if not profile:

            continue

        enrollment = StudentEnrollment.query.filter_by(student_profile_id=profile.id, statut='actif').first()

        if not enrollment:

            continue

        fees = Fee.query.filter_by(school_id=current_user.school_id, class_id=enrollment.class_id, academic_year_id=year_id if annee else None).all()

        # Grouper par devise

        fee_items = []

        totals_by_devise = {}

        for f in fees:

            paye = SchoolPayment.total_paye_eleve_fee(profile.id, f.id)

            reste = f.montant - paye

            fee_items.append({'fee': f, 'paye': paye, 'reste': reste})

            d = f.devise or 'CDF'

            if d not in totals_by_devise:

                totals_by_devise[d] = {'du': 0.0, 'paye': 0.0, 'reste': 0.0}

            totals_by_devise[d]['du'] += f.montant

            totals_by_devise[d]['paye'] += paye

            totals_by_devise[d]['reste'] += reste

        enfants_data.append({

            'profile': profile,

            'enrollment': enrollment,

            'fee_items': fee_items,

            'totals_by_devise': totals_by_devise,

            'all_paid': all(item['reste'] <= 0 for item in fee_items),

        })

    return render_template('finance/parent_account.html', enfants=enfants_data, school_id=current_user.school_id,

                          today=dt_date.today().isoformat(),

                          breadcrumbs=[("Mon Compte", None)])





@finance_bp.route('/tracking')

@role_required('super_admin', 'school_admin')

def payment_tracking():

    """Tableau de suivi : qui a paye, qui n'a pas paye, par classe."""

    school_id = _get_school_id()

    if not school_id:

        flash('Veuillez selectionner une ecole.', 'warning')

        return redirect(url_for('dashboard.index'))

    from app.academic.routes import _get_active_year_id
    year_id = _get_active_year_id(school_id)
    if not year_id:

        flash('Aucune annee scolaire configuree.', 'warning')

        return redirect(url_for('dashboard.index'))

    class_id = request.args.get('class_id', None, type=int)

    # Get fee types for this school

    fee_types = FeeType.query.filter_by(school_id=school_id, actif=True).order_by(FeeType.nom).all()

    # Get classes

    q_classes = Class.query.filter_by(school_id=school_id, actif=True)

    if class_id:

        q_classes = q_classes.filter_by(id=class_id)

    classes = q_classes.order_by(Class.nom).all()

    class_summaries = []

    for cl in classes:

        enrollments = StudentEnrollment.query.filter_by(class_id=cl.id, statut='actif').all()

        if not enrollments:

            continue

        rows = []

        stats = {'paid': 0, 'partial': 0, 'unpaid': 0}

        for enroll in enrollments:

            profile = enroll.student_profile

            if not profile:

                continue

            student_fees = Fee.query.filter_by(school_id=school_id, class_id=cl.id, academic_year_id=year_id).all()

            fee_data = []

            all_paid = True

            any_paid = False

            total_du = 0.0

            total_paye = 0.0

            for ft in fee_types:

                f = next((sf for sf in student_fees if sf.fee_type_id == ft.id), None)

                if f:

                    paye = SchoolPayment.total_paye_eleve_fee(profile.id, f.id)

                    du = f.montant

                    total_du += du

                    total_paye += paye

                    fee_data.append({

                        'paid': paye >= du and du > 0,

                        'partial': paye > 0 and paye < du,

                        'paye': paye,

                        'du': du,

                        'devise': f.devise or 'CDF',

                        'defined': True,

                    })

                    if paye <= 0:

                        all_paid = False

                    if paye > 0:

                        any_paid = True

                else:

                    fee_data.append({'defined': False})

            reste = total_du - total_paye

            if all_paid:

                stats['paid'] += 1

            elif any_paid:

                stats['partial'] += 1

            else:

                stats['unpaid'] += 1

            rows.append({

                'profile': profile,

                'fee_data': fee_data,

                'total_du': total_du,

                'total_paye': total_paye,

                'reste': reste,

                'all_paid': all_paid,

                'any_paid': any_paid,

            })

        class_summaries.append({'classe': cl, 'rows': rows, 'stats': stats})

    return render_template('finance/payment_tracking.html',

                          class_summaries=class_summaries, classes=classes,

                          fee_types=fee_types, class_id=class_id, school_id=school_id,

                          breadcrumbs=[("Suivi paiements", None)])



# ============================================================
# EXPORT PAIEMENTS
# ============================================================

@finance_bp.route('/export/payments')
@role_required('super_admin', 'school_admin')
def export_payments():
    """Exporte l'etat financier des eleves.
    Filtres: class_id, fee_type_id, statut (paye/non_paye)
    Colonnes: Eleve, Classe, Type frais, Montant, Paye, Reste, Statut
    """
    import openpyxl
    from app.academic.routes import _apply_excel_style
    school_id = _get_school_id()
    if not school_id:
        flash('Veuillez selectionner une ecole.', 'warning')
        return redirect(url_for('dashboard.index'))

    from app.academic.routes import _get_active_year_id
    year_id = _get_active_year_id(school_id)
    if not year_id:
        flash('Aucune annee scolaire active.', 'warning')
        return redirect(url_for('finance.payment_tracking', school_id=school_id))

    class_id = request.args.get('class_id', type=int)
    fee_type_id = request.args.get('fee_type_id', type=int)
    statut_filter = request.args.get('statut', '').strip()  # 'paye', 'non_paye', or '' (tous)

    # Construire les donnees
    query_classes = Class.query.filter_by(school_id=school_id, actif=True, academic_year_id=year_id)
    if class_id:
        query_classes = query_classes.filter_by(id=class_id)
    classes = query_classes.order_by(Class.nom).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Paiements"

    headers = ['Eleve', 'Classe', 'Type Frais', 'Montant', 'Paye', 'Reste', 'Statut']
    data_rows = []

    for cl in classes:
        enrollments = StudentEnrollment.query.filter_by(class_id=cl.id, statut='actif').all()
        for enroll in enrollments:
            sp = enroll.student_profile
            if not sp:
                continue
            user = sp.user

            fees_query = Fee.query.filter_by(school_id=school_id, class_id=cl.id, academic_year_id=year_id)
            if fee_type_id:
                fees_query = fees_query.filter_by(fee_type_id=fee_type_id)
            fees = fees_query.all()

            for f in fees:
                paye = SchoolPayment.total_paye_eleve_fee(sp.id, f.id)
                reste = round(f.montant - paye, 2)

                if reste <= 0:
                    statut_label = 'Paye'
                elif paye > 0:
                    statut_label = 'Partiel'
                else:
                    statut_label = 'Impaye'

                # Appliquer filtre statut
                if statut_filter == 'paye' and statut_label != 'Paye':
                    continue
                if statut_filter == 'non_paye' and statut_label == 'Paye':
                    continue

                data_rows.append([
                    f"{user.prenom} {user.nom}" if user else '',
                    cl.nom,
                    f.fee_type.nom if f.fee_type else '',
                    round(f.montant, 2),
                    round(paye, 2),
                    reste,
                    statut_label,
                ])

    if not data_rows:
        flash('Aucun paiement a exporter.', 'warning')
        return redirect(url_for('academic.exports_center', school_id=school_id))

    _apply_excel_style(ws, headers, data_rows)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = "Etat_Paiements.xlsx"
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)


