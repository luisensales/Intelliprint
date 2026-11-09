"""
printer_marks_generator.py - Generador de Marcas de Imprenta Profesionales
Inyecta marcas de corte (crop marks), marcas de sangrado, cruces de registro,
tiras de control densitométrico CMYK e información de archivo en el área de slug exterior.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import pymupdf
from pdf_utils import preserve_output_intents
import pikepdf


def add_printer_marks_to_pdf(
    pdf_path: str,
    output_path: str,
    slug_margin_mm: float = 10.0,
    bleed_mm: float = 3.0,
    job_filename: Optional[str] = None,
    job_id: Optional[str] = None,
    base_url: str = "",
) -> Dict[str, Any]:
    """
    Añade marcas de imprenta estándar ISO a todas las páginas de un PDF:
    - Marcas de corte (Crop Marks) en los 4 vértices del TrimBox.
    - Cruces de registro (Registration Targets) centradas en los 4 bordes.
    - Tira de control cromático CMYK (parches C, M, Y, K y sobreimpresiones).
    - Información de trabajo (nombre de archivo, página y fecha).
    - Normalización geométrica: MediaBox aloja las marcas, BleedBox define el sangrado,
      y TrimBox define las dimensiones netas de corte final.

    :param pdf_path: Ruta al PDF de entrada.
    :param output_path: Ruta de salida para el PDF con marcas de imprenta.
    :param slug_margin_mm: Margen exterior para marcas (10.0 mm por defecto).
    :param bleed_mm: Distancia de sangrado (3.0 mm por defecto).
    :param job_filename: Nombre visible del archivo para la tira de información.
    :return: Diccionario con estadísticas.
    """
    bleed_pt = bleed_mm * 72.0 / 25.4
    slug_pt = slug_margin_mm * 72.0 / 25.4
    margin = bleed_pt + slug_pt
    offset = 2.0 * 72.0 / 25.4  # Separación de 2 mm desde el corte
    mark_len = 5.0 * 72.0 / 25.4  # Longitud de 5 mm de las marcas

    src_doc = pymupdf.open(pdf_path)
    dst_doc = pymupdf.open()

    total_pages = len(src_doc)
    doc_name = job_filename or Path(pdf_path).name
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    black = (0.0, 0.0, 0.0)

    for idx, page in enumerate(src_doc):
        # Determinar el tamaño neto de corte (TrimBox original o página completa)
        if page.trimbox.width > 0 and page.trimbox.height > 0 and page.trimbox != page.mediabox:
            trim = page.trimbox
        else:
            trim = page.rect

        w_pt = trim.width
        h_pt = trim.height
        tot_w = round(w_pt + 2 * margin, 2)
        tot_h = round(h_pt + 2 * margin, 2)

        np = dst_doc.new_page(width=tot_w, height=tot_h)
        np.set_mediabox(np.rect)
        np.set_bleedbox(pymupdf.Rect(slug_pt, slug_pt, tot_w - slug_pt, tot_h - slug_pt))
        np.set_trimbox(pymupdf.Rect(margin, margin, margin + w_pt, margin + h_pt))

        # Colocar el contenido de la página original centrado en el TrimBox
        np.show_pdf_page(
            pymupdf.Rect(margin, margin, margin + w_pt, margin + h_pt),
            src_doc,
            idx
        )

        tx0 = margin
        ty0 = margin
        tx1 = margin + w_pt
        ty1 = margin + h_pt

        # 1. Marcas de Corte (Crop Marks) en los 4 vértices
        # Superior Izquierda
        np.draw_line(pymupdf.Point(tx0, ty0 - offset - mark_len), pymupdf.Point(tx0, ty0 - offset), color=black, width=0.35)
        np.draw_line(pymupdf.Point(tx0 - offset - mark_len, ty0), pymupdf.Point(tx0 - offset, ty0), color=black, width=0.35)
        # Superior Derecha
        np.draw_line(pymupdf.Point(tx1, ty0 - offset - mark_len), pymupdf.Point(tx1, ty0 - offset), color=black, width=0.35)
        np.draw_line(pymupdf.Point(tx1 + offset, ty0), pymupdf.Point(tx1 + offset + mark_len, ty0), color=black, width=0.35)
        # Inferior Izquierda
        np.draw_line(pymupdf.Point(tx0, ty1 + offset), pymupdf.Point(tx0, ty1 + offset + mark_len), color=black, width=0.35)
        np.draw_line(pymupdf.Point(tx0 - offset - mark_len, ty1), pymupdf.Point(tx0 - offset, ty1), color=black, width=0.35)
        # Inferior Derecha
        np.draw_line(pymupdf.Point(tx1, ty1 + offset), pymupdf.Point(tx1, ty1 + offset + mark_len), color=black, width=0.35)
        np.draw_line(pymupdf.Point(tx1 + offset, ty1), pymupdf.Point(tx1 + offset + mark_len, ty1), color=black, width=0.35)

        # 2. Cruces de Registro (Registration Targets) en los 4 costados
        def draw_reg_target(p, cx, cy):
            p.draw_circle(pymupdf.Point(cx, cy), 5.0, color=black, width=0.35)
            p.draw_circle(pymupdf.Point(cx, cy), 2.5, color=black, width=0.35)
            p.draw_line(pymupdf.Point(cx - 7.0, cy), pymupdf.Point(cx + 7.0, cy), color=black, width=0.35)
            p.draw_line(pymupdf.Point(cx, cy - 7.0), pymupdf.Point(cx, cy + 7.0), color=black, width=0.35)

        draw_reg_target(np, margin + w_pt / 2, slug_pt / 2)
        draw_reg_target(np, margin + w_pt / 2, tot_h - slug_pt / 2)
        draw_reg_target(np, slug_pt / 2, margin + h_pt / 2)
        draw_reg_target(np, tot_w - slug_pt / 2, margin + h_pt / 2)

        # 3. Tira de Control Normalizada FOGRA / ISO 12647-2 (Media Wedge con Balance de Grises)
        try:
            from control_strip_engine import draw_fogra_control_strip
            strip_w_est = 245.0
            start_x = max(margin + 180.0, tot_w - margin - strip_w_est)
            start_y = slug_pt / 2 - 3.5
            draw_fogra_control_strip(np, start_x, start_y, swatch_w=5.5, swatch_h=5.5, show_labels=True)
        except Exception as e:
            # Fallback a tira básica si hubiera algún problema
            colors = [
                (0.0, 0.65, 0.9), (0.85, 0.0, 0.5), (0.95, 0.85, 0.0), (0.1, 0.1, 0.1),
                (0.3, 0.15, 0.6), (0.1, 0.6, 0.25), (0.85, 0.25, 0.1), (0.5, 0.5, 0.5)
            ]
            swatch_size = 6.0
            start_x = tot_w - margin - len(colors) * (swatch_size + 2)
            start_y = slug_pt / 2 - swatch_size / 2
            for i, col in enumerate(colors):
                sx = start_x + i * (swatch_size + 2)
                np.draw_rect(pymupdf.Rect(sx, start_y, sx + swatch_size, start_y + swatch_size), color=black, fill=col, width=0.25)

        # 4. Información de Trabajo (Slug)
        info_text = f"{doc_name} · Pág {idx + 1}/{total_pages} · {now_str} · IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII"
        np.insert_text(pymupdf.Point(margin, slug_pt / 2 + 2), info_text, fontsize=6.5, color=(0.2, 0.2, 0.2))

        # Código QR de Trazabilidad para el Maquinista
        if job_id:
            try:
                from traceability_engine import embed_traceability_qr
                qr_sz = slug_pt * 0.75
                qr_rect = pymupdf.Rect(margin - qr_sz - 4, slug_pt / 2 - qr_sz / 2, margin - 4, slug_pt / 2 + qr_sz / 2)
                embed_traceability_qr(np, qr_rect, job_id=job_id, base_url=base_url)
            except Exception:
                pass

    temp_marked_path = str(output_path) + ".tmp.pdf"
    dst_doc.save(temp_marked_path)
    dst_doc.close()
    src_doc.close()

    try:
        preserve_output_intents(pdf_path, temp_marked_path, output_path)
    finally:
        Path(temp_marked_path).unlink(missing_ok=True)

    return {
        "status": "success",
        "pages_processed": total_pages,
        "bleed_mm": bleed_mm,
        "slug_margin_mm": slug_margin_mm
    }

