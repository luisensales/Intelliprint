"""Build the editable manual from the same source used by the web and PDF."""

import os
import tempfile
from pathlib import Path

from docx import Document
from docx.shared import Mm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from PIL import Image

from manual_content import BASE_DIR, MANUAL_TITLE, MANUAL_EDITION, inline_parts, parse_manual

ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_PATH = BASE_DIR / "Manual_de_Usuario_IntelliPrint.docx"


def add_inline(paragraph, text, size=None):
    for kind, value, target in inline_parts(text):
        if kind == "link":
            hyperlink = OxmlElement("w:hyperlink")
            hyperlink.set(qn("r:id"), paragraph.part.relate_to(target, RT.HYPERLINK, is_external=True))
            run = OxmlElement("w:r")
            properties = OxmlElement("w:rPr")
            color = OxmlElement("w:color"); color.set(qn("w:val"), "174EA6"); properties.append(color)
            run.append(properties)
            node = OxmlElement("w:t"); node.text = value; run.append(node)
            hyperlink.append(run); paragraph._p.append(hyperlink)
        else:
            run = paragraph.add_run(value)
            run.bold = kind == "bold"
            if kind == "code":
                run.font.name = "Consolas"
            if size:
                run.font.size = Pt(size)


def add_table(doc, rows):
    count = len(rows[0])
    widths = [52, 118] if count == 2 else [46, 60, 64]
    table = doc.add_table(rows=0, cols=count)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for column, width in zip(table.columns, widths):
        column.width = Mm(width)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement("w:" + side)
        for key, value in (("val", "single"), ("sz", "4"), ("color", "D9D9D9")):
            border.set(qn("w:" + key), value)
        borders.append(border)
    table._tbl.tblPr.append(borders)
    for row_index, values in enumerate(rows):
        row = table.add_row()
        if row_index == 0:
            repeat = OxmlElement("w:tblHeader"); row._tr.get_or_add_trPr().append(repeat)
        cant_split = OxmlElement("w:cantSplit"); row._tr.get_or_add_trPr().append(cant_split)
        for cell_index, (cell, text) in enumerate(zip(row.cells, values)):
            cell.width = Mm(widths[cell_index])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            properties = cell._tc.get_or_add_tcPr()
            margins = OxmlElement("w:tcMar")
            for side in ("top", "left", "bottom", "right"):
                margin = OxmlElement("w:" + side)
                margin.set(qn("w:w"), "100"); margin.set(qn("w:type"), "dxa"); margins.append(margin)
            properties.append(margins)
            shade = OxmlElement("w:shd")
            shade.set(qn("w:fill"), "E8F0FA" if row_index == 0 else ("F7F9FC" if row_index % 2 == 0 else "FFFFFF"))
            properties.append(shade)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(2)
            paragraph.paragraph_format.line_spacing = 1.10
            add_inline(paragraph, text, 9.3)
            if row_index == 0:
                for run in paragraph.runs:
                    run.bold = True
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(3)
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.line_spacing = Pt(2)


def add_numbered_list(doc, items):
    numbering = doc.part.numbering_part.element
    abstract_id = max([int(n.get(qn("w:abstractNumId"))) for n in numbering.findall(qn("w:abstractNum"))] + [0]) + 1
    num_id = max([int(n.get(qn("w:numId"))) for n in numbering.findall(qn("w:num"))] + [0]) + 1
    abstract = OxmlElement("w:abstractNum"); abstract.set(qn("w:abstractNumId"), str(abstract_id))
    level = OxmlElement("w:lvl"); level.set(qn("w:ilvl"), "0")
    for name, value in (("start", "1"), ("numFmt", "decimal"), ("lvlText", "%1.")):
        element = OxmlElement("w:" + name); element.set(qn("w:val"), value); level.append(element)
    layout = OxmlElement('w:pPr')
    indent = OxmlElement('w:ind')
    indent.set(qn('w:left'), '340'); indent.set(qn('w:hanging'), '340')
    layout.append(indent); level.append(layout)
    abstract.append(level); numbering.append(abstract)
    number = OxmlElement("w:num"); number.set(qn("w:numId"), str(num_id))
    identifier = OxmlElement("w:abstractNumId"); identifier.set(qn("w:val"), str(abstract_id)); number.append(identifier); numbering.append(number)
    for text in items:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Mm(6)
        paragraph.paragraph_format.first_line_indent = Mm(-6)
        paragraph.paragraph_format.tab_stops.add_tab_stop(Mm(6))
        number_properties = paragraph._p.get_or_add_pPr().get_or_add_numPr()
        number_properties.get_or_add_ilvl().val = 0
        number_properties.get_or_add_numId().val = num_id
        add_inline(paragraph, text)


