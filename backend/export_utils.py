import re
from html import escape
from io import BytesIO
from typing import Any

from docx import Document
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


SCORING_DIMENSIONS = (
    ("skills_match", "Skills Match"),
    ("project_experience", "Project Experience"),
    ("education", "Education"),
    ("work_experience", "Work Experience"),
    ("keyword_match", "Keyword Match"),
)

ATS_FIELDS = (
    ("important_keywords", "Important Keywords"),
    ("matched_keywords", "Matched Keywords"),
    ("missing_keywords", "Missing Keywords"),
    ("keyword_suggestions", "Keyword Suggestions"),
)


def clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_filename_part(value: Any, fallback: str) -> str:
    text = clean_text(value, fallback)
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:60] or fallback


def build_export_filename(prefix: str, record: dict[str, Any], extension: str) -> str:
    company = safe_filename_part(record.get("company_name"), "unknown-company")
    title = safe_filename_part(record.get("job_title"), "unknown-position")
    return f"{prefix}-{company}-{title}.{extension}"


def build_cover_letter_docx(record: dict[str, Any]) -> BytesIO:
    document = Document()
    document.add_heading("Cover Letter", level=1)
    document.add_paragraph(f"Company Name: {clean_text(record.get('company_name'), 'Unknown Company')}")
    document.add_paragraph(f"Job Title: {clean_text(record.get('job_title'), 'Unknown Position')}")
    document.add_heading("Generated Cover Letter", level=2)

    cover_letter = clean_text(record.get("cover_letter"), "No cover letter generated.")
    for paragraph in cover_letter.splitlines() or [cover_letter]:
        document.add_paragraph(paragraph)

    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer


def get_pdf_font_name() -> str:
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light"
    except Exception:
        return "Helvetica"


def paragraph_text(value: Any, fallback: str = "Not provided") -> str:
    text = clean_text(value, fallback)
    return escape(text).replace("\n", "<br/>")


def add_heading(story: list[Any], text: str, style: ParagraphStyle) -> None:
    story.append(Paragraph(escape(text), style))
    story.append(Spacer(1, 0.08 * inch))


def add_paragraph_block(
    story: list[Any],
    title: str,
    value: Any,
    heading_style: ParagraphStyle,
    body_style: ParagraphStyle,
    fallback: str = "Not provided",
) -> None:
    add_heading(story, title, heading_style)
    story.append(Paragraph(paragraph_text(value, fallback), body_style))
    story.append(Spacer(1, 0.14 * inch))


def add_list_block(
    story: list[Any],
    title: str,
    items: Any,
    heading_style: ParagraphStyle,
    body_style: ParagraphStyle,
) -> None:
    add_heading(story, title, heading_style)
    safe_items = as_list(items)
    if not safe_items:
        story.append(Paragraph("No items found.", body_style))
    else:
        for item in safe_items:
            story.append(Paragraph(f"- {paragraph_text(item)}", body_style))
    story.append(Spacer(1, 0.14 * inch))


