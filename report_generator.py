import os
from pathlib import Path
from datetime import datetime
import pymupdf

# ---------------------------------------------------------------------------
# Paleta y constantes
# ---------------------------------------------------------------------------
PAGE_W   = 595.3
PAGE_H   = 841.9
MARGIN_X = 35
CONTENT_W = PAGE_W - 2 * MARGIN_X   # 525.3 pt
FOOTER_Y  = 805
HEADER_H  = 75
FINDINGS_ROW_H = 40   # altura de cada fila de finding


def _palette():
    return {
        "navy":   (31/255, 38/255, 44/255),
        "blue":   (0.13, 0.40, 0.85),
        "slate":  (0.35, 0.40, 0.48),
        "light":  (0.95, 0.96, 0.98),
        "green":  (0.10, 0.60, 0.35),
        "red":    (0.85, 0.20, 0.20),
        "amber":  (0.85, 0.55, 0.10),
        "border": (0.80, 0.84, 0.88),
    }


def _draw_header(page, assets_dir, p):
    """Dibuja la cabecera azul marino con logos en la página dada."""
    page.draw_rect(pymupdf.Rect(0, 0, PAGE_W, HEADER_H), fill=p["navy"])

    imago_path     = assets_dir / "Logo-intelliprint-imago.jpg"
    full_logo_path = assets_dir / "Logo-intelliprint.jpg"

    if imago_path.exists():
        page.insert_image(pymupdf.Rect(28, 13, 76, 62), filename=str(imago_path), keep_proportion=True)
        text_x = 84
    elif full_logo_path.exists():
        page.insert_image(pymupdf.Rect(28, 16, 150, 58), filename=str(full_logo_path), keep_proportion=True)
        text_x = 158
    else:
        text_x = 35

    page.insert_text(pymupdf.Point(text_x, 35), "INTELLIPRINT · DICTAMEN OFICIAL",
                     fontsize=11.5, color=(1, 1, 1), fontname="helv")
    page.insert_text(pymupdf.Point(text_x, 52), "Certificado de Preflight y Control de Calidad",
                     fontsize=8, color=(0.75, 0.82, 0.90), fontname="helv")

    p_sales = assets_dir / "logo-salesianos.png"
    p_mendi = assets_dir / "logo-mendizabala.png"
    p_edu   = assets_dir / "logo-dept-educacion-1.png"

    if p_sales.exists() and p_mendi.exists() and p_edu.exists():
        capsule = pymupdf.Rect(310, 13, 567, 62)
        page.draw_rect(capsule, fill=(1, 1, 1), radius=0.08)
        page.insert_image(pymupdf.Rect(318, 17, 390, 58), filename=str(p_sales), keep_proportion=True)
        page.draw_line(pymupdf.Point(395, 20), pymupdf.Point(395, 55), color=(0.88, 0.88, 0.88), width=0.6)
        page.insert_image(pymupdf.Rect(400, 17, 474, 58), filename=str(p_mendi), keep_proportion=True)
        page.draw_line(pymupdf.Point(479, 20), pymupdf.Point(479, 55), color=(0.88, 0.88, 0.88), width=0.6)
        page.insert_image(pymupdf.Rect(484, 17, 560, 58), filename=str(p_edu), keep_proportion=True)


def _draw_footer(page, p, job_id, page_num, total_pages):
    """Dibuja el pie de página con número de página."""
    page.draw_line(pymupdf.Point(MARGIN_X, FOOTER_Y), pymupdf.Point(PAGE_W - MARGIN_X, FOOTER_Y),
                   color=p["border"], width=0.5)
    page.insert_text(pymupdf.Point(MARGIN_X, FOOTER_Y + 13),
                     "IntelliPrint Preflight Web v1.2.0 · Sistema Profesional de Calidad en Preimpresión",
                     fontsize=7.5, fontname="helv", color=p["slate"])
    page.insert_text(pymupdf.Point(390, FOOTER_Y + 13),
                     f"Certificado ID: {job_id}",
                     fontsize=7.5, fontname="helv", color=p["slate"])
    page.insert_text(pymupdf.Point(PAGE_W - MARGIN_X - 50, FOOTER_Y + 13),
                     f"Pág {page_num}/{total_pages}",
                     fontsize=7.5, fontname="helv", color=p["slate"])


# ---------------------------------------------------------------------------
# Generador principal
# ---------------------------------------------------------------------------

