"""
PDF Receipt Generator for EduSchool.
Uses reportlab to produce professional payment receipt PDFs.
"""

import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, Image
)

# ── Styles ──────────────────────────────────────────────────
_styles = getSampleStyleSheet()

STYLE_TITLE = ParagraphStyle(
    'ReceiptTitle', parent=_styles['Heading1'],
    fontSize=18, leading=22, alignment=TA_CENTER,
    spaceAfter=2 * mm, textColor=colors.HexColor('#1a237e'),
    fontName='Helvetica-Bold',
)

STYLE_SCHOOL_NAME = ParagraphStyle(
    'ReceiptSchoolName', parent=_styles['Heading2'],
    fontSize=14, leading=18, alignment=TA_CENTER,
    spaceAfter=1 * mm, textColor=colors.HexColor('#37474f'),
    fontName='Helvetica-Bold',
)

STYLE_SCHOOL_ADDRESS = ParagraphStyle(
    'ReceiptSchoolAddress', parent=_styles['Normal'],
    fontSize=9, leading=11, alignment=TA_CENTER,
    textColor=colors.HexColor('#757575'),
    fontName='Helvetica',
)

STYLE_RECEIPT_NO = ParagraphStyle(
    'ReceiptNo', parent=_styles['Normal'],
    fontSize=10, leading=12, alignment=TA_RIGHT,
    fontName='Helvetica-Bold',
    textColor=colors.HexColor('#1a237e'),
)

STYLE_LABEL = ParagraphStyle(
    'ReceiptLabel', parent=_styles['Normal'],
    fontSize=10, leading=14, fontName='Helvetica-Bold',
    textColor=colors.HexColor('#37474f'),
)

STYLE_VALUE = ParagraphStyle(
    'ReceiptValue', parent=_styles['Normal'],
    fontSize=10, leading=14, fontName='Helvetica',
    textColor=colors.HexColor('#212121'),
)

STYLE_AMOUNT = ParagraphStyle(
    'ReceiptAmount', parent=_styles['Normal'],
    fontSize=14, leading=18, fontName='Helvetica-Bold',
    textColor=colors.HexColor('#1a237e'),
)

STYLE_FOOTER = ParagraphStyle(
    'ReceiptFooter', parent=_styles['Normal'],
    fontSize=9, leading=12, alignment=TA_CENTER,
    textColor=colors.HexColor('#757575'),
    fontName='Helvetica-Oblique',
)

STYLE_SIGNATURE = ParagraphStyle(
    'ReceiptSignature', parent=_styles['Normal'],
    fontSize=10, leading=13, alignment=TA_CENTER,
    fontName='Helvetica',
)

STYLE_STAMP = ParagraphStyle(
    'ReceiptStamp', parent=_styles['Normal'],
    fontSize=10, leading=13, alignment=TA_CENTER,
    fontName='Helvetica-Bold',
    textColor=colors.HexColor('#b71c1c'),
)


