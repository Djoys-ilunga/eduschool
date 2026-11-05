"""
PDF Bulletin Generator for EduSchool.
Uses reportlab to produce professional bulletin PDFs.
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
    Spacer, Image, PageBreak
)
from reportlab.pdfgen import canvas as pdfgen_canvas


# ── Styles ──────────────────────────────────────────────────
_styles = getSampleStyleSheet()

STYLE_TITLE = ParagraphStyle(
    'BulletinTitle', parent=_styles['Heading1'],
    fontSize=16, leading=20, alignment=TA_CENTER,
    spaceAfter=2 * mm, textColor=colors.HexColor('#1a237e'),
    fontName='Helvetica-Bold',
)

STYLE_SUBTITLE = ParagraphStyle(
    'BulletinSubtitle', parent=_styles['Heading2'],
    fontSize=12, leading=14, alignment=TA_CENTER,
    spaceAfter=4 * mm, textColor=colors.HexColor('#37474f'),
    fontName='Helvetica',
)

STYLE_STUDENT_NAME = ParagraphStyle(
    'StudentName', parent=_styles['Normal'],
    fontSize=11, leading=13, fontName='Helvetica-Bold',
    textColor=colors.HexColor('#1a237e'),
)

STYLE_SECTION_TITLE = ParagraphStyle(
    'SectionTitle', parent=_styles['Normal'],
    fontSize=10, leading=12, fontName='Helvetica-Bold',
    textColor=colors.HexColor('#37474f'),
    spaceBefore=3 * mm, spaceAfter=2 * mm,
)

STYLE_CELL = ParagraphStyle(
    'BulletinCell', parent=_styles['Normal'],
    fontSize=9, leading=11, alignment=TA_CENTER,
    fontName='Helvetica',
)

STYLE_CELL_LEFT = ParagraphStyle(
    'BulletinCellLeft', parent=STYLE_CELL,
    alignment=TA_LEFT,
)

STYLE_SMALL = ParagraphStyle(
    'BulletinSmall', parent=_styles['Normal'],
    fontSize=8, leading=10, alignment=TA_CENTER,
    textColor=colors.HexColor('#757575'),
)

STYLE_FOOTER = ParagraphStyle(
    'BulletinFooter', parent=_styles['Normal'],
    fontSize=9, leading=11, alignment=TA_LEFT,
    fontName='Helvetica',
)

STYLE_SIGNATURE = ParagraphStyle(
    'Signature', parent=_styles['Normal'],
    fontSize=9, leading=11, alignment=TA_CENTER,
    fontName='Helvetica',
)

STYLE_APPRECIATION = ParagraphStyle(
    'AppreciationStyle', parent=_styles['Normal'],
    fontSize=9, leading=11, fontName='Helvetica-Oblique',
    textColor=colors.HexColor('#546e7a'),
)


def _build_cells(text, style=STYLE_CELL):
    """Helper: wrap text in a Paragraph for the table."""
    return Paragraph(str(text) if text is not None else '-', style)


def _appreciation_text(avg):
    """Map numeric average → French appreciation."""
    if avg is None:
        return '-'
    if avg >= 16:
        return 'Très Bien'
    if avg >= 14:
        return 'Bien'
    if avg >= 12:
        return 'Assez Bien'
    if avg >= 10:
        return 'Passable'
    return 'Insuffisant'


def _make_signature_block():
    """Return a 3-column signature table."""
    sig_data = [
        [
            Paragraph('Le Directeur', STYLE_SIGNATURE),
            Paragraph("Le Titulaire", STYLE_SIGNATURE),
            Paragraph("Le Parent", STYLE_SIGNATURE),
        ],
        [
            Paragraph('_________________', STYLE_SIGNATURE),
            Paragraph('_________________', STYLE_SIGNATURE),
            Paragraph('_________________', STYLE_SIGNATURE),
        ],
    ]
    tbl = Table(sig_data, colWidths=[170, 170, 170])
    tbl.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5 * mm),
    ]))
    return tbl


def generate_bulletin_pdf(bulletin_data, school, period=None, trimester=None):
    """
    Generate a bulletin PDF for a class.

    Parameters
    ----------
    bulletin_data : dict or None
        Output of _compute_bulletin() – must contain 'students' list.
    school : School
        The School model instance (for name, address, etc.).
    period : Period or None
        Period model instance (if bulletin is for a specific period).
    trimester : Trimester or None
        Trimester model instance (if bulletin is for a full trimester/semester).

    Returns
    -------
    bytes
        PDF content ready for download.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title='Bulletin Scolaire',
        author='EduSchool',
    )

    elements = []

    # ── Header ──
    elements.append(Paragraph('BULLETIN SCOLAIRE', STYLE_TITLE))
    elements.append(Paragraph(school.nom.upper(), STYLE_TITLE))

    # Subtitle
    div_label = school.division_label  # 'Trimestre' or 'Semestre'
    if trimester and period:
        subtitle = f'{div_label} {trimester.numero} — {trimester.nom}  |  {period.nom}'
    elif trimester:
        subtitle = f'{div_label} {trimester.numero} — {trimester.nom}'
    elif period and period.trimestre:
        t = period.trimestre
        subtitle = f'{div_label} {t.numero} — {t.nom}  |  {period.nom}'
    else:
        subtitle = ''

    if subtitle:
        elements.append(Paragraph(subtitle, STYLE_SUBTITLE))
    elements.append(Spacer(1, 3 * mm))

    if not bulletin_data or not bulletin_data.get('students'):
        elements.append(Paragraph(
            '<i>Aucune donnée de bulletin disponible.</i>',
            STYLE_CELL
        ))
        doc.build(elements)
        buffer.seek(0)
        return buffer.read()

    students = bulletin_data['students']
    periods_list = bulletin_data.get('periods', [])

    # ── Per-student pages ──
    for idx, sr in enumerate(students):
        if idx > 0:
            elements.append(PageBreak())

        student_user = sr['student']
        student_name = f"{student_user.prenom} {student_user.nom}"

        # Student identity header
        elements.append(Paragraph(
            f"Élève : {student_name}",
            STYLE_STUDENT_NAME
        ))

        # Matricule if available
        sp = sr.get('student_profile')
        if sp and sp.matricule:
            elements.append(Paragraph(
                f"Matricule : {sp.matricule}",
                STYLE_SMALL
            ))

        elements.append(Spacer(1, 4 * mm))

        # ── Subject table ──
        # Headers: Matière | Coef | Note/20 | Appréciation
        table_data = [
            [
                _build_cells('Matière', STYLE_CELL_LEFT),
                _build_cells('Coef', STYLE_CELL),
                _build_cells('Note/20', STYLE_CELL),
                _build_cells('Appréciation', STYLE_CELL),
            ]
        ]

        for subj in sr['subjects']:
            avg_val = f"{subj['avg']}" if subj['avg'] is not None else '-'
            table_data.append([
                _build_cells(subj['subject'].nom, STYLE_CELL_LEFT),
                _build_cells(str(subj['cs'].coefficient), STYLE_CELL),
                _build_cells(avg_val, STYLE_CELL),
                _build_cells(
                    _appreciation_text(subj['avg']),
                    STYLE_CELL,
                ),
            ])

        col_widths = [210, 45, 60, 195]  # total ≈ 510 (A4 width minus margins ≈ 180mm)
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

        tbl_style = TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            # Body
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#bdbdbd')),
            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            # Alignments
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (2, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ])
        tbl.setStyle(tbl_style)
        elements.append(tbl)

        elements.append(Spacer(1, 6 * mm))

        # ── Summary block ──
        # Two-column layout: summary left, date right
        moy = sr.get('moyenne_generale', 0) or 0
        rank = sr.get('rank', '-')
        total = bulletin_data.get('total_eleves', len(students))
        appreciation = sr.get('appreciation', _appreciation_text(moy))

        summary_text = (
            f"<b>Moyenne Générale :</b> {moy:.2f}/20<br/>"
            f"<b>Rang :</b> {rank}/{total}<br/>"
            f"<b>Appréciation :</b> {appreciation}"
        )
        elements.append(Paragraph(summary_text, STYLE_FOOTER))

        # Date
        date_str = datetime.now().strftime('%d/%m/%Y')
        elements.append(Spacer(1, 3 * mm))
        elements.append(Paragraph(
            f"<b>Date :</b> {date_str}",
            STYLE_FOOTER
        ))

        elements.append(Spacer(1, 8 * mm))

        # ── Signature block ──
        elements.append(_make_signature_block())

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


def generate_student_bulletin_pdf(student_data, school, division_item=None, is_period=True):
    """
    Generate an individual student bulletin PDF.

    Parameters
    ----------
    student_data : dict
        A single student entry from _compute_bulletin() output.
        (i.e. bulletin_data['students'][0] when filtered for one student)
    school : School
        School model instance.
    division_item : Period or Trimester or None
        The period or trimester being reported.
    is_period : bool
        True if division_item is a Period, False if it's a Trimester.

    Returns
    -------
    bytes
        PDF content.
    """
    # Wrap single student in bulletin_data structure
    fake_data = {
        'students': [student_data],
        'periods': student_data.get('_periods', []),
        'total_eleves': 1,
        'total_subjects': len(student_data.get('subjects', [])),
    }
    return generate_bulletin_pdf(fake_data, school, 
                                 period=division_item if is_period else None,
                                 trimester=division_item if not is_period else None)
