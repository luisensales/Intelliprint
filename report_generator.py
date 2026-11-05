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
    assets_dir = Path(__file__).parent / "assets"
    imago_path = assets_dir / "Logo-intelliprint-imago.jpg"
    full_logo_path = assets_dir / "Logo-intelliprint.jpg"

    if imago_path.exists():
        page.insert_image(pymupdf.Rect(28, 13, 76, 62), filename=str(imago_path), keep_proportion=True)
        text_x = 84
    elif full_logo_path.exists():
        page.insert_image(pymupdf.Rect(28, 16, 150, 58), filename=str(full_logo_path), keep_proportion=True)
        text_x = 158
    else:
        text_x = 35

    # Title and subtitle text
    page.insert_text(pymupdf.Point(text_x, 35), "INTELLIPRINT · DICTAMEN OFICIAL", fontsize=11.5, color=(1, 1, 1), fontname="helv")
    page.insert_text(pymupdf.Point(text_x, 52), "Certificado de Preflight y Control de Calidad", fontsize=8, color=(0.75, 0.82, 0.90), fontname="helv")

    # 3 Institutional Partner Logos: Salesianos, Mendizabala, Dept. Educación
    p_sales = assets_dir / "logo-salesianos.png"
    p_mendi = assets_dir / "logo-mendizabala.png"
    p_edu   = assets_dir / "logo-dept-educacion-1.png"

    if p_sales.exists() and p_mendi.exists() and p_edu.exists():
        capsule = pymupdf.Rect(310, 13, 567, 62)
        page.draw_rect(capsule, fill=(1, 1, 1), radius=0.08)

        # 1. Salesianos
        page.insert_image(pymupdf.Rect(318, 17, 390, 58), filename=str(p_sales), keep_proportion=True)
        page.draw_line(pymupdf.Point(395, 20), pymupdf.Point(395, 55), color=(0.88, 0.88, 0.88), width=0.6)

        # 2. Mendizabala
        page.insert_image(pymupdf.Rect(400, 17, 474, 58), filename=str(p_mendi), keep_proportion=True)
        page.draw_line(pymupdf.Point(479, 20), pymupdf.Point(479, 55), color=(0.88, 0.88, 0.88), width=0.6)

        # 3. Departamento de Educación
        page.insert_image(pymupdf.Rect(484, 17, 560, 58), filename=str(p_edu), keep_proportion=True)

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
    
    orig_icc = summary.get("original_icc_detected", {})
    orig_name = orig_icc.get("friendly_description") or orig_icc.get("identifier") or "No declarado"
    if len(orig_name) > 34: orig_name = orig_name[:31] + "..."

    icc_info = summary.get("icc_detected", {})
    icc_name = icc_info.get("friendly_description") or icc_info.get("identifier") or meta.get("selected_icc") or "No declarado"
    if len(icc_name) > 30: icc_name = icc_name[:27] + "..."

    page.insert_text(pymupdf.Point(45, y + 54), f"ICC Origen: {orig_name}", fontsize=8, fontname="helv", color=c_slate)
    page.insert_text(pymupdf.Point(220, y + 54), f"ICC Salida: {icc_name}", fontsize=8, fontname="helv", color=c_slate)
    page.insert_text(pymupdf.Point(400, y + 54), f"Sangre: {str(summary.get('bleed_note', 'N/A'))[:25]}", fontsize=8.5, fontname="helv", color=c_slate)

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    page.insert_text(pymupdf.Point(45, y + 70), f"Fecha/Hora: {now_str}", fontsize=8, fontname="helv", color=c_slate)
    page.insert_text(pymupdf.Point(220, y + 70), f"SHA-256: {meta.get('sha256', '')[:28]}...", fontsize=8, fontname="helv", color=c_slate)
    page.insert_text(pymupdf.Point(400, y + 70), f"Imágenes: {summary.get('total_images', 0)} ({summary.get('low_res_images', 0)} bajas, {summary.get('non_cmyk_images', 0)} RGB)", fontsize=8, fontname="helv", color=c_slate)

    y += 95
    # 3. Triple Result Boxes
    box_w = 166.5
    gap = 10

    # Recalcular contadores técnicos si se filtraron avisos RGB
    tech = triple.get("technical", {})
    all_findings = job_data.get("findings", [])
    cmyk_converted = meta.get("cmyk_converted_pdf_path")

    if cmyk_converted:
        # Contar cuántos findings RGB se han eliminado
        rgb_findings = [f for f in all_findings if "rgb" in f.get("title", "").lower() or "rgb" in f.get("message", "").lower()]
        rgb_warnings = sum(1 for f in rgb_findings if f.get("severity") != "ERROR")
        rgb_errors   = sum(1 for f in rgb_findings if f.get("severity") == "ERROR")
        adj_warnings = max(0, tech.get("warnings_count", 0) - rgb_warnings)
        adj_errors   = max(0, tech.get("errors_count",   0) - rgb_errors)
    else:
        adj_warnings = tech.get("warnings_count", 0)
        adj_errors   = tech.get("errors_count",   0)

    # Recalcular estado
    if adj_errors > 0:
        t_status = "FAIL"
        t_label  = tech.get("label", "NO CUMPLE")
    elif adj_warnings > 0:
        t_status = "PASS_WITH_WARNINGS"
        t_label  = "CUMPLE CON AVISOS"
    else:
        t_status = "PASS"
        t_label  = "CUMPLE"

    t_color = c_green if t_status == "PASS" else (c_amber if t_status == "PASS_WITH_WARNINGS" else c_red)
    page.draw_rect(pymupdf.Rect(35, y, 35 + box_w, y + 60), color=t_color, width=1.2, fill=(1, 1, 1))
    page.draw_rect(pymupdf.Rect(35, y, 35 + box_w, y + 18), fill=t_color)
    page.insert_text(pymupdf.Point(42, y + 13), "1. RESULTADO TÉCNICO", fontsize=8, fontname="helv", color=(1, 1, 1))
    page.insert_text(pymupdf.Point(42, y + 36), t_label, fontsize=10, fontname="helv", color=t_color)
    page.insert_text(pymupdf.Point(42, y + 50), f"{adj_errors} errores, {adj_warnings} avisos", fontsize=7.5, fontname="helv", color=c_slate)

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

    # Si se ha generado un PDF convertido a CMYK, filtrar los avisos de imágenes RGB
    cmyk_converted = job_data.get("job_meta", {}).get("cmyk_converted_pdf_path")
    if cmyk_converted:
        findings = [f for f in findings if "rgb" not in f.get("title", "").lower() and "rgb" not in f.get("message", "").lower()]

    if not findings:
        page.draw_rect(pymupdf.Rect(35, y, 560, y + 35), fill=(0.92, 0.98, 0.94), color=c_green, width=0.5)
        page.insert_text(pymupdf.Point(45, y + 22), "✓ Documento totalmente limpio. Supera todas las reglas obligatorias del perfil de preimpresión.", fontsize=8.5, fontname="helv", color=c_green)
        y += 45
    else:
        for idx, f in enumerate(findings[:12]):
            if y > 750:
                break
            is_err = f.get("severity") == "ERROR"
            b_col = c_red if is_err else c_amber
            fill_col = (0.99, 0.95, 0.95) if is_err else (0.99, 0.98, 0.94)
            # Bloque de 2 líneas: título arriba, mensaje debajo
            page.draw_rect(pymupdf.Rect(35, y, 560, y + 36), fill=fill_col, color=b_col, width=0.5)
            badge = "[ERROR]" if is_err else "[AVISO]"
            title_text = f"{badge} Pág {f.get('page', 1)}: {f.get('title', '')}"
            if len(title_text) > 85: title_text = title_text[:82] + "..."
            page.insert_text(pymupdf.Point(42, y + 14), title_text, fontsize=8, fontname="helv", color=b_col)
            msg = f.get("message", "")
            if len(msg) > 95: msg = msg[:92] + "..."
            page.insert_text(pymupdf.Point(42, y + 28), msg, fontsize=7, fontname="helv", color=c_slate)
            y += 40

    # Footer
    page.draw_line(pymupdf.Point(35, 805), pymupdf.Point(560, 805), color=c_border, width=0.5)
    page.insert_text(pymupdf.Point(35, 818), "IntelliPrint Preflight Web v1.2.0 · Sistema Profesional de Calidad en Preimpresión", fontsize=7.5, fontname="helv", color=c_slate)
    page.insert_text(pymupdf.Point(450, 818), f"Certificado ID: {meta.get('job_id', 'N/A')}", fontsize=7.5, fontname="helv", color=c_slate)

    doc.save(str(output_path), deflate=True, garbage=4)
    doc.close()
    return output_path