def generate_receipt_pdf(payment, school, student_user, fee):
    """
    Generate a payment receipt PDF.

    Parameters
    ----------
    payment : SchoolPayment
        The payment record.
    school : School
        The school model instance.
    student_user : User
        The student User instance (payment.student_profile.user).
    fee : Fee or None
        The Fee model instance associated with the payment.

    Returns
    -------
    bytes
        PDF content ready for download.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title='Reçu de Paiement',
        author='EduSchool',
    )

    elements = []

    # ── Receipt Number ──
    receipt_no = _generate_receipt_number(payment, school)
    elements.append(Paragraph(f'N° {receipt_no}', STYLE_RECEIPT_NO))
    elements.append(Spacer(1, 3 * mm))

    # ── Header ──
    elements.append(Paragraph('REÇU DE PAIEMENT', STYLE_TITLE))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(school.nom.upper(), STYLE_SCHOOL_NAME))

    if school.adresse:
        elements.append(Paragraph(school.adresse, STYLE_SCHOOL_ADDRESS))
    if school.ville or school.telephone:
        contact_parts = []
        if school.ville:
            contact_parts.append(school.ville)
        if school.telephone:
            contact_parts.append(f'Tél: {school.telephone}')
        if school.email:
            contact_parts.append(school.email)
        elements.append(Paragraph(' — '.join(contact_parts), STYLE_SCHOOL_ADDRESS))

    elements.append(Spacer(1, 6 * mm))

    # ── Separator line ──
    line_table = Table([['']], colWidths=[doc.width])
    line_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor('#1a237e')),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 5 * mm))

    # ── Body: Payment Details ──
    date_str = payment.date_paiement.strftime('%d/%m/%Y') if payment.date_paiement else '—'
    student_name = f'{student_user.prenom} {student_user.nom}'

    # Get class name
    from app.models.student import StudentEnrollment
    enrollment = StudentEnrollment.query.filter_by(
        student_profile_id=payment.student_profile_id,
        statut='actif'
    ).first()
    class_name = enrollment.classe.nom if enrollment else '—'

    fee_type_name = fee.fee_type.nom if fee and fee.fee_type else '—'
    devise = fee.devise if fee else (school.devise or 'CDF')
    montant_str = f'{payment.montant_paye:,.0f} {devise}'
    mode = payment.mode_paiement or '—'
    mode_label = _mode_label(mode)
    ref = payment.reference or '—'
    commentaire = payment.commentaire or '—'

    details = [
        ('Date de paiement', date_str),
        ('Élève', student_name),
        ('Classe', class_name),
        ('Type de frais', fee_type_name),
        ('Montant payé', ''),
        ('Mode de paiement', mode_label),
        ('Référence', ref),
    ]

    # Build details table (two columns: label | value)
    table_data = []
    for label, value in details:
        if label == 'Montant payé':
            # Special row for amount
            table_data.append([
                Paragraph(f'<b>{label}</b>', STYLE_LABEL),
                Paragraph(montant_str, STYLE_AMOUNT),
            ])
        else:
            table_data.append([
                Paragraph(f'<b>{label}</b>', STYLE_LABEL),
                Paragraph(value, STYLE_VALUE),
            ])

    col_widths = [doc.width * 0.35, doc.width * 0.65]
    tbl = Table(table_data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#e0e0e0')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f5f5f5')),
    ]))
    elements.append(tbl)

    # Comment if present
    if payment.commentaire:
        elements.append(Spacer(1, 4 * mm))
        elements.append(Paragraph(
            f'<b>Commentaire :</b> {payment.commentaire}',
            STYLE_VALUE
        ))

    elements.append(Spacer(1, 10 * mm))

    # ── Bottom separator ──
    line_table2 = Table([['']], colWidths=[doc.width])
    line_table2.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 0.5, colors.HexColor('#bdbdbd')),
    ]))
    elements.append(line_table2)
    elements.append(Spacer(1, 8 * mm))

    # ── Signature + Stamp Block ──
    sig_data = [
        [
            Paragraph('Cachet de l\'école', STYLE_STAMP),
            Paragraph('', STYLE_SIGNATURE),
            Paragraph('Signature du caissier', STYLE_SIGNATURE),
        ],
        [
            Paragraph('_________________', STYLE_SIGNATURE),
            Paragraph('', STYLE_SIGNATURE),
            Paragraph('_________________', STYLE_SIGNATURE),
        ],
    ]
    sig_tbl = Table(sig_data, colWidths=[doc.width * 0.33, doc.width * 0.34, doc.width * 0.33])
    sig_tbl.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4 * mm),
    ]))
    elements.append(sig_tbl)

    elements.append(Spacer(1, 10 * mm))

    # ── Footer ──
    elements.append(Paragraph(
        f'Reçu généré le {datetime.now().strftime("%d/%m/%Y à %H:%M")} — EduSchool',
        STYLE_FOOTER
    ))
    elements.append(Paragraph(
        'Ce reçu tient lieu de quittance pour le paiement mentionné ci-dessus.',
        STYLE_FOOTER
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


def _generate_receipt_number(payment, school):
    """
    Generate a unique receipt number.
    Format: RECU-{school_code}-{payment_id:06d}
    """
    school_code = (school.code or 'ECOLE').upper()
    return f'RECU-{school_code}-{payment.id:06d}'


def _mode_label(mode):
    """Translate payment mode to French label."""
    labels = {
        'especes': 'Espèces',
        'virement': 'Virement bancaire',
        'mobile_money': 'Mobile Money',
        'cheque': 'Chèque',
        'carte': 'Carte bancaire',
    }
    return labels.get(mode, mode)
