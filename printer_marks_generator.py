"""
printer_marks_generator.py - Generador de Marcas de Imprenta Profesionales
Inyecta marcas de corte (crop marks), marcas de sangrado, cruces de registro,
tiras de control densitométrico CMYK e información de archivo en el área de slug exterior.
"""

from datetime import datetime
from io import BytesIO
import math
from pathlib import Path
from typing import Dict, Any, List, Optional
import pymupdf
from pdf_utils import atomic_output, add_form_resource, pdf_numbers, rect_clip
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
    if (not all(math.isfinite(v) for v in (bleed_mm, slug_margin_mm))
            or not 0 <= bleed_mm <= 100 or not 8 <= slug_margin_mm <= 100):
        raise ValueError('Sangrado o margen de marcas no válido (margen mínimo 8 mm).')

    src_doc = pikepdf.open(pdf_path)
    dst_doc = pymupdf.open()

    total_pages = len(src_doc.pages)
    doc_name = job_filename or Path(pdf_path).name
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    black = (0.0, 0.0, 0.0, 1.0)

    for idx, page in enumerate(src_doc.pages):
        trim = list(map(float, page.trimbox))
        unit = float(page.obj.get('/UserUnit', 1))
        if not math.isfinite(unit) or unit <= 0:
            raise ValueError('Unidad de página PDF no válida.')
        factor = 72 / 25.4 / unit
        bleed_pt, slug_pt = bleed_mm * factor, slug_margin_mm * factor
        margin = bleed_pt + slug_pt
        offset = bleed_pt + 1 * factor  # Marks begin OUTSIDE the artwork bleed.
        mark_len = 5 * factor
        w_pt, h_pt = trim[2] - trim[0], trim[3] - trim[1]
        if w_pt <= 0 or h_pt <= 0:
            raise ValueError('Caja de corte no válida.')
        tot_w, tot_h = w_pt + 2 * margin, h_pt + 2 * margin

        np = dst_doc.new_page(width=tot_w, height=tot_h)
        # This transparent page contains ONLY marks. Native source content is
        # kept in place below; fitting a whole bled page into TrimBox shrank it.

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
            with pymupdf.open() as strip_doc:
                strip_page = strip_doc.new_page(width=400, height=20)
                strip_width = draw_fogra_control_strip(strip_page, 0, 1, swatch_w=5.5, swatch_h=5.5, show_labels=True)
                scale = min(1 / unit, max(w_pt / 2 - 10 / unit, 1) / strip_width)
                rect = pymupdf.Rect(margin, tot_h - slug_pt / 2 - 6 * scale,
                                    margin + strip_width * scale, tot_h - slug_pt / 2 + 6 * scale)
                np.show_pdf_page(rect, strip_doc, 0, clip=pymupdf.Rect(0, 0, strip_width, 12))
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
        font_size = 6.5 / unit
        available = max(w_pt / 2 - 10 / unit, 1)
        while info_text and pymupdf.get_text_length(info_text, fontsize=font_size) > available:
            info_text = info_text[:-1]
        np.insert_text(pymupdf.Point(margin, slug_pt / 2 + 2 / unit), info_text, fontsize=font_size, color=black)

        # Código QR de Trazabilidad para el Maquinista
        if job_id:
            try:
                from traceability_engine import embed_traceability_qr
                qr_sz = slug_pt * 0.75
                qr_rect = pymupdf.Rect(margin - qr_sz - 4, slug_pt / 2 - qr_sz / 2, margin - 4, slug_pt / 2 + qr_sz / 2)
                embed_traceability_qr(np, qr_rect, job_id=job_id, base_url=base_url)
            except Exception:
                pass

    try:
        with pikepdf.open(BytesIO(dst_doc.tobytes())) as marks:
            for page, overlay in zip(src_doc.pages, marks.pages):
                trim = list(map(float, page.trimbox))
                unit = float(page.obj.get('/UserUnit', 1))
                bleed = bleed_mm * 72 / 25.4 / unit
                slug = slug_margin_mm * 72 / 25.4 / unit
                bb = [trim[0] - bleed, trim[1] - bleed, trim[2] + bleed, trim[3] + bleed]
                media = [bb[0] - slug, bb[1] - slug, bb[2] + slug, bb[3] + slug]
                # Clip old slug/marks, retaining all artwork INCLUDING its bleed.
                page.contents_add(('q\n' + rect_clip(bb)).encode('ascii'), prepend=True)
                page.contents_add(b'\nQ\n')
                form = src_doc.copy_foreign(overlay.as_form_xobject(handle_transformations=False))
                form.BBox = list(map(float, overlay.mediabox))
                name = add_form_resource(page, form)
                page.contents_add(('q\n' + pdf_numbers([1, 0, 0, 1, media[0], media[1]]) +
                                   f' cm\n{name} Do\nQ\n').encode('ascii'))
                page.MediaBox = media
                page.CropBox = media
                page.TrimBox = trim
                page.BleedBox = bb
            with atomic_output(output_path) as temporary:
                src_doc.save(temporary)
                src_doc.close()  # Release the source before replacing it on Windows.
    finally:
        dst_doc.close()
        src_doc.close()

    return {
        "status": "success", "success": True,
        "pages_processed": total_pages,
        "bleed_mm": bleed_mm,
        "slug_margin_mm": slug_margin_mm
    }

