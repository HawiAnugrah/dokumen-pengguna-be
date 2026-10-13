import io
import re
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    HRFlowable,
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Canvas yang menghitung total halaman dan menggambar footer 'Halaman X dari Y' serta running header."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Hanya tampilkan header & footer di halaman 2 ke atas (halaman 1 adalah cover)
        if self._pageNumber > 1:
            # Header
            self.drawString(40, 810, "Userdoc — Dokumen Spesifikasi Kebutuhan Proyek")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(40, 804, 555, 804)

            # Footer
            self.line(40, 45, 555, 45)
            self.drawString(40, 32, f"Dicetak otomatis oleh Userdoc AI Platform • {datetime.now().strftime('%d %b %Y')}")
            page_text = f"Halaman {self._pageNumber} dari {page_count}"
            self.drawRightString(555, 32, page_text)

        self.restoreState()

def clean_text(text: str) -> str:
    """Membersihkan teks dan escape karakter khusus XML untuk Paragraph reportlab."""
    if not text:
        return ""
    text = str(text)
    # Ganti ampersand dulu, lalu < dan >
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Ganti newline dengan <br/>
    text = text.replace("\n", "<br/>")
    return text

def build_project_pdf(project) -> bytes:
    """
    Menghasilkan file PDF lengkap berisi spesifikasi kebutuhan proyek (PRD / SRS).
    Mencakup Overview, User Types, Personas, Epics, Stories, Acceptance Criteria,
    Test Cases, Tech Notes, NFRs, Journeys, Tech Stack, dan Dev Plans.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=50,
        bottomMargin=55,
    )

    styles = getSampleStyleSheet()

    # Warna tema
    PRIMARY = colors.HexColor("#1E3A8A")       # Deep Blue
    SECONDARY = colors.HexColor("#2563EB")     # Blue
    ACCENT = colors.HexColor("#0D9488")        # Teal
    TEXT_DARK = colors.HexColor("#0F172A")     # Slate 900
    TEXT_MUTED = colors.HexColor("#475569")    # Slate 600
    BG_LIGHT = colors.HexColor("#F8FAFC")      # Slate 50
    BORDER_LIGHT = colors.HexColor("#E2E8F0")  # Slate 200

    # Custom typography styles
    style_cover_title = ParagraphStyle(
        'CoverTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=PRIMARY,
        spaceAfter=8,
    )

    style_cover_subtitle = ParagraphStyle(
        'CoverSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=TEXT_MUTED,
        spaceAfter=15,
    )

    style_h1 = ParagraphStyle(
        'SectionH1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=PRIMARY,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )

    style_h2 = ParagraphStyle(
        'SectionH2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=SECONDARY,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )

    style_body = ParagraphStyle(
        'BodyCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=TEXT_DARK,
        spaceAfter=4,
    )

    style_body_bold = ParagraphStyle(
        'BodyBoldCustom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=13,
        textColor=TEXT_DARK,
        spaceAfter=4,
    )

    style_caption = ParagraphStyle(
        'CaptionCustom',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=11,
        textColor=TEXT_MUTED,
    )

    story_elements = []

    # ================= COVER / HEADER =================
    story_elements.append(Paragraph("DOKUMEN SPESIFIKASI KEBUTUHAN PERANGKAT LUNAK", style_caption))
    story_elements.append(Spacer(1, 4))
    story_elements.append(Paragraph(clean_text(project.name), style_cover_title))
    
    workspace_name = project.workspace.name if project.workspace else "Workspace"
    created_date = project.created_at.strftime("%d %B %Y") if project.created_at else datetime.now().strftime("%d %B %Y")
    meta_sub = f"Workspace: <b>{clean_text(workspace_name)}</b> &nbsp;|&nbsp; Tanggal Dibuat: <b>{created_date}</b>"
    story_elements.append(Paragraph(meta_sub, style_cover_subtitle))
    story_elements.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY, spaceBefore=4, spaceAfter=14))

    # Ringkasan Proyek
    overview_data = [
        [Paragraph("<b>Domain Bisnis</b>", style_body), Paragraph(clean_text(project.domain_business or "Belum ditentukan"), style_body)],
        [Paragraph("<b>Tipe Aplikasi</b>", style_body), Paragraph(clean_text(project.application_type or "Belum ditentukan"), style_body)],
        [Paragraph("<b>Target Pengguna</b>", style_body), Paragraph(clean_text(project.target_users or "-"), style_body)],
        [Paragraph("<b>Tujuan Bisnis</b>", style_body), Paragraph(clean_text(project.business_goals or "-"), style_body)],
        [Paragraph("<b>Deskripsi</b>", style_body), Paragraph(clean_text(project.description or "Tidak ada deskripsi"), style_body)],
    ]
    if project.repo_url:
        overview_data.append([Paragraph("<b>Repository</b>", style_body), Paragraph(clean_text(project.repo_url), style_body)])

    overview_table = Table(overview_data, colWidths=[120, 395])
    overview_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story_elements.append(overview_table)
    story_elements.append(Spacer(1, 14))

    # ================= 1. USER TYPES & PERSONAS =================
    user_types = getattr(project, "user_types", []) or []
    if user_types:
        story_elements.append(Paragraph("1. Tipe Pengguna & Persona (User Types & Personas)", style_h1))
        story_elements.append(HRFlowable(width="100%", thickness=0.5, color=SECONDARY, spaceBefore=2, spaceAfter=8))

        for idx, ut in enumerate(user_types, 1):
            story_elements.append(Paragraph(f"1.{idx}. {clean_text(ut.name)}", style_h2))
            if ut.description:
                story_elements.append(Paragraph(clean_text(ut.description), style_body))

            personas = getattr(ut, "personas", []) or []
            if personas:
                for p in personas:
                    persona_rows = [
                        [Paragraph(f"<b>Persona: {clean_text(p.name)}</b>", style_body_bold), Paragraph(f"Jabatan: {clean_text(p.job_title or '-')}", style_body)],
                        [Paragraph(f"Usia: {p.age if p.age else '-'} • Lokasi: {clean_text(p.location or '-')}", style_caption), Paragraph(f"Status: {clean_text(p.family_status or '-')}", style_caption)],
                    ]
                    if p.about:
                        persona_rows.append([Paragraph("<b>Latar Belakang:</b>", style_body), Paragraph(clean_text(p.about), style_body)])
                    if p.goals:
                        persona_rows.append([Paragraph("<b>Goals (Tujuan):</b>", style_body), Paragraph(clean_text(p.goals), style_body)])
                    if p.frustrations:
                        persona_rows.append([Paragraph("<b>Frustrations:</b>", style_body), Paragraph(clean_text(p.frustrations), style_body)])

                    p_table = Table(persona_rows, colWidths=[120, 395])
                    p_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('TOPPADDING', (0, 0), (-1, -1), 4),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                        ('LEFTPADDING', (0, 0), (-1, -1), 6),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ]))
                    story_elements.append(Spacer(1, 4))
                    story_elements.append(p_table)
            story_elements.append(Spacer(1, 8))

    # ================= 2. EPICS & USER STORIES =================
    epics = getattr(project, "epics", []) or []
    if epics:
        story_elements.append(Spacer(1, 6))
        story_elements.append(Paragraph("2. Kebutuhan Fungsional (Epics & User Stories)", style_h1))
        story_elements.append(HRFlowable(width="100%", thickness=0.5, color=SECONDARY, spaceBefore=2, spaceAfter=8))

        for e_idx, epic in enumerate(epics, 1):
            story_elements.append(Paragraph(f"Epic 2.{e_idx}: {clean_text(epic.name)}", style_h2))
            if epic.description:
                story_elements.append(Paragraph(clean_text(epic.description), style_body))

            stories = getattr(epic, "stories", []) or []
            if not stories:
                story_elements.append(Paragraph("<i>Belum ada User Story pada Epic ini.</i>", style_caption))
            else:
                for s in stories:
                    code_badge = s.code or f"US-{s.id}"
                    status_badge = f"[{s.status.upper() if s.status else 'DRAFT'}]"
                    
                    # Story narrative
                    role_text = s.as_a or (s.user_type.name if s.user_type else "Pengguna")
                    narrative = f"<b>{code_badge}</b> {status_badge}<br/>"
                    narrative += f"<b>Sebagai</b> {clean_text(role_text)}, "
                    narrative += f"<b>saya ingin</b> {clean_text(s.i_want)}"
                    if s.so_that:
                        narrative += f", <b>sehingga</b> {clean_text(s.so_that)}."
                    else:
                        narrative += "."

                    story_box_data = [[Paragraph(narrative, style_body)]]

                    # Acceptance Criteria
                    ac_list = getattr(s, "acceptance_criteria", []) or []
                    if ac_list:
                        ac_text = "<b>Acceptance Criteria:</b><br/>"
                        for idx_ac, ac in enumerate(ac_list, 1):
                            ac_text += f"&nbsp;&nbsp;• {clean_text(ac.description)}<br/>"
                        story_box_data.append([Paragraph(ac_text, style_body)])

                    # Tech Notes
                    tech_notes = getattr(s, "tech_notes", []) or []
                    if tech_notes:
                        tn_text = "<b>Catatan Teknis (Tech Notes):</b><br/>"
                        for tn in tech_notes:
                            tn_text += f"&nbsp;&nbsp;<i>{clean_text(tn.content)}</i><br/>"
                        story_box_data.append([Paragraph(tn_text, style_body)])

                    # Test Cases
                    test_cases = getattr(s, "test_cases", []) or []
                    if test_cases:
                        tc_text = "<b>Skenario Pengujian (Test Cases):</b><br/>"
                        for idx_tc, tc in enumerate(test_cases, 1):
                            tc_text += f"&nbsp;&nbsp;<b>TC-{idx_tc}:</b> {clean_text(tc.action)} &rarr; <i>Ekspektasi: {clean_text(tc.expected_result)}</i><br/>"
                        story_box_data.append([Paragraph(tc_text, style_body)])

                    story_table = Table(story_box_data, colWidths=[515])
                    story_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
                        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                        ('LINEBEFORE', (0, 0), (0, -1), 3, SECONDARY),
                        ('TOPPADDING', (0, 0), (-1, -1), 4),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                        ('LEFTPADDING', (0, 0), (-1, -1), 8),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                    ]))
                    story_elements.append(Spacer(1, 4))
                    story_elements.append(story_table)

            story_elements.append(Spacer(1, 8))

    # ================= 3. NON-FUNCTIONAL REQUIREMENTS =================
    nfrs = getattr(project, "nfrs", []) or []
    if nfrs:
        story_elements.append(Spacer(1, 6))
        story_elements.append(Paragraph("3. Kebutuhan Non-Fungsional (Non-Functional Requirements)", style_h1))
        story_elements.append(HRFlowable(width="100%", thickness=0.5, color=SECONDARY, spaceBefore=2, spaceAfter=8))

        nfr_rows = [[Paragraph("<b>Kategori</b>", style_body_bold), Paragraph("<b>Spesifikasi Kebutuhan</b>", style_body_bold)]]
        for nfr in nfrs:
            nfr_rows.append([
                Paragraph(clean_text(nfr.category), style_body),
                Paragraph(clean_text(nfr.description), style_body),
            ])

        nfr_table = Table(nfr_rows, colWidths=[130, 385])
        nfr_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story_elements.append(nfr_table)
        story_elements.append(Spacer(1, 10))

    # ================= 4. USER JOURNEYS =================
    journeys = getattr(project, "user_journeys", []) or []
    if journeys:
        story_elements.append(Spacer(1, 6))
        story_elements.append(Paragraph("4. Alur Perjalanan Pengguna (User Journeys)", style_h1))
        story_elements.append(HRFlowable(width="100%", thickness=0.5, color=SECONDARY, spaceBefore=2, spaceAfter=8))

        for j_idx, j in enumerate(journeys, 1):
            story_elements.append(Paragraph(f"4.{j_idx}. {clean_text(j.name)}", style_h2))
            if j.description:
                story_elements.append(Paragraph(clean_text(j.description), style_body))

            steps = sorted(getattr(j, "steps", []) or [], key=lambda x: x.step_order)
            if steps:
                for s in steps:
                    p_name = s.persona.name if s.persona else "Pengguna"
                    step_header = f"<b>Langkah {s.step_order}: {clean_text(s.title)}</b> &nbsp;&nbsp;|&nbsp;&nbsp; <i>Persona: {clean_text(p_name)}</i>"
                    story_elements.append(Spacer(1, 4))
                    story_elements.append(Paragraph(step_header, style_body_bold))
                    if s.description:
                        desc_clean = clean_text(s.description)
                        for part in desc_clean.split("<br/>"):
                            if part.strip():
                                story_elements.append(Paragraph(part.strip(), style_body))
                    story_elements.append(Spacer(1, 4))
            story_elements.append(Spacer(1, 8))

    # ================= 5. BUILD MODULE (TECH STACK & GUIDELINES) =================
    tech_stack = getattr(project, "tech_stack", None)
    guidelines = getattr(project, "coding_guidelines", []) or []
    plans = getattr(project, "development_plans", []) or []

    if tech_stack or guidelines or plans:
        story_elements.append(Spacer(1, 6))
        story_elements.append(Paragraph("5. Arsitektur Teknis & Panduan Coding (Build Module)", style_h1))
        story_elements.append(HRFlowable(width="100%", thickness=0.5, color=SECONDARY, spaceBefore=2, spaceAfter=8))

        if tech_stack:
            story_elements.append(Paragraph("5.1. Konfigurasi Technology Stack", style_h2))
            ts_rows = [
                [Paragraph("<b>Platform</b>", style_body), Paragraph(clean_text(tech_stack.platform or "-"), style_body)],
                [Paragraph("<b>UI Framework & Bahasa</b>", style_body), Paragraph(f"{clean_text(tech_stack.ui_framework or '-')} ({clean_text(tech_stack.ui_language or '-')})", style_body)],
                [Paragraph("<b>UI Library</b>", style_body), Paragraph(clean_text(tech_stack.ui_library or "-"), style_body)],
                [Paragraph("<b>Application Layer</b>", style_body), Paragraph(f"{clean_text(tech_stack.app_framework or '-')} ({clean_text(tech_language := tech_stack.app_language or '-')})", style_body)],
                [Paragraph("<b>Data Layer (Database)</b>", style_body), Paragraph(clean_text(tech_stack.data_layer or "-"), style_body)],
                [Paragraph("<b>Integration Layer</b>", style_body), Paragraph(clean_text(tech_stack.integration_layer or "-"), style_body)],
                [Paragraph("<b>Skala Pengguna</b>", style_body), Paragraph(clean_text(tech_stack.scale or "-"), style_body)],
            ]
            ts_table = Table(ts_rows, colWidths=[150, 365])
            ts_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
                ('BOX', (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]))
            story_elements.append(ts_table)
            story_elements.append(Spacer(1, 8))

        if guidelines:
            story_elements.append(Paragraph("5.2. Coding Guidelines & Architecture Rules", style_h2))
            for g in guidelines:
                cat_label = f"[{g.category.upper()}] " if g.category else ""
                g_content = [
                    [Paragraph(f"<b>{cat_label}{clean_text(g.title)}</b>", style_body_bold)],
                    [Paragraph(clean_text(g.content), style_body)],
                ]
                g_table = Table(g_content, colWidths=[515])
                g_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ]))
                story_elements.append(Spacer(1, 4))
                story_elements.append(g_table)
            story_elements.append(Spacer(1, 8))

        if plans:
            story_elements.append(Paragraph("5.3. Rencana Pengembangan (Development Plans)", style_h2))
            plan_rows = [[
                Paragraph("<b>Tugas / Fitur</b>", style_body_bold),
                Paragraph("<b>Status</b>", style_body_bold),
                Paragraph("<b>Deskripsi</b>", style_body_bold),
            ]]
            for p in plans:
                plan_rows.append([
                    Paragraph(clean_text(p.title), style_body),
                    Paragraph(f"<b>{clean_text(p.status.upper() if p.status else 'TODO')}</b>", style_body),
                    Paragraph(clean_text(p.description or "-"), style_body),
                ])
            plan_table = Table(plan_rows, colWidths=[150, 75, 290])
            plan_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ('BOX', (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]))
            story_elements.append(Spacer(1, 4))
            story_elements.append(plan_table)

    # Bangun dokumen menggunakan NumberedCanvas
    doc.build(story_elements, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
