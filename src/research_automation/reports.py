"""Readable PDF copies of research notes; Markdown remains the evidence source."""
from __future__ import annotations

import io
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def report_font():
    name = "ResearchChinese"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    windows_font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msjh.ttc"
    if windows_font.is_file():
        pdfmetrics.registerFont(TTFont(name, str(windows_font), subfontIndex=0))
    else:
        # Standard Traditional Chinese CID font; supplied by the PDF viewer.
        name = "MSung-Light"
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(name))
    return name


def pdf_report(title, sections):
    font = report_font()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=44, leftMargin=44,
                            topMargin=42, bottomMargin=42, title=title, author="Degree Savior")
    body = ParagraphStyle("ResearchBody", fontName=font, fontSize=10, leading=16,
                          wordWrap="CJK", spaceAfter=7, splitLongWords=True)
    heading = ParagraphStyle("ResearchHeading", parent=body, fontSize=13, leading=20,
                             spaceBefore=12, keepWithNext=True, textColor=colors.HexColor("#155E75"))
    title_style = ParagraphStyle("ResearchTitle", parent=heading, fontSize=18, leading=26)
    story = [Paragraph(escape(title), title_style), Spacer(1, 8)]
    for label, text in sections:
        story.append(Paragraph(escape(label), heading))
        # Preserve visible sources without treating research text as PDF markup.
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", str(text))
        for paragraph in re.split(r"\n\s*\n", text):
            if paragraph.strip():
                story.append(Paragraph(escape(paragraph).replace("\n", "<br/>"), body))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(44, 25, "Degree Savior")
        canvas.drawRightString(A4[0] - 44, 25, str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
