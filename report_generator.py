import os
from pathlib import Path
from datetime import datetime
import pymupdf

def generate_preflight_certificate_pdf(job_data, output_path):
    """
    Generates a professional Preflight & Production Release Certificate PDF.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=595.3, height=841.9) # A4 format

    # Prepress palette
    c_navy = (31/255, 38/255, 44/255) # Hex #1f262c matching Logo-intelliprint.jpg
    c_blue = (0.13, 0.40, 0.85)
    c_slate = (0.35, 0.40, 0.48)
    c_light = (0.95, 0.96, 0.98)
    c_green = (0.10, 0.60, 0.35)
    c_red = (0.85, 0.20, 0.20)
    c_amber = (0.85, 0.55, 0.10)
    c_border = (0.80, 0.84, 0.88)

    # 1. Header Banner
    page.draw_rect(pymupdf.Rect(0, 0, 595.3, 75), fill=c_navy)

    # Logo first (left), seamless without white background or border
    logo_path = Path(__file__).parent / "assets" / "Logo-intelliprint.jpg"
    if logo_path.exists():
        page.insert_image(pymupdf.Rect(30, 13, 214, 65), filename=str(logo_path), keep_proportion=True)
        text_x = 226
    else:
        text_x = 35

    # Then title and subtitle text
    page.insert_text(pymupdf.Point(text_x, 35), "INTELLIPRINT · DICTAMEN OFICIAL DE PRODUCCIÓN", fontsize=12.5, color=(1, 1, 1), fontname="helv")
    page.insert_text(pymupdf.Point(text_x, 53), "Certificado de Preflight, Control de Calidad y Autorización de Salida a Taller", fontsize=8.5, color=(0.75, 0.82, 0.90), fontname="helv")

    meta = job_data.get("job_meta", {})
    triple = job_data.get("triple_result", {})
    summary = job_data.get("job_summary", {})
    release = triple.get("release", {})

    y = 95
    # 2. Metadata Box
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 80), fill=c_light, color=c_border, width=0.8)
    page.insert_text(pymupdf.Point(45, y + 20), f"Archivo: {meta.get('filename', 'documento.pdf')}", fontsize=10, fontname="helv", color=c_navy)
    page.insert_text(pymupdf.Point(45, y + 38), f"ID Trabajo: {meta.get('job_id', 'N/A')}", fontsize=8.5, fontname="helv", color=c_slate)
    page.insert_text(pymupdf.Point(220, y + 38), f"Perfil Objetivo: {meta.get('profile_id', 'OFFSET_300')}", fontsize=8.5, fontname="helv", color=c_slate)
    page.insert_text(pymupdf.Point(400, y + 38), f"Páginas: {summary.get('pages', 1)}", fontsize=8.5, fontname="helv", color=c_slate)
    
    icc_info = summary.get("icc_detected", {})
    icc_name = icc_info.get("identifier") or meta.get("selected_icc") or "No declarado"
    page.insert_text(pymupdf.Point(45, y + 54), f"Perfil ICC Salida: {icc_name}", fontsize=8.5, fontname="helv", color=c_slate)
    page.insert_text(pymupdf.Point(400, y + 54), f"Sangre: {str(summary.get('bleed_note', 'N/A'))[:25]}", fontsize=8.5, fontname="helv", color=c_slate)

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    page.insert_text(pymupdf.Point(45, y + 70), f"Fecha/Hora: {now_str}", fontsize=8, fontname="helv", color=c_slate)
    page.insert_text(pymupdf.Point(220, y + 70), f"SHA-256: {meta.get('sha256', '')[:28]}...", fontsize=8, fontname="helv", color=c_slate)

    y += 95
    # 3. Triple Result Boxes
    box_w = 166.5
    gap = 10
    
    # Technical
    tech = triple.get("technical", {})
    t_status = tech.get("status", "FAIL")
    t_color = c_green if t_status == "PASS" else (c_amber if t_status == "PASS_WITH_WARNINGS" else c_red)
    page.draw_rect(pymupdf.Rect(35, y, 35 + box_w, y + 60), color=t_color, width=1.2, fill=(1, 1, 1))
    page.draw_rect(pymupdf.Rect(35, y, 35 + box_w, y + 18), fill=t_color)
    page.insert_text(pymupdf.Point(42, y + 13), "1. RESULTADO TÉCNICO", fontsize=8, fontname="helv", color=(1, 1, 1))
    page.insert_text(pymupdf.Point(42, y + 36), tech.get("label", "NO CUMPLE"), fontsize=10, fontname="helv", color=t_color)
    page.insert_text(pymupdf.Point(42, y + 50), f"{tech.get('errors_count', 0)} errores, {tech.get('warnings_count', 0)} avisos", fontsize=7.5, fontname="helv", color=c_slate)

    # Content
    content = triple.get("content", {})
    c_status = content.get("status", "PENDING_REVIEW")
    cont_col = c_green if c_status == "RESOLVED" else c_amber
    x2 = 35 + box_w + gap
    page.draw_rect(pymupdf.Rect(x2, y, x2 + box_w, y + 60), color=cont_col, width=1.2, fill=(1, 1, 1))
    page.draw_rect(pymupdf.Rect(x2, y, x2 + box_w, y + 18), fill=cont_col)
    page.insert_text(pymupdf.Point(x2 + 7, y + 13), "2. CONTENIDO EDITORIAL", fontsize=8, fontname="helv", color=(1, 1, 1))
    page.insert_text(pymupdf.Point(x2 + 7, y + 36), "REVISIÓN RESUELTA" if c_status == "RESOLVED" else "REVISIÓN REALIZADA", fontsize=9.5, fontname="helv", color=cont_col)
    page.insert_text(pymupdf.Point(x2 + 7, y + 50), f"{content.get('suggestions_count', 0)} sugerencias revisadas", fontsize=7.5, fontname="helv", color=c_slate)

    # Release
    decision_val = release.get("decision", "")
    rel_status = release.get("status", "AUTHORIZED" if "approved" in decision_val else "PENDING_AUTHORIZATION")
    r_color = c_green if rel_status == "AUTHORIZED" else (c_red if rel_status == "REJECTED" else c_amber)
    x3 = x2 + box_w + gap
    page.draw_rect(pymupdf.Rect(x3, y, x3 + box_w, y + 60), color=r_color, width=1.2, fill=(1, 1, 1))
    page.draw_rect(pymupdf.Rect(x3, y, x3 + box_w, y + 18), fill=r_color)
    page.insert_text(pymupdf.Point(x3 + 7, y + 13), "3. DICTAMEN DE SALIDA", fontsize=8, fontname="helv", color=(1, 1, 1))
    page.insert_text(pymupdf.Point(x3 + 7, y + 36), "AUTORIZADO TIRADA" if rel_status == "AUTHORIZED" else "PENDIENTE / RECHAZADO", fontsize=9.5, fontname="helv", color=r_color)
    op_name = release.get("operator") or "Operario de taller"
    page.insert_text(pymupdf.Point(x3 + 7, y + 50), f"Firmado por: {op_name[:20]}", fontsize=7.5, fontname="helv", color=c_slate)

    y += 75
    # 4. Official Signature / Authorization Box
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 65), fill=(0.96, 0.98, 0.96) if rel_status == "AUTHORIZED" else c_light, color=r_color, width=1.0)
    page.insert_text(pymupdf.Point(45, y + 18), "REGISTRO FORMAL DE AUTORIZACIÓN PARA PRODUCCIÓN", fontsize=9, fontname="helv", color=r_color)
    page.insert_text(pymupdf.Point(45, y + 36), f"Operario Responsable: {release.get('operator', 'No firmado')}   |   Decisión: {release.get('decision', 'Autorizar paso a producción (Aprobado)')}", fontsize=8.5, fontname="helv", color=c_navy)
    obs = release.get("notes") or "Sin observaciones particulares. Documento verificado conforme a los estándares de taller."
    page.insert_text(pymupdf.Point(45, y + 52), f"Observaciones del Taller: {obs[:80]}", fontsize=8, fontname="helv", color=c_slate)

    y += 80
    # 5. Technical Findings Section
    page.insert_text(pymupdf.Point(35, y + 15), "DETALLE DE VERIFICACIONES TÉCNICAS E INCIDENCIAS", fontsize=10, fontname="helv", color=c_navy)
    page.draw_line(pymupdf.Point(35, y + 20), pymupdf.Point(560, y + 20), color=c_navy, width=0.8)
    y += 30

    findings = job_data.get("findings", [])
    if not findings:
        page.draw_rect(pymupdf.Rect(35, y, 560, y + 35), fill=(0.92, 0.98, 0.94), color=c_green, width=0.5)
        page.insert_text(pymupdf.Point(45, y + 22), "✓ Documento totalmente limpio. Supera todas las reglas obligatorias del perfil de preimpresión.", fontsize=8.5, fontname="helv", color=c_green)
        y += 45
    else:
        for idx, f in enumerate(findings[:12]):
            if y > 760:
                break
            is_err = f.get("severity") == "ERROR"
            b_col = c_red if is_err else c_amber
            page.draw_rect(pymupdf.Rect(35, y, 560, y + 24), fill=(0.99, 0.95, 0.95) if is_err else (0.99, 0.98, 0.94), color=b_col, width=0.5)
            badge = "[ERROR]" if is_err else "[AVISO]"
            page.insert_text(pymupdf.Point(42, y + 15), f"{badge} Pág {f.get('page', 1)}: {f.get('title', '')}", fontsize=8, fontname="helv", color=b_col)
            msg = f.get("message", "")
            if len(msg) > 65: msg = msg[:62] + "..."
            page.insert_text(pymupdf.Point(260, y + 15), msg, fontsize=7.5, fontname="helv", color=c_slate)
            y += 28

    # Footer
    page.draw_line(pymupdf.Point(35, 805), pymupdf.Point(560, 805), color=c_border, width=0.5)
    page.insert_text(pymupdf.Point(35, 818), "IntelliPrint Preflight Web v1.2.0 · Sistema Profesional de Calidad en Preimpresión", fontsize=7.5, fontname="helv", color=c_slate)
    page.insert_text(pymupdf.Point(450, 818), f"Certificado ID: {meta.get('job_id', 'N/A')}", fontsize=7.5, fontname="helv", color=c_slate)

    doc.save(str(output_path))
    doc.close()
    return output_path

