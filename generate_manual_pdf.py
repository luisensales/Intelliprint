"""Portable PDF builder using the canonical, complete user manual."""

import html
import os
import tempfile
from pathlib import Path

from reportlab import __file__ as reportlab_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, Image, LongTable, PageBreak, PageTemplate, Paragraph, Spacer, TableStyle

from PIL import Image as PillowImage
from manual_content import BASE_DIR, MANUAL_EDITION, MANUAL_TITLE, inline_html, parse_manual

OUTPUT_PDF = BASE_DIR / "Manual_de_Usuario_IntelliPrint.pdf"


def register_fonts():
    folder = Path(reportlab_file).parent / 'fonts'
    for name, file in [('ManualSans', 'Vera.ttf'), ('ManualSansBold', 'VeraBd.ttf'), ('ManualSansItalic', 'VeraIt.ttf'), ('ManualSansBoldItalic', 'VeraBI.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(folder / file)))
    pdfmetrics.registerFontFamily('ManualSans', normal='ManualSans', bold='ManualSansBold', italic='ManualSansItalic', boldItalic='ManualSansBoldItalic')


def formatted(text):
    return inline_html(text).replace('<strong>', '<b>').replace('</strong>', '</b>').replace('<code>', '<font name="Courier">').replace('</code>', '</font>')


class ManualDocument(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if getattr(flowable, '_manual_anchor', None):
            self.canv.bookmarkPage(flowable._manual_anchor)
            self.canv.addOutlineEntry(flowable.getPlainText(), flowable._manual_anchor, flowable._manual_level)


def build_manual_pdf(output_path=None):
    register_fonts()
    output_path = Path(output_path or OUTPUT_PDF)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = A4
    content_width = width - 40 * mm
    styles = {
        'body': ParagraphStyle('Body', fontName='ManualSans', fontSize=9.8, leading=12.6, spaceAfter=5.5, textColor=colors.black),
        'title': ParagraphStyle('Title', fontName='ManualSansBold', fontSize=24, leading=29, spaceBefore=10, spaceAfter=14, textColor=colors.black),
        'h1': ParagraphStyle('Chapter', fontName='ManualSansBold', fontSize=17.5, leading=22, spaceAfter=12, keepWithNext=True, textColor=colors.black),
        'h2': ParagraphStyle('Section', fontName='ManualSansBold', fontSize=12.5, leading=16.5, spaceBefore=10, spaceAfter=6, keepWithNext=True, textColor=colors.black),
        'h3': ParagraphStyle('Minor', fontName='ManualSansBold', fontSize=10.8, leading=14, spaceBefore=8, spaceAfter=5, keepWithNext=True, textColor=colors.black),
        'cell': ParagraphStyle('Cell', fontName='ManualSans', fontSize=8.6, leading=11.2, spaceAfter=1, textColor=colors.black),
        'head': ParagraphStyle('CellHeader', fontName='ManualSansBold', fontSize=8.8, leading=11.4, spaceAfter=1, textColor=colors.black),
    }
    fd, temporary = tempfile.mkstemp(suffix='.pdf', dir=output_path.parent)
    os.close(fd)
    try:
        document = ManualDocument(temporary, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                                  topMargin=19 * mm, bottomMargin=19 * mm, title=MANUAL_TITLE, author='IntelliPrint')
        def page_frame(canvas, doc):
            canvas.setFont('ManualSans', 8)
            canvas.setFillColor(colors.black)
            canvas.drawString(20 * mm, height - 11 * mm, f'IntelliPrint   Manual de usuario   Edición {MANUAL_EDITION}')
            canvas.drawRightString(width - 20 * mm, 10 * mm, f'Edición {MANUAL_EDITION}   |   {doc.page}')
        document.addPageTemplates(PageTemplate(id='Manual', frames=[Frame(20 * mm, 19 * mm, content_width, height - 38 * mm,
                                                                         leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=page_frame))
        blocks = parse_manual()
        first_chapter = next(i for i, b in enumerate(blocks) if b['kind'] == 'heading' and b['level'] == 2)
        story = []
        logos = []
        for name in ('logo-salesianos.png', 'logo-mendizabala.png', 'logo-dept-educacion-1.png'):
            path = BASE_DIR / 'assets' / name
            if path.exists():
                with PillowImage.open(path) as picture:
                    logo_width, logo_height = picture.size
                scale = min(44 / logo_width, 12 / logo_height)
                logos.append(Image(str(path), width=logo_width * scale * mm, height=logo_height * scale * mm))
        if logos:
            story.extend([LongTable([logos], colWidths=[content_width / len(logos)] * len(logos)), Spacer(1, 10 * mm)])
        logo = BASE_DIR / 'assets/Logo-intelliprint.png'
        if logo.exists():
            with PillowImage.open(logo) as picture:
                logo_width, logo_height = picture.size
            image = Image(str(logo), width=100 * mm, height=100 * logo_height / logo_width * mm)
            image.hAlign = 'LEFT'
            story.extend([image, Spacer(1, 12 * mm)])
        story.append(Paragraph(html.escape(MANUAL_TITLE), styles['title']))
        for block in blocks[1:first_chapter]:
            if block['kind'] == 'paragraph':
                story.append(Paragraph(formatted(block['text']), styles['body']))
        story.extend([PageBreak(), Paragraph('Índice de capítulos', styles['h1'])])
        for block in blocks:
            if block['kind'] == 'heading' and block['level'] == 2:
                story.append(Paragraph(f'<a href="#{block["anchor"]}">{html.escape(block["text"])}</a>', styles['body']))
        story.append(Paragraph('Usa los marcadores y la búsqueda del lector PDF para localizar un control.', styles['body']))
        for block in blocks[first_chapter:]:
            kind = block['kind']
            if kind == 'heading':
                if block['level'] == 2:
                    story.append(PageBreak())
                paragraph = Paragraph(html.escape(block['text']), styles['h' + str(block['level'] - 1)])
                paragraph._manual_anchor = block['anchor']
                paragraph._manual_level = block['level'] - 2
                story.append(paragraph)
            elif kind == 'paragraph':
                story.append(Paragraph(formatted(block['text']), styles['body']))
            elif kind == 'ordered_list':
                for number, item in enumerate(block['items'], 1):
                    story.append(Paragraph(f'{number}. {formatted(item)}', styles['body']))
            elif kind == 'bullet':
                story.append(Paragraph('- ' + formatted(block['text']), styles['body']))
            elif kind == 'table':
                rows = [[Paragraph(formatted(cell), styles['head' if row_index == 0 else 'cell']) for cell in row]
                        for row_index, row in enumerate(block['rows'])]
                widths = [52 * mm, 118 * mm] if len(rows[0]) == 2 else [46 * mm, 60 * mm, 64 * mm]
                table = LongTable(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
                table.setStyle(TableStyle([
                    ('GRID', (0, 0), (-1, -1), .5, colors.HexColor('#D9D9D9')),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8F0FA')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7F9FC')]),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5.5), ('RIGHTPADDING', (0, 0), (-1, -1), 5.5),
                    ('TOPPADDING', (0, 0), (-1, -1), 4.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
                ]))
                story.extend([table, Spacer(1, 6)])
        document.build(story)
        os.replace(temporary, output_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return output_path


if __name__ == '__main__':
    print(build_manual_pdf())
