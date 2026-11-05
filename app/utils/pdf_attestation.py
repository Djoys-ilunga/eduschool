"""
PDF Attestation de Scolarité Generator for EduSchool.
Uses reportlab to produce professional attestation PDFs.
"""

import io
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, Image
)


# ── Styles ──────────────────────────────────────────────────
_styles = getSampleStyleSheet()

STYLE_SCHOOL_NAME = ParagraphStyle(
    'AttestSchoolName', parent=_styles['Heading1'],
    fontSize=18, leading=22, alignment=TA_CENTER,
    spaceAfter=1 * mm, textColor=colors.HexColor('#1a237e'),
    fontName='Helvetica-Bold',
)

STYLE_SCHOOL_DETAILS = ParagraphStyle(
    'AttestSchoolDetails', parent=_styles['Normal'],
    fontSize=9, leading=12, alignment=TA_CENTER,
    spaceAfter=4 * mm, textColor=colors.HexColor('#546e7a'),
    fontName='Helvetica',
)

STYLE_TITLE = ParagraphStyle(
    'AttestTitle', parent=_styles['Heading2'],
    fontSize=16, leading=20, alignment=TA_CENTER,
    spaceAfter=6 * mm, textColor=colors.HexColor('#1a237e'),
    fontName='Helvetica-Bold',
)

STYLE_BODY = ParagraphStyle(
    'AttestBody', parent=_styles['Normal'],
    fontSize=12, leading=18, alignment=TA_JUSTIFY,
    spaceAfter=4 * mm, textColor=colors.black,
    fontName='Helvetica',
    firstLineIndent=0,
)

STYLE_DATE = ParagraphStyle(
    'AttestDate', parent=_styles['Normal'],
    fontSize=11, leading=14, alignment=TA_RIGHT,
    spaceBefore=10 * mm, spaceAfter=6 * mm,
    fontName='Helvetica',
)

STYLE_SIGNATURE = ParagraphStyle(
    'AttestSignature', parent=_styles['Normal'],
    fontSize=11, leading=14, alignment=TA_RIGHT,
    fontName='Helvetica-Bold',
)

STYLE_FOOTER = ParagraphStyle(
    'AttestFooter', parent=_styles['Normal'],
    fontSize=8, leading=10, alignment=TA_CENTER,
    textColor=colors.HexColor('#9e9e9e'),
    fontName='Helvetica',
)


def _sexe_text(sexe):
    """Retourne 'né' ou 'née' selon le sexe."""
    if sexe == 'F':
        return 'née'
    return 'né'


def _format_date(d):
    """Formate une date en version française lisible."""
    if d is None:
        return ''
    mois = [
        'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
        'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'
    ]
    if hasattr(d, 'day'):
        return f"{d.day} {mois[d.month - 1]} {d.year}"
    return str(d)


