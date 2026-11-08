"""
generate_manual_docx.py
=======================
Generador del Manual de Usuario Oficial de IntelliPrint en formato Microsoft Word (.docx).
Diseño profesional y maquetación editorial para Salesianos Urnieta, CIFP Mendizabala LHII
y Departamento de Educación del Gobierno Vasco.
"""

import os
import io
from pathlib import Path
from PIL import Image
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_PATH = BASE_DIR / "Manual_de_Usuario_IntelliPrint.docx"

# Colores corporativos IntelliPrint / FP
C_NAVY = RGBColor(31, 38, 44)         # #1F262C
C_BLUE = RGBColor(37, 99, 235)        # #2563EB
C_PURPLE = RGBColor(109, 40, 217)     # #6D28D9
C_DARK_SLATE = RGBColor(51, 65, 85)   # #334155
C_MUTED = RGBColor(100, 116, 139)     # #64748B
C_EMERALD = RGBColor(5, 150, 105)     # #059669
C_AMBER = RGBColor(217, 119, 6)       # #D97706
C_ROSE = RGBColor(225, 29, 72)        # #E11D48

HEX_NAVY = "1F262C"
HEX_BLUE = "2563EB"
HEX_LIGHT_BLUE = "EFF6FF"
HEX_LIGHT_GRAY = "F8FAFC"
HEX_BORDER = "CBD5E1"
HEX_EMERALD = "059669"
HEX_LIGHT_GREEN = "ECFDF5"
HEX_AMBER = "D97706"
HEX_LIGHT_AMBER = "FFFBEB"
HEX_PURPLE = "6D28D9"
HEX_LIGHT_PURPLE = "F5F3FF"


def get_docx_image_stream(path: Path) -> io.BytesIO:
    """Asegura que cualquier imagen sea convertida a un stream PNG limpio reconocido por python-docx."""
    im = Image.open(path)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    buf.seek(0)
    return buf


def set_cell_background(cell, fill_hex):
    """Establece el color de fondo de una celda XML."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=140, bottom=140, left=180, right=180):
    """Establece márgenes interiores (padding) de celda en dxa (1 pt = 20 dxa)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def set_cell_border_left_accent(cell, border_hex="2563EB", border_size="36"):
    """Crea un recuadro de aviso con borde grueso a la izquierda y sin bordes en los otros lados."""
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:left w:val="single" w:sz="{border_size}" w:space="0" w:color="{border_hex}"/>'
        f'<w:top w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'<w:bottom w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)


def set_table_borders(table, border_hex="E2E8F0"):
    """Establece bordes sutiles en tablas de datos."""
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="{border_hex}"/>'
        f'<w:bottom w:val="single" w:sz="12" w:space="0" w:color="1F262C"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{border_hex}"/>'
        f'<w:insideV w:val="none"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


def add_callout(doc, title, text, style="blue"):
    """Inserta una caja de llamada destacada."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False

    cell = tbl.cell(0, 0)
    cell.width = Inches(6.5)

    if style == "emerald":
        bg_hex, border_hex, icon = HEX_LIGHT_GREEN, HEX_EMERALD, "✓ "
        t_color = C_EMERALD
    elif style == "amber":
        bg_hex, border_hex, icon = HEX_LIGHT_AMBER, HEX_AMBER, "⚠ "
        t_color = C_AMBER
    elif style == "purple":
        bg_hex, border_hex, icon = HEX_LIGHT_PURPLE, HEX_PURPLE, "🎓 "
        t_color = C_PURPLE
    else:
        bg_hex, border_hex, icon = HEX_LIGHT_BLUE, HEX_BLUE, "ℹ "
        t_color = C_BLUE

    set_cell_background(cell, bg_hex)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=180)
    set_cell_border_left_accent(cell, border_hex=border_hex, border_size="32")

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.15

    r_title = p.add_run(f"{icon}{title}\n")
    r_title.bold = True
    r_title.font.name = "Calibri"
    r_title.font.size = Pt(10.5)
    r_title.font.color.rgb = t_color

    r_text = p.add_run(text)
    r_text.font.name = "Calibri"
    r_text.font.size = Pt(9.5)
    r_text.font.color.rgb = C_DARK_SLATE

    # Espacio tras la tabla
    p_after = doc.add_paragraph()
    p_after.paragraph_format.space_before = Pt(0)
    p_after.paragraph_format.space_after = Pt(4)


def add_heading_1_styled(doc, text):
    """Encabezado 1 con estilo moderno y barra inferior."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True

    run = p.add_run(text)
    run.bold = True
    run.font.name = "Calibri"
    run.font.size = Pt(15.0)
    run.font.color.rgb = C_NAVY

    # Borde inferior decorativo en XML
    pPr = p._p.get_or_add_pPr()
    pBdr = parse_xml(
        f'<w:pBdr {nsdecls("w")}>'
        f'<w:bottom w:val="single" w:sz="14" w:space="4" w:color="{HEX_BLUE}"/>'
        f'</w:pBdr>'
    )
    pPr.append(pBdr)


def add_heading_2_styled(doc, text):
    """Encabezado 2 con acento de color."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True

    run = p.add_run(text)
    run.bold = True
    run.font.name = "Calibri"
    run.font.size = Pt(12.5)
    run.font.color.rgb = C_BLUE


def add_heading_3_styled(doc, text):
    """Encabezado 3."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True

    run = p.add_run(text)
    run.bold = True
    run.font.name = "Calibri"
    run.font.size = Pt(10.5)
    run.font.color.rgb = C_DARK_SLATE


def add_bullet_styled(doc, bold_prefix, text):
    """Párrafo de viñeta estilizado."""
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.15

    r_bold = p.add_run(bold_prefix)
    r_bold.bold = True
    r_bold.font.name = "Calibri"
    r_bold.font.size = Pt(9.5)
    r_bold.font.color.rgb = C_DARK_SLATE

    r_text = p.add_run(text)
    r_text.font.name = "Calibri"
    r_text.font.size = Pt(9.5)
    r_text.font.color.rgb = C_DARK_SLATE