def add_summary_table(
    story: list[Any],
    record: dict[str, Any],
    body_style: ParagraphStyle,
) -> None:
    data = [
        ["Company Name", paragraph_text(record.get("company_name"), "Unknown Company")],
        ["Job Title", paragraph_text(record.get("job_title"), "Unknown Position")],
        ["Job URL", paragraph_text(record.get("job_url"))],
        ["Application Status", paragraph_text(record.get("application_status"), "Saved")],
        ["Match Score", f"{clean_text(record.get('match_score'), '0')}/100"],
    ]
    table = Table(
        [
            [
                Paragraph(f"<b>{escape(str(label))}</b>", body_style),
                Paragraph(str(value), body_style),
            ]
            for label, value in data
        ],
        colWidths=[1.75 * inch, 4.75 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf2f7")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.18 * inch))


def add_scoring_breakdown(
    story: list[Any],
    record: dict[str, Any],
    heading_style: ParagraphStyle,
    body_style: ParagraphStyle,
) -> None:
    add_heading(story, "Scoring Breakdown", heading_style)
    breakdown = as_dict(record.get("scoring_breakdown"))

    for key, label in SCORING_DIMENSIONS:
        section = as_dict(breakdown.get(key))
        score = clean_text(section.get("score"), "0")
        reason = paragraph_text(section.get("reason"), "No reason generated.")
        story.append(Paragraph(f"<b>{escape(label)}: {escape(score)}/100</b>", body_style))
        story.append(Paragraph(reason, body_style))
        evidence = as_list(section.get("evidence"))
        if evidence:
            for item in evidence:
                story.append(Paragraph(f"- {paragraph_text(item)}", body_style))
        else:
            story.append(Paragraph("- No evidence provided.", body_style))
        story.append(Spacer(1, 0.08 * inch))

    story.append(Spacer(1, 0.06 * inch))


def add_ats_analysis(
    story: list[Any],
    record: dict[str, Any],
    heading_style: ParagraphStyle,
    body_style: ParagraphStyle,
) -> None:
    add_heading(story, "ATS Keyword Analysis", heading_style)
    ats_analysis = as_dict(record.get("ats_analysis"))
    for key, label in ATS_FIELDS:
        story.append(Paragraph(f"<b>{escape(label)}</b>", body_style))
        items = as_list(ats_analysis.get(key))
        if items:
            story.append(Paragraph(paragraph_text(", ".join(items)), body_style))
        else:
            story.append(Paragraph("No keywords found.", body_style))
        story.append(Spacer(1, 0.08 * inch))

    story.append(Spacer(1, 0.06 * inch))


def add_upgraded_bullets(
    story: list[Any],
    record: dict[str, Any],
    heading_style: ParagraphStyle,
    body_style: ParagraphStyle,
) -> None:
    add_heading(story, "Upgraded Resume Bullets", heading_style)
    bullets = record.get("upgraded_resume_bullets")
    if not isinstance(bullets, list) or not bullets:
        story.append(Paragraph("No bullet improvements generated.", body_style))
        story.append(Spacer(1, 0.14 * inch))
        return

    for item in bullets:
        bullet = as_dict(item)
        original = paragraph_text(bullet.get("original"), "Not provided")
        improved = paragraph_text(bullet.get("improved"), "Not provided")
        reason = paragraph_text(bullet.get("reason"), "Not provided")
        story.append(Paragraph(f"<b>Original:</b> {original}", body_style))
        story.append(Paragraph(f"<b>Improved:</b> {improved}", body_style))
        story.append(Paragraph(f"<b>Reason:</b> {reason}", body_style))
        story.append(Spacer(1, 0.1 * inch))

    story.append(Spacer(1, 0.06 * inch))


def add_rag_sources(
    story: list[Any],
    record: dict[str, Any],
    heading_style: ParagraphStyle,
    body_style: ParagraphStyle,
) -> None:
    add_heading(story, "RAG Sources", heading_style)
    sources = record.get("rag_sources")
    if not isinstance(sources, list) or not sources:
        story.append(Paragraph("No RAG sources used.", body_style))
        story.append(Spacer(1, 0.14 * inch))
        return

    for source in sources:
        item = as_dict(source)
        title = paragraph_text(item.get("document_title"), "Untitled knowledge document")
        category = paragraph_text(item.get("category"), "Other")
        chunk_index = paragraph_text(item.get("chunk_index"), "0")
        reason = paragraph_text(item.get("relevance_reason"), "No relevance reason provided.")
        story.append(Paragraph(f"<b>{title}</b>", body_style))
        story.append(Paragraph(f"Category: {category} | Chunk Index: {chunk_index}", body_style))
        story.append(Paragraph(f"Reason: {reason}", body_style))
        story.append(Spacer(1, 0.1 * inch))

    story.append(Spacer(1, 0.06 * inch))


def build_analysis_report_pdf(record: dict[str, Any]) -> BytesIO:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title="Personal Job Application Analysis Report",
    )

    font_name = get_pdf_font_name()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ExportTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#12332d"),
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "ExportHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#166b5f"),
        spaceBefore=6,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "ExportBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9.5,
        leading=13,
        spaceAfter=3,
    )

    story: list[Any] = [
        Paragraph("Personal Job Application Analysis Report", title_style),
    ]
    add_summary_table(story, record, body_style)
    add_paragraph_block(story, "Match Reason", record.get("match_reason"), heading_style, body_style)
    add_paragraph_block(story, "Job Summary", record.get("job_summary"), heading_style, body_style)
    add_scoring_breakdown(story, record, heading_style, body_style)
    add_ats_analysis(story, record, heading_style, body_style)
    add_list_block(story, "Matched Skills", record.get("matched_skills"), heading_style, body_style)
    add_list_block(story, "Missing Skills", record.get("missing_skills"), heading_style, body_style)
    add_list_block(
        story,
        "Resume Suggestions",
        record.get("resume_suggestions"),
        heading_style,
        body_style,
    )
    add_upgraded_bullets(story, record, heading_style, body_style)
    add_rag_sources(story, record, heading_style, body_style)
    add_paragraph_block(
        story,
        "Cover Letter",
        record.get("cover_letter"),
        heading_style,
        body_style,
        fallback="No cover letter generated.",
    )

    document.build(story)
    buffer.seek(0)
    return buffer