def build_manual_docx(output_path=None):
    output_path = Path(output_path or OUTPUT_PATH)
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.top_margin = section.bottom_margin = Mm(19)
    section.left_margin = section.right_margin = Mm(20)
    section.header_distance = section.footer_distance = Mm(8)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Arial", Pt(10.5)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.widow_control = True
    for name, size in (("Title", 26), ("Subtitle", 12), ("Heading 1", 18), ("Heading 2", 13), ("Heading 3", 11)):
        style = doc.styles[name]
        style.font.name, style.font.size = "Arial", Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = Pt(14)
        style.paragraph_format.space_after = Pt(7)
        for border in list(style.element.findall('.//' + qn('w:pBdr'))):
            border.getparent().remove(border)
    header = section.header.paragraphs[0]
    header.text = f"IntelliPrint   Manual de usuario   Edición {MANUAL_EDITION}"
    header.style = doc.styles["Normal"]
    for run in header.runs:
        run.font.size = Pt(8)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run(f"Edición {MANUAL_EDITION}   |   ")
    for instruction in ("PAGE", "NUMPAGES"):
        if instruction == "NUMPAGES":
            footer.add_run(" / ")
        field = OxmlElement("w:fldSimple"); field.set(qn("w:instr"), instruction); footer._p.append(field)
    for run in footer.runs:
        run.font.size = Pt(8)
    logos = doc.add_paragraph()
    logos.paragraph_format.space_after = Pt(20)
    for filename in ("logo-salesianos.png", "logo-mendizabala.png", "logo-dept-educacion-1.png"):
        path = ASSETS_DIR / filename
        if path.exists():
            with Image.open(path) as picture:
                width, height = picture.size
            scale = min(44 / width, 12 / height)
            logos.add_run().add_picture(str(path), width=Mm(width * scale), height=Mm(height * scale))
            logos.add_run("    ")
    logo = ASSETS_DIR / "Logo-intelliprint.png"
    if logo.exists():
        doc.add_paragraph().add_run().add_picture(str(logo), width=Mm(100))
    doc.add_paragraph(MANUAL_TITLE, style="Title")
    blocks = parse_manual()
    first_chapter = next(i for i, b in enumerate(blocks) if b['kind'] == 'heading' and b['level'] == 2)
    for block in blocks[1:first_chapter]:
        if block['kind'] == 'paragraph':
            add_inline(doc.add_paragraph(), block['text'])
    doc.add_page_break()
    doc.add_paragraph("Índice de capítulos", style="Heading 1")
    for block in blocks:
        if block['kind'] == 'heading' and block['level'] == 2:
            doc.add_paragraph(block['text'])
    doc.add_paragraph("Usa el panel de navegación de Word o los marcadores del lector PDF para recorrer los apartados. Busca un control por su nombre.")
    for block in blocks[first_chapter:]:
        kind = block['kind']
        if kind == 'heading':
            paragraph = doc.add_heading(block['text'], level=block['level'] - 1)
            if block['level'] == 2:
                paragraph.paragraph_format.space_before = Pt(0)
                paragraph.paragraph_format.page_break_before = True
        elif kind == 'paragraph':
            add_inline(doc.add_paragraph(), block['text'])
        elif kind == 'ordered_list':
            add_numbered_list(doc, block['items'])
        elif kind == 'bullet':
            add_inline(doc.add_paragraph(style='List Bullet'), block['text'])
        elif kind == 'table':
            add_table(doc, block['rows'])
    doc.core_properties.title = MANUAL_TITLE
    doc.core_properties.subject = "Opciones y operación de la aplicación"
    doc.core_properties.author = "IntelliPrint"
    doc.core_properties.version = MANUAL_EDITION
    settings = doc.settings.element
    update = OxmlElement("w:updateFields"); update.set(qn("w:val"), "true"); settings.append(update)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(suffix='.docx', dir=output_path.parent)
    os.close(fd)
    try:
        doc.save(temporary)
        os.replace(temporary, output_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return output_path


if __name__ == '__main__':
    print(build_manual_docx())