def generate_attestation_pdf(student_profile, school, enrollment):
    """
    Generate an attestation de scolarité PDF.

    Parameters
    ----------
    student_profile : StudentProfile
        The student's profile (includes date_naissance, lieu_naissance, sexe).
    school : School
        The School model instance (name, address, logo, cachet).
    enrollment : StudentEnrollment or None
        The active enrollment (class, academic_year).

    Returns
    -------
    bytes
        PDF content ready for download.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=25 * mm,
        topMargin=25 * mm,
        bottomMargin=25 * mm,
        title='Attestation de Scolarité',
        author='EduSchool',
    )

    elements = []

    # ── Logo (if present) ──
    logo_path = school.logo
    if logo_path:
        # Resolve relative path
        abs_logo = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            logo_path.lstrip('/').lstrip('\\')
        )
        if os.path.isfile(abs_logo):
            try:
                img = Image(abs_logo, width=20 * mm, height=20 * mm)
                img.hAlign = 'CENTER'
                elements.append(img)
                elements.append(Spacer(1, 3 * mm))
            except Exception:
                pass  # skip logo on error

    # ── School header ──
    elements.append(Paragraph(school.nom.upper(), STYLE_SCHOOL_NAME))

    # Build address line
    addr_parts = []
    if school.adresse:
        addr_parts.append(school.adresse)
    if school.ville:
        addr_parts.append(school.ville)
    if school.pays:
        addr_parts.append(school.pays)
    contact_parts = []
    if school.telephone:
        contact_parts.append(f'Tél: {school.telephone}')
    if school.email:
        contact_parts.append(f'Email: {school.email}')

    addr_line = ' — '.join(addr_parts)
    contact_line = ' | '.join(contact_parts)

    if addr_line:
        elements.append(Paragraph(addr_line, STYLE_SCHOOL_DETAILS))
    if contact_line:
        elements.append(Paragraph(contact_line, STYLE_SCHOOL_DETAILS))

    # ── Horizontal separator ──
    sep = Table([['']], colWidths=[160 * mm])
    sep.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 2, colors.HexColor('#1a237e')),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#1a237e')),
        ('TOPPADDING', (0, 0), (-1, 0), 0),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2 * mm),
    ]))
    elements.append(sep)

    # ── Title ──
    elements.append(Spacer(1, 5 * mm))
    elements.append(Paragraph('ATTESTATION DE SCOLARITÉ', STYLE_TITLE))

    # ── Body ──
    user = student_profile.user
    student_name = f"{user.prenom} {user.nom}"
    ne_ou_ne = _sexe_text(student_profile.sexe)

    date_naiss = _format_date(student_profile.date_naissance)
    lieu_naiss = student_profile.lieu_naissance or '________________'

    classe_nom = enrollment.classe.nom if enrollment else '________________'
    annee_nom = enrollment.annee_scolaire.nom if enrollment else '________________'

    # Director: use school name as fallback since no directeur field exists
    directeur = 'Le Directeur'

    body_text = (
        f"Je soussigné, <b>{directeur}</b> de <b>{school.nom}</b>, certifie que "
        f"<b>{student_name}</b>, {ne_ou_ne} le <b>{date_naiss}</b> à <b>{lieu_naiss}</b>, "
        f"est régulièrement inscrit(e) en classe de <b>{classe_nom}</b> "
        f"pour l'année scolaire <b>{annee_nom}</b>."
    )
    elements.append(Paragraph(body_text, STYLE_BODY))

    # Additional paragraph
    elements.append(Paragraph(
        "En foi de quoi, la présente attestation lui est délivrée pour servir "
        "et valoir ce que de droit.",
        STYLE_BODY
    ))

    # ── Date ──
    today_str = _format_date(datetime.now())
    elements.append(Paragraph(f"Fait à {school.ville or '________________'}, le {today_str}", STYLE_DATE))

    # ── Signature block ──
    elements.append(Spacer(1, 8 * mm))

    sig_data = [
        [
            Paragraph('', STYLE_SIGNATURE),
            Paragraph(f"<b>{directeur}</b>", STYLE_SIGNATURE),
        ],
        [
            Paragraph('', STYLE_SIGNATURE),
            Paragraph('____________________', STYLE_SIGNATURE),
        ],
    ]
    sig_tbl = Table(sig_data, colWidths=[90 * mm, 90 * mm])
    sig_tbl.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(sig_tbl)

    # ── Cachet placeholder ──
    if school.cachet:
        elements.append(Spacer(1, 5 * mm))
        elements.append(Paragraph(
            f'<i>Cachet de l\'école</i>',
            ParagraphStyle(
                'CachetLabel', parent=_styles['Normal'],
                fontSize=8, leading=10, alignment=TA_RIGHT,
                textColor=colors.HexColor('#9e9e9e'),
                fontName='Helvetica-Oblique',
            )
        ))

    # ── Footer line ──
    elements.append(Spacer(1, 10 * mm))
    footer_line = Table([['']], colWidths=[160 * mm])
    footer_line.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 1, colors.HexColor('#bdbdbd')),
        ('TOPPADDING', (0, 0), (-1, 0), 3),
    ]))
    elements.append(footer_line)
    elements.append(Paragraph(
        f"{school.nom} — Attestation générée le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — EduSchool",
        STYLE_FOOTER
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