def generate_preflight_certificate_pdf(job_data, output_path):
    """
    Genera el PDF del Dictamen Oficial IntelliPrint.
    Los findings se distribuyen en tantas páginas A4 como sean necesarias.
    """
    doc = pymupdf.open()
    assets_dir = Path(__file__).parent / "assets"
    p = _palette()

    meta    = job_data.get("job_meta", {})
    triple  = job_data.get("triple_result", {})
    summary = job_data.get("job_summary", {})
    release = triple.get("release", {})

    # -----------------------------------------------------------------------
    # Página 1: cabecera + metadatos + triple result + autorización
    # -----------------------------------------------------------------------
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _draw_header(page, assets_dir, p)

    y = HEADER_H + 20

    # -- Metadatos --
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + 80),
                   fill=p["light"], color=p["border"], width=0.8)
    page.insert_text(pymupdf.Point(45, y + 20),
                     f"Archivo: {meta.get('filename', 'documento.pdf')}",
                     fontsize=10, fontname="helv", color=p["navy"])
    page.insert_text(pymupdf.Point(45, y + 38),
                     f"ID Trabajo: {meta.get('job_id', 'N/A')}",
                     fontsize=8.5, fontname="helv", color=p["slate"])
    page.insert_text(pymupdf.Point(220, y + 38),
                     f"Perfil Objetivo: {meta.get('profile_id', 'OFFSET_300')}",
                     fontsize=8.5, fontname="helv", color=p["slate"])
    page.insert_text(pymupdf.Point(400, y + 38),
                     f"Páginas: {summary.get('pages', 1)}",
                     fontsize=8.5, fontname="helv", color=p["slate"])

    orig_icc  = summary.get("original_icc_detected", {})
    orig_name = orig_icc.get("friendly_description") or orig_icc.get("identifier") or "No declarado"
    if len(orig_name) > 34: orig_name = orig_name[:31] + "..."

    icc_info = summary.get("icc_detected", {})
    icc_name = icc_info.get("friendly_description") or icc_info.get("identifier") or meta.get("selected_icc") or "No declarado"
    if len(icc_name) > 30: icc_name = icc_name[:27] + "..."

    page.insert_text(pymupdf.Point(45, y + 54),
                     f"ICC Origen: {orig_name}", fontsize=8, fontname="helv", color=p["slate"])
    page.insert_text(pymupdf.Point(220, y + 54),
                     f"ICC Salida: {icc_name}", fontsize=8, fontname="helv", color=p["slate"])
    page.insert_text(pymupdf.Point(400, y + 54),
                     f"Sangre: {str(summary.get('bleed_note', 'N/A'))[:25]}",
                     fontsize=8.5, fontname="helv", color=p["slate"])

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    page.insert_text(pymupdf.Point(45, y + 70),
                     f"Fecha/Hora: {now_str}", fontsize=8, fontname="helv", color=p["slate"])
    page.insert_text(pymupdf.Point(220, y + 70),
                     f"SHA-256: {meta.get('sha256', '')[:28]}...", fontsize=8, fontname="helv", color=p["slate"])
    page.insert_text(pymupdf.Point(400, y + 70),
                     f"Imágenes: {summary.get('total_images', 0)} "
                     f"({summary.get('low_res_images', 0)} bajas, {summary.get('non_cmyk_images', 0)} RGB)",
                     fontsize=8, fontname="helv", color=p["slate"])

    y += 95

    # -- Triple Result --
    box_w = 166.5
    gap   = 10

    tech = triple.get("technical", {})
    all_findings  = job_data.get("findings", [])

    # Filtrar incidencias resueltas según historial de correcciones
    findings = list(all_findings)
    if meta.get("has_cmyk_converted") or meta.get("cmyk_converted_pdf_path"):
        findings = [f for f in findings
                    if "rgb" not in f.get("title", "").lower()
                    and "rgb" not in f.get("message", "").lower()]

    if meta.get("has_overprint_fixed") or meta.get("overprint_fixed_pdf_path"):
        findings = [f for f in findings
                    if f.get("rule_id") not in ("BLACK_TEXT_KNOCKOUT", "BLACK_TEXT_KNOCKOUT_100")
                    and not (("calado" in f.get("title", "").lower() or "knockout" in f.get("title", "").lower())
                             and "barniz" not in f.get("title", "").lower())]

    if meta.get("has_varnish_overprint_fixed"):
        findings = [f for f in findings
                    if f.get("rule_id") != "VARNISH_KNOCKOUT"
                    and "barniz" not in f.get("title", "").lower()]

    if meta.get("has_hairline_fixed") or meta.get("hairline_fixed_pdf_path"):
        findings = [f for f in findings
                    if f.get("rule_id") != "HAIRLINE_DETECTED"
                    and "filete" not in f.get("title", "").lower()]

    if meta.get("has_icc_fixed") or meta.get("icc_fixed_pdf_path"):
        findings = [f for f in findings
                    if f.get("rule_id") != "DOCUMENT_OUTPUT_ICC"
                    and "icc" not in f.get("title", "").lower()]

    if meta.get("has_bleed_fixed") or meta.get("bleed_fixed_pdf_path"):
        findings = [f for f in findings
                    if f.get("rule_id") != "BLEED_GEOMETRY_3MM"
                    and "sangrado" not in f.get("title", "").lower()]

    adj_errors   = sum(1 for f in findings if f.get("severity") == "ERROR")
    adj_warnings = sum(1 for f in findings if f.get("severity") == "WARNING")

    if adj_errors > 0:
        t_status = "FAIL";            t_label = "NO CUMPLE"
    elif adj_warnings > 0:
        t_status = "PASS_WITH_WARNINGS"; t_label = "CUMPLE CON AVISOS"
    else:
        t_status = "PASS";            t_label = "CUMPLE"

    t_color = p["green"] if t_status == "PASS" else (p["amber"] if t_status == "PASS_WITH_WARNINGS" else p["red"])
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, MARGIN_X + box_w, y + 60), color=t_color, width=1.2, fill=(1,1,1))
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, MARGIN_X + box_w, y + 18), fill=t_color)
    page.insert_text(pymupdf.Point(42, y + 13), "1. RESULTADO TÉCNICO", fontsize=8, fontname="helv", color=(1,1,1))
    page.insert_text(pymupdf.Point(42, y + 36), t_label, fontsize=10, fontname="helv", color=t_color)
    page.insert_text(pymupdf.Point(42, y + 50), f"{adj_errors} errores, {adj_warnings} avisos",
                     fontsize=7.5, fontname="helv", color=p["slate"])

    content   = triple.get("content", {})
    c_status  = content.get("status", "PENDING_REVIEW")
    cont_col  = p["green"] if c_status == "RESOLVED" else p["amber"]
    x2 = MARGIN_X + box_w + gap
    page.draw_rect(pymupdf.Rect(x2, y, x2 + box_w, y + 60), color=cont_col, width=1.2, fill=(1,1,1))
    page.draw_rect(pymupdf.Rect(x2, y, x2 + box_w, y + 18), fill=cont_col)
    page.insert_text(pymupdf.Point(x2 + 7, y + 13), "2. CONTENIDO EDITORIAL", fontsize=8, fontname="helv", color=(1,1,1))
    page.insert_text(pymupdf.Point(x2 + 7, y + 36),
                     "REVISIÓN RESUELTA" if c_status == "RESOLVED" else "REVISIÓN REALIZADA",
                     fontsize=9.5, fontname="helv", color=cont_col)
    page.insert_text(pymupdf.Point(x2 + 7, y + 50),
                     f"{content.get('suggestions_count', 0)} sugerencias revisadas",
                     fontsize=7.5, fontname="helv", color=p["slate"])

    decision_val = release.get("decision", "")
    rel_status   = release.get("status", "AUTHORIZED" if "approved" in decision_val else "PENDING_AUTHORIZATION")
    r_color      = p["green"] if rel_status == "AUTHORIZED" else (p["red"] if rel_status == "REJECTED" else p["amber"])
    x3 = x2 + box_w + gap
    page.draw_rect(pymupdf.Rect(x3, y, x3 + box_w, y + 60), color=r_color, width=1.2, fill=(1,1,1))
    page.draw_rect(pymupdf.Rect(x3, y, x3 + box_w, y + 18), fill=r_color)
    page.insert_text(pymupdf.Point(x3 + 7, y + 13), "3. DICTAMEN DE SALIDA", fontsize=8, fontname="helv", color=(1,1,1))
    page.insert_text(pymupdf.Point(x3 + 7, y + 36),
                     "AUTORIZADO TIRADA" if rel_status == "AUTHORIZED" else "PENDIENTE / RECHAZADO",
                     fontsize=9.5, fontname="helv", color=r_color)
    op_name = release.get("operator") or "Operario de taller"
    page.insert_text(pymupdf.Point(x3 + 7, y + 50),
                     f"Firmado por: {op_name[:20]}", fontsize=7.5, fontname="helv", color=p["slate"])

    y += 75

    # -- Autorización --
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + 65),
                   fill=(0.96, 0.98, 0.96) if rel_status == "AUTHORIZED" else p["light"],
                   color=r_color, width=1.0)
    page.insert_text(pymupdf.Point(45, y + 18),
                     "REGISTRO FORMAL DE AUTORIZACIÓN PARA PRODUCCIÓN",
                     fontsize=9, fontname="helv", color=r_color)
    op_line = f"Operario Responsable: {release.get('operator', 'No firmado')}   |   Decisión: {release.get('decision', 'Autorizar paso a producción (Aprobado)')}"
    if len(op_line) > 90: op_line = op_line[:87] + "..."
    page.insert_text(pymupdf.Point(45, y + 36), op_line, fontsize=8.5, fontname="helv", color=p["navy"])
    obs = release.get("notes") or "Sin observaciones particulares. Documento verificado conforme a los estándares de taller."
    page.insert_text(pymupdf.Point(45, y + 52),
                     f"Observaciones del Taller: {obs[:85]}", fontsize=8, fontname="helv", color=p["slate"])

    y += 80

    # -----------------------------------------------------------------------
    # Título de la sección de incidencias (en página 1)
    # -----------------------------------------------------------------------
    page.insert_text(pymupdf.Point(MARGIN_X, y + 15),
                     "DETALLE DE VERIFICACIONES TÉCNICAS E INCIDENCIAS",
                     fontsize=10, fontname="helv", color=p["navy"])
    page.draw_line(pymupdf.Point(MARGIN_X, y + 20), pymupdf.Point(PAGE_W - MARGIN_X, y + 20),
                   color=p["navy"], width=0.8)
    y += 30

    # -----------------------------------------------------------------------
    # Findings con paginación dinámica (usando la lista ya filtrada)
    # -----------------------------------------------------------------------
    # Límite inferior del área útil en cada página
    BOTTOM_LIMIT = FOOTER_Y - 15

    if not findings:
        page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + 35),
                       fill=(0.92, 0.98, 0.94), color=p["green"], width=0.5)
        page.insert_text(pymupdf.Point(45, y + 22),
                         "✓ Documento totalmente limpio. Supera todas las reglas obligatorias del perfil de preimpresión.",
                         fontsize=8.5, fontname="helv", color=p["green"])
        y += 45
    else:
        pages_list = [page]  # lista de páginas para numerar al final

        for f in findings:
            # Si no cabe el siguiente finding, crear nueva página
            if y + FINDINGS_ROW_H > BOTTOM_LIMIT:
                # Footer en la página actual (número provisional, se actualiza al final)
                page_ref = page  # guardar ref para footer
                pages_list.append(None)  # placeholder, se rellena abajo

                page = doc.new_page(width=PAGE_W, height=PAGE_H)
                _draw_header(page, assets_dir, p)
                pages_list[-1] = page

                # Título de continuación
                y = HEADER_H + 20
                page.insert_text(pymupdf.Point(MARGIN_X, y + 12),
                                 "DETALLE DE VERIFICACIONES TÉCNICAS E INCIDENCIAS (continuación)",
                                 fontsize=9, fontname="helv", color=p["navy"])
                page.draw_line(pymupdf.Point(MARGIN_X, y + 17), pymupdf.Point(PAGE_W - MARGIN_X, y + 17),
                               color=p["navy"], width=0.6)
                y += 28

            is_err   = f.get("severity") == "ERROR"
            b_col    = p["red"] if is_err else p["amber"]
            fill_col = (0.99, 0.95, 0.95) if is_err else (0.99, 0.98, 0.94)
            badge    = "[ERROR]" if is_err else "[AVISO]"

            page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + FINDINGS_ROW_H - 4),
                           fill=fill_col, color=b_col, width=0.5)

            raw_title = f"{badge} Pág {f.get('page', 1)}: {f.get('title', '')}"
            # Reemplazar símbolos matemáticos no compatibles con Helvetica en PyMuPDF
            clean_title = raw_title.replace("≥", ">=").replace("≤", "<=")
            if len(clean_title) > 88: clean_title = clean_title[:85] + "..."
            page.insert_text(pymupdf.Point(42, y + 14), clean_title, fontsize=8, fontname="helv", color=b_col)

            raw_msg = f.get("message", "")
            clean_msg = raw_msg.replace("≥", ">=").replace("≤", "<=")
            if len(clean_msg) > 100: clean_msg = clean_msg[:97] + "..."
            page.insert_text(pymupdf.Point(42, y + 28), clean_msg, fontsize=7, fontname="helv", color=p["slate"])

            y += FINDINGS_ROW_H

    # -----------------------------------------------------------------------
    # Footers con numeración correcta (ahora que sabemos el total de páginas)
    # -----------------------------------------------------------------------
    total_pages = len(doc)
    job_id_str  = meta.get("job_id", "N/A")
    for page_num, pg in enumerate(doc, start=1):
        _draw_footer(pg, p, job_id_str, page_num, total_pages)

    doc.save(str(output_path), deflate=True, garbage=4)
    doc.close()
    return output_path