def add_body_p(doc, text, bold=False, italic=False):
    """Párrafo de cuerpo estándar."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.15

    r = p.add_run(text)
    r.bold = bold
    r.italic = italic
    r.font.name = "Calibri"
    r.font.size = Pt(9.5)
    r.font.color.rgb = C_DARK_SLATE
    return p


def build_manual_docx():
    print("Iniciando construcción del Manual de Usuario IntelliPrint (.docx)...")
    doc = Document()

    # 1. Configurar márgenes de página A4 (2.0 cm laterales, 2.2 cm sup/inf)
    for section in doc.sections:
        section.page_width = Inches(8.27)    # 210 mm
        section.page_height = Inches(11.69)  # 297 mm
        section.top_margin = Inches(0.85)
        section.bottom_margin = Inches(0.85)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)

        # Configurar pie de página estándar
        footer = section.footer
        p_foot = footer.paragraphs[0]
        p_foot.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_foot.paragraph_format.space_after = Pt(0)
        r_foot = p_foot.add_run(
            "IntelliPrint v1.2.0 · Manual de Usuario · Salesianos Urnieta / CIFP Mendizabala LHII · Hezkuntza Saila"
        )
        r_foot.font.name = "Calibri"
        r_foot.font.size = Pt(8.0)
        r_foot.font.color.rgb = C_MUTED

    # =========================================================================
    # PORTADA EDITORIAL DE ALTA CALIDAD
    # =========================================================================

    # 1. Tabla de logotipos institucionales en la cabecera de la portada
    tbl_logos = doc.add_table(rows=1, cols=3)
    tbl_logos.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_logos.autofit = False

    w_col = Inches(2.15)
    for i in range(3):
        tbl_logos.columns[i].width = w_col

    # Logos
    p_sales = ASSETS_DIR / "logo-salesianos.png"
    p_mendi = ASSETS_DIR / "logo-mendizabala.png"
    p_edu = ASSETS_DIR / "logo-dept-educacion-1.png"

    cell_0 = tbl_logos.cell(0, 0)
    cell_0.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p0 = cell_0.paragraphs[0]
    p0.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if p_sales.exists():
        p0.add_run().add_picture(get_docx_image_stream(p_sales), width=Inches(1.8))

    cell_1 = tbl_logos.cell(0, 1)
    cell_1.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p1 = cell_1.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if p_mendi.exists():
        p1.add_run().add_picture(get_docx_image_stream(p_mendi), width=Inches(1.6))

    cell_2 = tbl_logos.cell(0, 2)
    cell_2.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p2 = cell_2.paragraphs[0]
    p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    if p_edu.exists():
        p2.add_run().add_picture(get_docx_image_stream(p_edu), width=Inches(1.8))

    p_spacer_1 = doc.add_paragraph()
    p_spacer_1.paragraph_format.space_before = Pt(36)
    p_spacer_1.paragraph_format.space_after = Pt(0)

    # 2. Logotipo Central de IntelliPrint
    p_logo = doc.add_paragraph()
    p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_logo.paragraph_format.space_before = Pt(0)
    p_logo.paragraph_format.space_after = Pt(16)

    p_full_logo = ASSETS_DIR / "Logo-intelliprint.jpg"
    p_imago = ASSETS_DIR / "Logo-intelliprint-imago.jpg"
    if p_full_logo.exists():
        p_logo.add_run().add_picture(get_docx_image_stream(p_full_logo), width=Inches(3.4))
    elif p_imago.exists():
        p_logo.add_run().add_picture(get_docx_image_stream(p_imago), width=Inches(1.8))

    # 3. Título Principal
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(6)
    p_title.paragraph_format.space_after = Pt(4)
    r_t = p_title.add_run("INTELLIPRINT")
    r_t.bold = True
    r_t.font.name = "Calibri"
    r_t.font.size = Pt(34.0)
    r_t.font.color.rgb = C_NAVY

    # 4. Subtítulo y Versión
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(12)
    r_sub = p_sub.add_run("MANUAL OFICIAL DE USUARIO Y GUÍA DE OPERACIÓN TÉCNICA")
    r_sub.bold = True
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(13.0)
    r_sub.font.color.rgb = C_BLUE

    # 5. Badge de Versión
    p_badge = doc.add_paragraph()
    p_badge.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_badge.paragraph_format.space_before = Pt(0)
    p_badge.paragraph_format.space_after = Pt(28)
    r_b = p_badge.add_run("Versión 1.2.0 · Edición de Taller y Formación Profesional")
    r_b.font.name = "Calibri"
    r_b.font.size = Pt(10.0)
    r_b.italic = True
    r_b.font.color.rgb = C_MUTED

    # 6. Cuadro de Resumen en la Portada
    tbl_summary = doc.add_table(rows=1, cols=1)
    tbl_summary.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_summary.autofit = False
    c_sum = tbl_summary.cell(0, 0)
    c_sum.width = Inches(6.4)
    set_cell_background(c_sum, HEX_LIGHT_GRAY)
    set_cell_margins(c_sum, top=180, bottom=180, left=220, right=220)
    set_cell_border_left_accent(c_sum, border_hex=HEX_NAVY, border_size="36")

    p_s = c_sum.paragraphs[0]
    p_s.paragraph_format.space_after = Pt(0)
    p_s.paragraph_format.line_spacing = 1.2
    r_s_title = p_s.add_run("SISTEMA DE PREFLIGHT, NORMALIZACIÓN E IMPOSICIÓN INTELIGENTE\n")
    r_s_title.bold = True
    r_s_title.font.name = "Calibri"
    r_s_title.font.size = Pt(10.5)
    r_s_title.font.color.rgb = C_NAVY

    r_s_desc = p_s.add_run(
        "Guía completa para operarios de preimpresión, maquinistas de offset/digital y alumnado de Artes Gráficas. "
        "Cubre la auditoría geométrica y colorimétrica (ISO 12647-2 / PDF/X), la corrección automática en 1 clic, "
        "el motor de imposición de pliegos N-Up, el inspector de códigos de barras, la trazabilidad mediante código QR "
        "a pie de máquina y el simulador interactivo de consecuencias físicas en taller."
    )
    r_s_desc.font.name = "Calibri"
    r_s_desc.font.size = Pt(9.5)
    r_s_desc.font.color.rgb = C_DARK_SLATE

    # 7. Créditos Institucionales al pie de la portada
    p_spacer_2 = doc.add_paragraph()
    p_spacer_2.paragraph_format.space_before = Pt(45)
    p_spacer_2.paragraph_format.space_after = Pt(0)

    tbl_foot = doc.add_table(rows=2, cols=2)
    tbl_foot.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_foot.autofit = False
    tbl_foot.columns[0].width = Inches(3.2)
    tbl_foot.columns[1].width = Inches(3.2)

    c00 = tbl_foot.cell(0, 0)
    p00 = c00.paragraphs[0]
    p00.paragraph_format.space_after = Pt(2)
    r00 = p00.add_run("Centros Desarrolladores:")
    r00.bold = True
    r00.font.name = "Calibri"
    r00.font.size = Pt(9.0)
    r00.font.color.rgb = C_NAVY

    r00_txt = p00.add_run("\n• CPIFP Salesianos Urnieta LHIPI (Gipuzkoa)\n• CIFP Mendizabala LHII (Álava)")
    r00_txt.font.name = "Calibri"
    r00_txt.font.size = Pt(8.5)
    r00_txt.font.color.rgb = C_DARK_SLATE

    c01 = tbl_foot.cell(0, 1)
    p01 = c01.paragraphs[0]
    p01.paragraph_format.space_after = Pt(2)
    r01 = p01.add_run("Marco Institucional:")
    r01.bold = True
    r01.font.name = "Calibri"
    r01.font.size = Pt(9.0)
    r01.font.color.rgb = C_NAVY

    r01_txt = p01.add_run("\n• Proyectos de Innovación Aplicada en FP\n• Departamento de Educación · Gobierno Vasco\n• Convocatoria 2026-2027")
    r01_txt.font.name = "Calibri"
    r01_txt.font.size = Pt(8.5)
    r01_txt.font.color.rgb = C_DARK_SLATE

    # Salto de página para el cuerpo del manual
    doc.add_page_break()

    # =========================================================================
    # ÍNDICE GENERAL ESTRUCTURADO
    # =========================================================================

    add_heading_1_styled(doc, "ÍNDICE GENERAL")

    toc_items = [
        ("1. ¿QUÉ ES INTELLIPRINT?", "Filosofía, objetivos de taller y arquitectura del sistema"),
        ("2. PRIMEROS PASOS Y ACCESO", "Requisitos de archivo, conexión al servidor y estructura de la pantalla"),
        ("3. CONFIGURACIÓN DEL PREFLIGHT", "Subida de documentos, inspección rápida, perfiles de comprobación y gestión ICC"),
        ("4. EL INFORME DE VERIFICACIÓN", "Semáforo global, hallazgos técnicos, corrector ortográfico, TAC y separaciones CMYK"),
        ("5. SUITE DE CORRECCIÓN EN 1 CLIC", "Taller en 1 Clic, conversión RGB a CMYK, sobreimpresión, hairlines y sangre reflejada"),
        ("6. MÓDULOS AVANZADOS DE PRODUCCIÓN", "Imposición N-Up, códigos de barras 100% K, Hot-Folder, margen de seguridad y lomo"),
        ("7. TRAZABILIDAD Y QR DEL MAQUINISTA", "Inyección de QR en el pliego y consola web móvil (/verify/{job_id}) a pie de máquina"),
        ("8. MODO DIDÁCTICO Y SIMULADOR FP", "Retos prácticos, simulador físico interactivo, quiz técnico y ficha oficial en PDF"),
        ("9. DOCUMENTACIÓN Y CERTIFICADOS", "Certificado técnico oficial, guía pedagógica para clientes y exportación JSON"),
        ("10. PREGUNTAS FRECUENTES (FAQ)", "Resolución de incidencias comunes de preimpresión y producción gráfica"),
    ]

    tbl_toc = doc.add_table(rows=len(toc_items), cols=2)
    tbl_toc.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_toc.autofit = False
    tbl_toc.columns[0].width = Inches(3.2)
    tbl_toc.columns[1].width = Inches(3.3)
    set_table_borders(tbl_toc, border_hex="E2E8F0")

    for i, (sec_title, sec_desc) in enumerate(toc_items):
        cell_t = tbl_toc.cell(i, 0)
        cell_d = tbl_toc.cell(i, 1)

        set_cell_margins(cell_t, top=80, bottom=80, left=80, right=80)
        set_cell_margins(cell_d, top=80, bottom=80, left=80, right=80)

        pt = cell_t.paragraphs[0]
        pt.paragraph_format.space_after = Pt(0)
        rt = pt.add_run(sec_title)
        rt.bold = True
        rt.font.name = "Calibri"
        rt.font.size = Pt(9.5)
        rt.font.color.rgb = C_BLUE

        pd = cell_d.paragraphs[0]
        pd.paragraph_format.space_after = Pt(0)
        rd = pd.add_run(sec_desc)
        rd.font.name = "Calibri"
        rd.font.size = Pt(9.0)
        rd.font.color.rgb = C_MUTED

    doc.add_page_break()

    # =========================================================================
    # SECCIÓN 1: ¿QUÉ ES INTELLIPRINT?
    # =========================================================================

    add_heading_1_styled(doc, "1. ¿QUÉ ES INTELLIPRINT?")

    add_body_p(
        doc,
        "IntelliPrint es una solución informática avanzada de ingeniería de software gráfico diseñada para la auditoría, "
        "normalización, corrección e imposición de documentos PDF antes de su entrada a las prensas de impresión offset y digital. "
        "El proyecto ha sido concebido y desarrollado de forma conjunta por el profesorado y alumnado técnico del CPIFP Salesianos Urnieta LHIPI "
        "y del CIFP Mendizabala LHII, en estrecha colaboración con empresas del sector gráfico de Euskadi y el apoyo institucional del "
        "Departamento de Educación del Gobierno Vasco."
    )

    add_heading_2_styled(doc, "1.1. Misión de Taller: Objetivo Cero Errores y Cero Desperdicio")
    add_body_p(
        doc,
        "En una imprenta comercial moderna, más del 70% de las paradas no planificadas de máquina y repeticiones de tirada se deben a "
        "defectos inadvertidos en los archivos entregados por agencias de publicidad, diseñadores o clientes finales: fondos sin sangre, "
        "textos en tipografía menuda compuestos en 4 tintas (Rich Black), exceso de cobertura de tinta (TAC > 300%) que provoca repintado "
        "en la pila de salida, filetes invisibles para el láser del CTP o códigos de barras borrosos que fallan en el punto de venta."
    )
    add_body_p(
        doc,
        "IntelliPrint actúa como un cortafuegos inteligente de taller: somete el PDF a una batería de comprobaciones según normativas "
        "internacionales (ISO 12647-2, ISO 15930 / PDF/X, Ghent Workgroup) y proporciona herramientas de corrección matemática directa "
        "que permiten subsanar los problemas en un solo clic, sin recurrir a costosas idas y vueltas con el cliente."
    )

    add_callout(
        doc,
        title="Impacto Medioambiental y Económico",
        text="Corregir un error de sangre o de TAC en preimpresión cuesta menos de 1 minuto. Corregirlo cuando el trabajo ya está en máquina "
             "supone tirar a la basura cientos de pliegos de papel estucado, desperdiciar planchas de aluminio CTP, lavar la batería de tintas y "
             "asumir horas de parada de taller. IntelliPrint minimiza la maculatura y optimiza la huella ecológica de la imprenta.",
        style="emerald"
    )

    # =========================================================================
    # SECCIÓN 2: PRIMEROS PASOS Y ACCESO
    # =========================================================================

    add_heading_1_styled(doc, "2. PRIMEROS PASOS Y ACCESO A LA APLICACIÓN")

    add_body_p(
        doc,
        "IntelliPrint se ejecuta a través de cualquier navegador web moderno (Google Chrome, Mozilla Firefox, Microsoft Edge o Safari) "
        "sin necesidad de instalar plugins ni programas adicionales en las estaciones de trabajo de los operarios o en los puestos del aula."
    )

    add_heading_2_styled(doc, "2.1. Conexión y Estado del Servidor")
    add_bullet_styled(doc, "Dirección Local o de Red: ", "Acceda a http://localhost:8000 en el puesto servidor o a la IP/dominio configurado en la red de su centro o imprenta.")
    add_bullet_styled(doc, "Indicador Motor Activo: ", "En el ángulo superior izquierdo, junto al título, compruebe que se visualiza el badge verde 'Motor Activo'. Esto certifica que el backend de FastAPI, las librerías PyMuPDF/PikePDF y los perfiles ICC están listos.")
    add_bullet_styled(doc, "Cabecera Institucional: ", "En el margen derecho se muestran los sellos oficiales de Salesianos Urnieta, CIFP Mendizabala LHII y Eusko Jaurlaritza.")
    add_bullet_styled(doc, "Acceso a Modo Didáctico: ", "El botón morado con icono de birrete [Modo Didáctico FP] permite ingresar al banco de retos y simulador para estudiantes.")

    add_heading_2_styled(doc, "2.2. Requisitos de los Archivos PDF")
    add_body_p(
        doc,
        "La plataforma admite cualquier documento PDF con especificaciones desde la versión 1.3 hasta 2.0, incluyendo estándares PDF/X-1a, "
        "PDF/X-3 y PDF/X-4. Admite trabajos de una sola hoja (tarjetas de visita, cartelería, packaging) y publicaciones multipágina de gran volumen (revistas, libros, catálogos)."
    )

    # =========================================================================
    # SECCIÓN 3: CONFIGURACIÓN DEL PREFLIGHT
    # =========================================================================

    add_heading_1_styled(doc, "3. CONFIGURACIÓN Y ANÁLISIS DE ENTRADA")

    add_body_p(
        doc,
        "El proceso de preflight comienza en la tarjeta principal 'Configuración del Preflight':"
    )

    add_heading_2_styled(doc, "3.1. Carga del Documento e Inspección Rápida")
    add_body_p(
        doc,
        "Puede arrastrar el archivo directamente a la zona punteada o hacer clic en 'Seleccionar PDF'. Inmediatamente, sin retrasos, "
        "el sistema realiza una inspección preliminar mostrando: tamaño en MB, número de páginas, dimensiones físicas de corte en milímetros, "
        "recuento de imágenes rasterizadas y el perfil de salida (OutputIntent) incrustado en el PDF original."
    )

    add_heading_2_styled(doc, "3.2. Selección de Perfiles de Verificación")
    add_body_p(
        doc,
        "El preflight adapta sus umbrales al tipo de producto que se desea imprimir mediante el selector de perfil:"
    )

    tbl_profiles = doc.add_table(rows=6, cols=3)
    tbl_profiles.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_profiles.autofit = False
    tbl_profiles.columns[0].width = Inches(1.8)
    tbl_profiles.columns[1].width = Inches(1.2)
    tbl_profiles.columns[2].width = Inches(3.4)
    set_table_borders(tbl_profiles, border_hex="CBD5E1")

    # Cabecera tabla
    headers = ["Perfil de Verificación", "Límite TAC", "Aplicación Recomendada en Taller"]
    for j, h in enumerate(headers):
        c = tbl_profiles.cell(0, j)
        set_cell_background(c, HEX_NAVY)
        set_cell_margins(c, top=100, bottom=100, left=100, right=100)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.name = "Calibri"
        r.font.size = Pt(9.0)
        r.font.color.rgb = RGBColor(255, 255, 255)

    profile_data = [
        ("Offset Comercial 300%", "300%", "Papel estucado (couché) brillante o mate según ISO 12647-2 (FOGRA39 / FOGRA51)."),
        ("Impresión Digital Estándar", "320%", "Prensas digitales láser y tóner seco. Admite mayor densidad de fusión."),
        ("Prensa y Papel Periódico", "240%", "Papel prensa estándar de alta porosidad y absorción rápida (evita repintado)."),
        ("Packaging y Cartoncillo", "300%", "Estuches, cajas y packaging con tintas directas y trazados de troquelado."),
        ("Gran Formato y Cartelería", "320%", "Lonas, vinilos y displays donde la resolución mínima admitida es de 150 DPI."),
    ]

    for i, row in enumerate(profile_data, 1):
        for j, val in enumerate(row):
            c = tbl_profiles.cell(i, j)
            if i % 2 == 1:
                set_cell_background(c, HEX_LIGHT_GRAY)
            set_cell_margins(c, top=80, bottom=80, left=100, right=100)
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(val)
            r.font.name = "Calibri"
            r.font.size = Pt(8.5)
            r.font.color.rgb = C_DARK_SLATE
            if j == 0:
                r.bold = True

    add_body_p(doc, "")

    add_heading_2_styled(doc, "3.3. Gestión del Espacio de Color y Perfiles ICC")
    add_bullet_styled(doc, "Preservar Perfil Existente: ", "Respeta el perfil embebido por el diseñador si ya cumple con los estándares.")
    add_bullet_styled(doc, "Asignar Perfil Estándar: ", "Inyecta la etiqueta OutputIntent oficial si el documento viene 'huérfano' sin perfil definido.")
    add_bullet_styled(doc, "Catálogo ICC Integrado: ", "Permite forzar la conversión hacia perfiles certificados de la ECI: ISO Coated v2 300% (FOGRA39), PSO Coated v3 (FOGRA51), PSO Uncoated v3 (FOGRA52), sRGB o Adobe RGB.")

    # =========================================================================
    # SECCIÓN 4: EL INFORME DE VERIFICACIÓN
    # =========================================================================

    add_heading_1_styled(doc, "4. EL INFORME DE VERIFICACIÓN (PREFLIGHT REPORT)")

    add_body_p(
        doc,
        "Al pulsar 'Iniciar Preflight Completo', el motor analiza miles de objetos vectoriales, tramas e imágenes, "
        "desplegando una consola interactiva estructurada en 6 pestañas especializadas:"
    )

    add_heading_2_styled(doc, "4.1. Semáforo Global de Producción")
    add_body_p(
        doc,
        "La cabecera de resultados resume de un vistazo la aptitud del archivo mediante tres tarjetas principales:"
    )
    add_bullet_styled(doc, "Resultado Técnico: ", "Dictamen oficial (APTO en verde, AJUSTES en ámbar, RECHAZADO en rojo).")
    add_bullet_styled(doc, "Espacio de Color & ICC: ", "Informa del perfil de salida y de la existencia de imágenes RGB o tintas directas.")
    add_bullet_styled(doc, "Geometría & Cajas: ", "Verifica la presencia de los 3 mm de sangre y la concordancia de TrimBox y BleedBox.")

    add_heading_2_styled(doc, "4.2. Pestaña 1: Hallazgos e Incidencias Técnicas (Findings)")
    add_body_p(
        doc,
        "Detalla cada una de las comprobaciones efectuadas, agrupadas por severidad cromática. Para cada fallo detectado "
        "(falta de sangre, líneas pelo, imágenes a baja resolución, fuentes no incrustadas), IntelliPrint ofrece un botón "
        "de corrección directa que ejecuta la reparación en memoria de forma instantánea."
    )

    add_heading_2_styled(doc, "4.3. Pestaña 2: Corrector Ortográfico Editorial")
    add_body_p(
        doc,
        "Revisa todos los textos del documento contrastándolos con una base léxica de más de 85.000 términos en español y un glosario "
        "específico de la industria gráfica. Permite aplicar correcciones ortográficas sobre el texto antes de quemar planchas o añadir "
        "palabras técnicas al glosario permanente del taller."
    )

    add_heading_2_styled(doc, "4.4. Pestaña 3: Métricas de Producción y Heatmap de TAC")
    add_body_p(
        doc,
        "Calcula la Cobertura Total de Tinta (Total Area Coverage) píxel a píxel. Si detecta zonas donde la suma de pigmentos C+M+Y+K "
        "supera el límite de seguridad (300%), genera un mapa de calor superpuesto señalando con precisión milimétrica qué imágenes "
        "o masas oscuras corren riesgo de repintado en la bandeja de salida."
    )

    add_heading_2_styled(doc, "4.5. Pestaña 4: Visor Densitométrico de Separaciones CMYK")
    add_body_p(
        doc,
        "Simula la mesa de luz de fotomecánica permitiendo al operario aislar y conmutar individualmente los 4 canales de color: "
        "Cian (C), Magenta (M), Amarillo (Y) y Negro (K). Esencial para comprobar que textos negros de 6 pt están en el canal K al 100% "
        "y no contienen residuos de color en los otros tres cuerpos."
    )

    add_heading_2_styled(doc, "4.6. Pestaña 5: Comparador Visual Antes / Después (Slider)")
    add_body_p(
        doc,
        "Tras aplicar cualquier corrección, esta herramienta despliega una cortinilla interactiva deslizable que permite comparar "
        "la versión original frente a la versión corregida, asegurando que ninguna fotografía, degradado o texto ha sufrido desplazamientos."
    )

    add_heading_2_styled(doc, "4.7. Pestaña 6: Hoja de Aprobación de Tirada (Release)")
    add_body_p(
        doc,
        "Permite formalizar la autorización de entrada a máquina: el operario selecciona la máquina de destino, anota su nombre y puede "
        "estampar su firma digital sobre un lienzo táctil, generando un registro de responsabilidad y conformidad de tirada."
    )

    # =========================================================================
    # SECCIÓN 5: SUITE DE HERRAMIENTAS Y CORRECCIONES EN 1 CLIC
    # =========================================================================

    add_heading_1_styled(doc, "5. SUITE DE HERRAMIENTAS Y CORRECCIONES EN 1 CLIC")

    add_body_p(
        doc,
        "La barra de herramientas superior contiene los motores de normalización automatizada:"
    )

    add_bullet_styled(doc, "Taller en 1 Clic (Batch Auto-Fix): ", "Ejecuta de manera secuencial y no destructiva todas las reparaciones recomendadas: normaliza cajas de página, genera sangre reflejada de 3 mm si faltaba, convierte imágenes RGB a CMYK, fuerza la sobreimpresión en textos negros y engrosa líneas pelo a 0.30 pt.")
    add_bullet_styled(doc, "Conversión de Color RGB a CMYK: ", "Convierte todos los mapas de bits en sRGB o Adobe RGB al perfil CMYK objetivo mediante transformaciones directas en espacio Lab, preservando el contraste tonal.")
    add_bullet_styled(doc, "Conversión de Tintas Planas (Pantone a CMYK): ", "Descompone los colores directos Spot/Pantone no presupuestados en sus valores óptimos de cuatricromía CMYK para tiradas de 4 colores.")
    add_bullet_styled(doc, "Corrección de Sobreimpresión (Overprint): ", "Aplica sobreimpresión obligatoria al texto negro 100% K para evitar descalces, y retira la sobreimpresión en textos u objetos blancos para evitar que desaparezcan en la plancha.")
    add_bullet_styled(doc, "Corrección de Líneas Finas (Hairlines): ", "Detecta trazos de menos de 0.25 pt (habituales en AutoCAD e Illustrator) y los eleva a 0.30 pt para asegurar su insolado en el CTP a 2400 DPI.")
    add_bullet_styled(doc, "Vectorización de Fuentes (Outlining): ", "Convierte todos los textos en curvas vectoriales puras, eliminando de raíz cualquier problema de fuentes no incrustadas, bloqueadas por DRM o ausentes en el RIP.")
    add_bullet_styled(doc, "Generador de Sangre Reflejada (Mirror Bleed): ", "Si el diseño carece de sangría exterior, crea una extensión perimetral de 3 mm mediante espejo de los píxeles de los bordes, protegiendo el corte de guillotina contra filetes blancos.")
    add_bullet_styled(doc, "Inyector de Marcas de Imprenta: ", "Amplía el pliego técnico e introduce cruces de registro, marcas de corte exteriores, escalas de control de entintado CMYK y la identificación institucional de la tirada.")
    add_bullet_styled(doc, "Limitador de Cobertura de Tinta (TAC 300%): ", "Aplica un recorte suave en las densidades máximas de sombra para que ninguna zona supere el 300%, impidiendo el repintado en la salida de máquina.")

    # =========================================================================
    # SECCIÓN 6: MÓDULOS AVANZADOS DE PRODUCCIÓN
    # =========================================================================

    doc.add_page_break()
    add_heading_1_styled(doc, "6. MÓDULOS AVANZADOS DE PRODUCCIÓN")

    add_heading_2_styled(doc, "6.1. Motor de Imposición de Pliegos de Máquina (N-Up)")
    add_body_p(
        doc,
        "Permite montar el pliego de máquina directamente en el navegador sin depender de programas externos de imposición:"
    )
    add_bullet_styled(doc, "Formatos de Hoja Soportados: ", "SRA3 (320 × 450 mm), A3 (297 × 420 mm), A4, 50 × 70 cm (B2) y 70 × 100 cm (B1).")
    add_bullet_styled(doc, "Esquemas de Montaje: ", "Paso y Repetición (N-Up Step and Repeat) para tarjetas y folletos sueltos, o Cuadernillo Grapado para revistas y publicaciones plegadas.")
    add_bullet_styled(doc, "Tratamiento Inteligente de Sangre: ", "Gestiona automáticamente los 3 escenarios posibles: añade marcas respetando los 3 mm de sangre existentes, genera sangría reflejada si el archivo carece de ella o recorta marcas de corte previas del cliente para evitar marcas duplicadas.")
    add_bullet_styled(doc, "Cálculo en Tiempo Real: ", "Indica el número exacto de poses por hoja, el porcentaje de aprovechamiento del papel y permite descargar el PDF impuesto listo para CTP o prensa digital.")

    add_heading_2_styled(doc, "6.2. Inspector y Corrector de Códigos de Barras y QR")
    add_body_p(
        doc,
        "Analiza mediante visión por computador (OpenCV) la presencia de códigos comerciales (EAN-13, EAN-8, QR Code, Code 128):"
    )
    add_bullet_styled(doc, "Validación GS1: ", "Comprueba el dígito de control aritmético (módulo 10) para evitar códigos defectuosos de origen.")
    add_bullet_styled(doc, "Detección de Cuatricromía: ", "Toma muestras microscópicas de píxeles en los canales C, M, Y, K para comprobar si el código se imprimirá en Negro Puro o en Negro Enriquecido (4 tintas).")
    add_bullet_styled(doc, "Corrección en 1 Clic a 100% K: ", "Re-genera el código en vector puro a 300 DPI en tinta negra 100% sobreimpresa y añade una reserva blanca opaca (Quiet Zone) en los laterales para garantizar lectura perfecta en cajas registradoras.")

    add_heading_2_styled(doc, "6.3. Procesamiento por Lotes y Hot-Folder Automatizado")
    add_body_p(
        doc,
        "Para entornos de alta productividad, IntelliPrint incluye:"
    )
    add_bullet_styled(doc, "Cola de Lotes en Navegador: ", "Permite arrastrar decenas de archivos a la vez, procesándolos en paralelo con opción de 'Corregir Todo el Lote' y descarga en archivo ZIP comprimido.")
    add_bullet_styled(doc, "Carpeta Caliente (Hot-Folder Daemon): ", "Servicio en segundo plano que vigila la carpeta de red hotfolder/in/. Al depositar un PDF, comprueba la estabilidad de copia, realiza el preflight y lo traslada automáticamente a out_aprobados/ (con su certificado) o a out_rechazados/ (con el informe didáctico para el cliente).")

    add_heading_2_styled(doc, "6.4. Inspector de Margen de Seguridad y Lomo")
    add_body_p(
        doc,
        "Analiza geométricamente la distancia de los textos y logotipos respecto a las líneas de corte y plegado:"
    )
    add_bullet_styled(doc, "Detección Automática: ", "Distingue hojas sueltas (tarjetas de visita 85×55 mm, flyers: margen 3 mm, lomo 0 mm) frente a publicaciones encuadernadas (≥ 4 páginas: margen 3 mm, reserva de lomo/medianil de 8 mm alternante).")
    add_bullet_styled(doc, "Visor de Advertencia: ", "Muestra un render visual con líneas roja de corte (TrimBox), verde de seguridad, morada de lomo y cajas de alerta rojas en textos en riesgo de ser guillotinados.")

    # =========================================================================
    # SECCIÓN 7: TRAZABILIDAD Y QR DEL MAQUINISTA
    # =========================================================================

    add_heading_1_styled(doc, "7. TRAZABILIDAD DE TALLER Y CÓDIGO QR PARA EL MAQUINISTA")

    add_body_p(
        doc,
        "Uno de los avances clave de IntelliPrint es la unión directa entre el departamento de preimpresión y el maquinista "
        "a pie de máquina, eliminando las dudas y papeles perdidos en el taller."
    )

    add_callout(
        doc,
        title="Código QR en el Margen Técnico (Slug Area)",
        text="Al generar la imposición del pliego o añadir marcas de imprenta, el motor inyecta en el margen inferior de la hoja "
             "un código QR de 9 × 9 mm en 100% K nítido junto a la leyenda institucional: IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII. "
             "Cualquier cámara de smartphone o tablet enfoca el QR y abre en 1 segundo la consola web del trabajo.",
        style="purple"
    )

    add_heading_2_styled(doc, "7.1. Ficha Móvil de Verificación (/verify/{job_id})")
    add_body_p(
        doc,
        "La interfaz móvil para el maquinista ha sido diseñada específicamente para condiciones de taller (alta legibilidad y rapidez):"
    )
    add_bullet_styled(doc, "Semáforo de Autorización: ", "Verde esmeralda 'LISTO PARA IMPRESIÓN (TIRADA AUTORIZADA)' o ámbar 'REQUIERE AJUSTES PREVIOS'.")
    add_bullet_styled(doc, "Cuerpos de Tinta a Preparar: ", "Indica exactamente qué tintas debe cargar en el tintero (CMYK convencional + nombres de tintas directas/Pantone detectadas).")
    add_bullet_styled(doc, "Perfil ICC y TAC Máximo: ", "Muestra el perfil de color que debe cargar en la consola de entintado y el valor de cobertura para regular el secador IR y los polvos antimaculadores.")
    add_bullet_styled(doc, "Verificaciones Clave: ", "Chequeo de sangrado (3 mm), líneas pelo, códigos de barras y dimensiones del pliego.")
    add_bullet_styled(doc, "Descargas a Pie de Máquina: ", "Enlaces directos para descargar o consultar el Certificado Técnico PDF, la Guía del Cliente o el archivo del Pliego Impuesto.")

    # =========================================================================
    # SECCIÓN 8: MODO DIDÁCTICO Y SIMULADOR FP
    # =========================================================================

    doc.add_page_break()
    add_heading_1_styled(doc, "8. MODO DIDÁCTICO Y SIMULADOR DE TALLER FP")

    add_body_p(
        doc,
        "Diseñado en el marco de la innovación aplicada en Formación Profesional de Artes Gráficas, este módulo "
        "transforma la aplicación en un aula virtual de aprendizaje experimental para el alumnado."
    )

    add_heading_2_styled(doc, "8.1. Banco de Retos Prácticos de Taller")
    add_body_p(
        doc,
        "El profesor o estudiante puede cargar con un solo clic casos de estudio preparados por el equipo docente:"
    )
    add_bullet_styled(doc, "Reto 1 (Iniciación FP): ", "Tarjeta corporativa con textos de 6 pt en 4 tintas (Rich Black 300%) y sin sangrado exterior (0 mm).")
    add_bullet_styled(doc, "Reto 2 (Intermedio): ", "Folleto publicitario nocturno con TAC del 365% (riesgo severo de repintado) y filetes de 0.06 pt no insolables en CTP.")
    add_bullet_styled(doc, "Reto 3 (Avanzado): ", "Estuche cosmético de packaging con código EAN-13 en cuatricromía y textos legales a 1.2 mm del troquel.")
    add_bullet_styled(doc, "Reto 4 (Avanzado): ", "Revista técnica de 16 páginas con textos invadiendo el medianil/lomo y fotos en sRGB.")

    add_heading_2_styled(doc, "8.2. Simulador Visual de Consecuencias Físicas en Máquina")
    add_body_p(
        doc,
        "Mediante controles deslizantes (sliders) interactivos, el alumno observa en tiempo real los fallos que ocurrirían en el taller:"
    )
    add_bullet_styled(doc, "Descalce de Registro Offset: ", "Slider de 0.05 a 0.50 mm mostrando la aparición de halos cian, magenta y amarillo sobre tipografías menudas si se componen en 4 tintas.")
    add_bullet_styled(doc, "Repintado / Maculado en Pila: ", "Slider de TAC (260% a 380%) que renderiza la mancha oleosa transferida por presión al dorso de la hoja superior en la pila de salida.")
    add_bullet_styled(doc, "Desvío de Guillotina: ", "Conmutador de sangre (+3 mm vs 0 mm) y oscilación de corte que ilustra el antiestético filete blanco sobre papel virgen.")
    add_bullet_styled(doc, "Pérdida en Plancha CTP: ", "Slider de grosor de trazo que demuestra cómo el rayo láser térmico a 2400 DPI pierde la emulsión en líneas de grosor < 0.25 pt.")

    add_heading_2_styled(doc, "8.3. Cuestionario de Autoevaluación Técnica (Quiz)")
    add_body_p(
        doc,
        "Prueba tipo test de 5 preguntas técnicas basadas en las normas ISO 12647-2, ISO 15930 y GS1. "
        "Calcula la nota de 0 a 10 e informa del nivel competencial (Sobresaliente, Notable, Aprobado, Insuficiente) "
        "acompañado de la fundamentación técnica de cada respuesta."
    )

    add_heading_2_styled(doc, "8.4. Ficha Oficial de Evaluación y Prácticas en PDF")
    add_body_p(
        doc,
        "Genera un documento PDF formal en tamaño A4 con membrete de Salesianos Urnieta, CIFP Mendizabala LHII y Gobierno Vasco "
        "con los datos del alumno, resumen del reto analizado, diagnóstico técnico, calificación obtenida y casillas para las firmas "
        "del profesor evaluador y del estudiante."
    )

    # =========================================================================
    # SECCIÓN 9: DOCUMENTACIÓN Y ENTREGABLES
    # =========================================================================

    add_heading_1_styled(doc, "9. DOCUMENTACIÓN DE SALIDA Y ENTREGABLES")

    add_body_p(
        doc,
        "IntelliPrint genera tres modalidades de salida documental diseñadas para distintos destinatarios:"
    )

    tbl_outputs = doc.add_table(rows=4, cols=3)
    tbl_outputs.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_outputs.autofit = False
    tbl_outputs.columns[0].width = Inches(1.8)
    tbl_outputs.columns[1].width = Inches(1.3)
    tbl_outputs.columns[2].width = Inches(3.3)
    set_table_borders(tbl_outputs, border_hex="CBD5E1")

    headers_out = ["Documento Entregable", "Destinatario", "Contenido y Objetivo"]
    for j, h in enumerate(headers_out):
        c = tbl_outputs.cell(0, j)
        set_cell_background(c, HEX_NAVY)
        set_cell_margins(c, top=100, bottom=100, left=100, right=100)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.name = "Calibri"
        r.font.size = Pt(9.0)
        r.font.color.rgb = RGBColor(255, 255, 255)

    out_data = [
        ("Certificado Técnico de Preflight (PDF A4)", "Jefe de Taller / Archivo Técnico", "Informe riguroso de una página con sellos oficiales, huella SHA-256 de integridad, métricas densitométricas y veredicto formal de tirada."),
        ("Guía Pedagógica para el Cliente (PDF A4)", "Diseñador / Agencia / Cliente", "Informe cordial sin tecnicismos hostiles que explica qué incidencias se encontraron y cómo solucionarlas paso a paso en InDesign, Illustrator o Photoshop."),
        ("Informe de Datos Estructurado (JSON)", "Sistemas ERP / MIS de Imprenta", "Exportación completa en árbol JSON con todas las métricas, árboles de objetos y perfiles para integración automática en flujos de producción."),
    ]

    for i, row in enumerate(out_data, 1):
        for j, val in enumerate(row):
            c = tbl_outputs.cell(i, j)
            if i % 2 == 1:
                set_cell_background(c, HEX_LIGHT_GRAY)
            set_cell_margins(c, top=80, bottom=80, left=100, right=100)
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(val)
            r.font.name = "Calibri"
            r.font.size = Pt(8.5)
            r.font.color.rgb = C_DARK_SLATE
            if j == 0:
                r.bold = True

    add_body_p(doc, "")

    # =========================================================================
    # SECCIÓN 10: PREGUNTAS FRECUENTES (FAQ)
    # =========================================================================

    add_heading_1_styled(doc, "10. PREGUNTAS FRECUENTES Y SOLUCIÓN DE PROBLEMAS (FAQ)")

    faqs = [
        ("1. ¿Por qué el preflight marca error en un texto negro si en pantalla se ve negro perfecto?",
         "En pantalla, un texto negro compuesto por 4 tintas (Rich Black: C70 M60 Y50 K90) se ve intenso. Pero en la máquina de imprenta requiere 4 planchas diferentes. En tipografías finas de 6 u 8 pt, cualquier vibración o dilatación de papel descalzará las planchas, creando halos de color y texto borroso. Pulse 'Taller en 1 Clic' o 'Sobreimpresión' para pasarlo a 100% K puro con sobreimpresión."),

        ("2. ¿La sangre reflejada artificial modifica el contenido del diseño?",
         "No. La herramienta de sangre reflejada solo toma una franja de 3 mm de los bordes externos y los refleja simétricamente hacia afuera (más allá de la línea de corte TrimBox). La superficie visible final del trabajo permanece 100% inalterada."),

        ("3. ¿Cuál es la diferencia entre el Certificado de Preflight y la Ficha del Maquinista?",
         "El Certificado es un informe administrativo y de control de calidad formal en PDF A4. La Ficha del Maquinista (/verify/{job_id}) es una consola web móvil ultra-rápida pensada para abrirse en 1 segundo escaneando el código QR impreso en el pliego a pie de máquina, mostrando solo las variables críticas para el tiraje."),

        ("4. ¿Cómo se activa el Hot-Folder automatizado en la red de la imprenta?",
         "En la ventana 'Lote & Hot-Folder', haga clic en 'Iniciar Hot-Folder'. A partir de ese instante, cualquier archivo PDF depositado en la carpeta compartida hotfolder/in/ será procesado en segundo plano de manera continua."),

        ("5. ¿Cumple IntelliPrint con las normas internacionales del sector?",
         "Sí. Todas las tolerancias y reglas de comprobación y corrección están parametrizadas con base en las normas ISO 12647-2 (Offset en pliegos), ISO 15930 (Estándares PDF/X-1a y PDF/X-4), ISO/IEC 15420 (GS1 para códigos de barras) y las recomendaciones del Ghent Workgroup (GWG).")
    ]

    for q, a in faqs:
        add_heading_2_styled(doc, q)
        add_body_p(doc, a)

    # Pie institucional de cierre
    doc.add_page_break()
    p_close = doc.add_paragraph()
    p_close.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_close.paragraph_format.space_before = Pt(120)

    r_c1 = p_close.add_run("INTELLIPRINT PREFLIGHT & TALLER DIGITAL\n")
    r_c1.bold = True
    r_c1.font.name = "Calibri"
    r_c1.font.size = Pt(14.0)
    r_c1.font.color.rgb = C_NAVY

    r_c2 = p_close.add_run("Proyecto de Innovación Aplicada y Transferencia del Conocimiento en FP\n")
    r_c2.font.name = "Calibri"
    r_c2.font.size = Pt(11.0)
    r_c2.font.color.rgb = C_BLUE

    r_c3 = p_close.add_run(
        "CPIFP Salesianos Urnieta LHIPI (Gipuzkoa) · CIFP Mendizabala LHII (Álava)\n"
        "Departamento de Educación · Hezkuntza Saila · Eusko Jaurlaritza / Gobierno Vasco\n"
        "2026 - 2027"
    )
    r_c3.font.name = "Calibri"
    r_c3.font.size = Pt(9.5)
    r_c3.font.color.rgb = C_MUTED

    doc.save(str(OUTPUT_PATH))
    print(f"Manual generado con éxito: {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")
    return OUTPUT_PATH

if __name__ == "__main__":
    build_manual_docx()

