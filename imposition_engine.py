"""
imposition_engine.py – Motor de Imposición de Pliegos de Taller (Prepress Imposition Engine).

Permite:
  1. Paso y Repetición (Step & Repeat / N-Up multi-pose):
     Montaje automático optimizado de tarjetas, flyers, postales o adhesivos en pliegos SRA3, A3, A4 o B3,
     con cálculo de máximo aprovechamiento, calles de corte intermedias (inter-cut) y sangrado.
  2. Cuadernillos Grapados (Saddle-Stitch Booklet 2-Up):
     Casado automático de páginas encaradas para folletos y revistas grapadas (múltiplos de 4).
  3. Montaje Multi-página (2-Up / 4-Up estándar):
     Distribución de documentos de múltiples páginas en pliegos de producción.
  4. Generación de marcas de corte perimetrales e intermedias, cruces de registro,
     marcas de plegado punteadas, tiras de control CMYK y datos del pliego (Slug).
"""

from __future__ import annotations

import io
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf
from PIL import Image

PT_PER_MM = 72.0 / 25.4
MM_PER_PT = 25.4 / 72.0

STANDARD_SHEET_SIZES_MM: Dict[str, Tuple[float, float]] = {
    "SRA3": (320.0, 450.0),  # Estándar imprenta digital (Ancho x Alto en vertical)
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "B3": (350.0, 500.0),   # Medio pliego offset pequeño formato
    "SRA4": (225.0, 320.0),
}


def _get_page_boxes_mm(page: pymupdf.Page) -> Tuple[float, float, float, float]:
    """
    Obtiene las dimensiones netas de corte (TrimBox) y brutas con sangre en milímetros.
    Devuelve (trim_w_mm, trim_h_mm, total_w_mm, total_h_mm).
    """
    rect_trim = page.rect
    try:
        tb = page.trimbox
        if tb and tb.is_valid and tb.width > 20 and tb.height > 20:
            rect_trim = tb
    except Exception:
        pass

    trim_w_mm = rect_trim.width * MM_PER_PT
    trim_h_mm = rect_trim.height * MM_PER_PT

    rect_total = page.rect
    try:
        bb = page.bleedbox
        if bb and bb.is_valid and bb.width > 20 and bb.height > 20:
            rect_total = bb
    except Exception:
        pass

    total_w_mm = rect_total.width * MM_PER_PT
    total_h_mm = rect_total.height * MM_PER_PT

    return round(trim_w_mm, 2), round(trim_h_mm, 2), round(total_w_mm, 2), round(total_h_mm, 2)


def calculate_imposition_plan(
    pdf_path: str | Path,
    sheet_size: str = "SRA3",
    orientation: str = "auto",  # "auto", "landscape", "portrait"
    mode: str = "step_and_repeat",  # "step_and_repeat", "booklet", "2up", "4up"
    gap_mm: float = 4.0,  # Calle intermedia entre poses
    bleed_mm: float = 2.0,  # Sangrado por pose en la imposición
    sheet_margin_mm: float = 10.0,  # Margen perimetral para pinza de máquina y marcas
    user_cols: Optional[int] = None,
    user_rows: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Calcula el plan geométrico de imposición y aprovechamiento del pliego.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    doc = pymupdf.open(str(pdf_path))
    total_doc_pages = len(doc)
    if total_doc_pages == 0:
        doc.close()
        raise ValueError("El documento PDF no contiene páginas.")

    p0 = doc[0]
    trim_w_mm, trim_h_mm, src_total_w_mm, src_total_h_mm = _get_page_boxes_mm(p0)
    doc.close()

    base_sheet = STANDARD_SHEET_SIZES_MM.get(sheet_size.upper(), STANDARD_SHEET_SIZES_MM["SRA3"])
    sheet_short_mm, sheet_long_mm = min(base_sheet), max(base_sheet)

    # 1. PLAN MODO CUADERNILLO (BOOKLET SADDLE-STITCH)
    if mode == "booklet":
        # En cuadernillo, 2 páginas van por pliego apaisado
        sheet_w_mm = sheet_long_mm
        sheet_h_mm = sheet_short_mm
        # Ajustar dimensiones de escala 100%
        # Comprobar si 2 páginas caben en el pliego
        avail_w = sheet_w_mm - 2 * sheet_margin_mm
        avail_h = sheet_h_mm - 2 * sheet_margin_mm
        fits_normal = (trim_w_mm * 2 <= avail_w and trim_h_mm <= avail_h)

        padded_pages = total_doc_pages
        remainder = padded_pages % 4
        if remainder != 0:
            padded_pages += (4 - remainder)

        sheets_needed = padded_pages // 4
        eff = round(((trim_w_mm * 2 * trim_h_mm) / (sheet_w_mm * sheet_h_mm)) * 100, 1)

        return {
            "mode": "booklet",
            "sheet_size": sheet_size.upper(),
            "sheet_dimensions_mm": [sheet_w_mm, sheet_h_mm],
            "orientation": "landscape",
            "original_pages": total_doc_pages,
            "padded_pages": padded_pages,
            "sheets_needed": sheets_needed,
            "pages_per_sheet_side": 2,
            "pose_size_mm": [trim_w_mm, trim_h_mm],
            "grid": {"cols": 2, "rows": 1, "total_poses": 2},
            "rotated_90": False,
            "gap_mm": 0.0,
            "bleed_mm": bleed_mm,
            "sheet_margin_mm": sheet_margin_mm,
            "efficiency_percent": eff,
            "fits": fits_normal,
            "warning": None if fits_normal else "El formato de página excede el tamaño del pliego seleccionado para cuadernillo."
        }

    # 2. PLAN MODO PASO Y REPETICIÓN (STEP & REPEAT / N-UP)
    # Probar orientaciones de pliego y rotación de poses para maximizar aprovechamiento
    best_option: Optional[Dict[str, Any]] = None
    best_poses = -1
    best_eff = -1.0

    orientations_to_test = ["landscape", "portrait"] if orientation == "auto" else [orientation.lower()]

    for s_orient in orientations_to_test:
        if s_orient == "landscape":
            s_w, s_h = sheet_long_mm, sheet_short_mm
        else:
            s_w, s_h = sheet_short_mm, sheet_long_mm

        avail_w = s_w - 2 * sheet_margin_mm
        avail_h = s_h - 2 * sheet_margin_mm

        # Variantes de rotación de la pose
        pose_variants = [
            {"rot": False, "w": trim_w_mm, "h": trim_h_mm},
            {"rot": True, "w": trim_h_mm, "h": trim_w_mm},
        ]

        for pv in pose_variants:
            pw, ph = pv["w"], pv["h"]
            if pw <= 0 or ph <= 0:
                continue

            if user_cols and user_rows:
                c = user_cols
                r = user_rows
                req_w = c * pw + (c - 1) * gap_mm
                req_h = r * ph + (r - 1) * gap_mm
                if req_w > avail_w or req_h > avail_h:
                    continue
            else:
                c = int((avail_w + gap_mm) // (pw + gap_mm))
                r = int((avail_h + gap_mm) // (ph + gap_mm))

            poses = c * r
            if poses <= 0:
                continue

            used_area = poses * pw * ph
            sheet_area = s_w * s_h
            eff = round((used_area / sheet_area) * 100, 1)

            if poses > best_poses or (poses == best_poses and eff > best_eff):
                best_poses = poses
                best_eff = eff
                best_option = {
                    "mode": mode,
                    "sheet_size": sheet_size.upper(),
                    "sheet_dimensions_mm": [s_w, s_h],
                    "orientation": s_orient,
                    "original_pages": total_doc_pages,
                    "pose_size_mm": [trim_w_mm, trim_h_mm],
                    "grid": {"cols": c, "rows": r, "total_poses": poses},
                    "rotated_90": pv["rot"],
                    "effective_pose_size_mm": [pw, ph],
                    "gap_mm": gap_mm,
                    "bleed_mm": bleed_mm,
                    "sheet_margin_mm": sheet_margin_mm,
                    "efficiency_percent": eff,
                    "fits": True,
                    "warning": None
                }

    if not best_option:
        # Fallback si el diseño es más grande que el pliego
        s_w, s_h = sheet_long_mm, sheet_short_mm
        return {
            "mode": mode,
            "sheet_size": sheet_size.upper(),
            "sheet_dimensions_mm": [s_w, s_h],
            "orientation": "landscape",
            "original_pages": total_doc_pages,
            "pose_size_mm": [trim_w_mm, trim_h_mm],
            "grid": {"cols": 1, "rows": 1, "total_poses": 1},
            "rotated_90": False,
            "effective_pose_size_mm": [trim_w_mm, trim_h_mm],
            "gap_mm": gap_mm,
            "bleed_mm": bleed_mm,
            "sheet_margin_mm": sheet_margin_mm,
            "efficiency_percent": round(((trim_w_mm * trim_h_mm) / (s_w * s_h)) * 100, 1),
            "fits": False,
            "warning": "El documento excede el área útil del pliego (incluyendo márgenes de pinza)."
        }

    return best_option


def _draw_registration_cross(page: pymupdf.Page, cx: float, cy: float, radius: float = 6.0):
    """Dibuja una cruz de registro circular estilo prepress en coordenadas (cx, cy)."""
    shape = page.new_shape()
    shape.draw_circle(pymupdf.Point(cx, cy), radius)
    shape.draw_line(pymupdf.Point(cx - radius - 3.5, cy), pymupdf.Point(cx + radius + 3.5, cy))
    shape.draw_line(pymupdf.Point(cx, cy - radius - 3.5), pymupdf.Point(cx, cy + radius + 3.5))
    shape.finish(color=(0, 0, 0), width=0.45)
    shape.commit()


def _draw_cmyk_color_strip(page: pymupdf.Page, x_start: float, y_top: float, patch_w: float = 14.0, patch_h: float = 8.0):
    """Dibuja una tira de control densitométrico CMYK (C, M, Y, K al 100% y 50%)."""
    colors = [
        (0.0, 0.65, 0.90),      # Cyan 100%
        (0.5, 0.82, 0.95),      # Cyan 50%
        (0.85, 0.05, 0.45),     # Magenta 100%
        (0.92, 0.52, 0.72),     # Magenta 50%
        (0.98, 0.85, 0.05),     # Yellow 100%
        (0.99, 0.92, 0.52),     # Yellow 50%
        (0.10, 0.10, 0.10),     # Black 100%
        (0.55, 0.55, 0.55),     # Black 50%
    ]
    cur_x = x_start
    shape = page.new_shape()
    for col in colors:
        shape.draw_rect(pymupdf.Rect(cur_x, y_top, cur_x + patch_w, y_top + patch_h))
        shape.finish(fill=col, color=(0.4, 0.4, 0.4), width=0.3)
        cur_x += patch_w + 1.5
    shape.commit()


def generate_imposed_pdf(
    pdf_path: str | Path,
    output_path: str | Path,
    sheet_size: str = "SRA3",
    orientation: str = "auto",
    mode: str = "step_and_repeat",
    gap_mm: float = 4.0,
    bleed_mm: float = 2.0,
    sheet_margin_mm: float = 10.0,
    add_marks: bool = True,
    add_reg_crosses: bool = True,
    add_color_bar: bool = True,
    add_slug: bool = True,
    user_cols: Optional[int] = None,
    user_rows: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Genera el archivo PDF impuesto en pliego de máquina listo para ripeo y CTP/Digital.
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)

    plan = calculate_imposition_plan(
        pdf_path=pdf_path,
        sheet_size=sheet_size,
        orientation=orientation,
        mode=mode,
        gap_mm=gap_mm,
        bleed_mm=bleed_mm,
        sheet_margin_mm=sheet_margin_mm,
        user_cols=user_cols,
        user_rows=user_rows,
    )

    src_doc = pymupdf.open(str(pdf_path))
    out_doc = pymupdf.open()

    sheet_w_mm, sheet_h_mm = plan["sheet_dimensions_mm"]
    sheet_w_pt = sheet_w_mm * PT_PER_MM
    sheet_h_pt = sheet_h_mm * PT_PER_MM

    # =========================================================================
    # 1. GENERACIÓN: MODO CUADERNILLO GRAPADO (SADDLE-STITCH BOOKLET)
    # =========================================================================
    if mode == "booklet":
        total_p = plan["original_pages"]
        padded_p = plan["padded_pages"]
        sheets_needed = plan["sheets_needed"]

        pw_pt = plan["pose_size_mm"][0] * PT_PER_MM
        ph_pt = plan["pose_size_mm"][1] * PT_PER_MM

        # Centrar el díptico en el pliego
        total_w_pt = pw_pt * 2
        total_h_pt = ph_pt
        x_start = (sheet_w_pt - total_w_pt) / 2.0
        y_start = (sheet_h_pt - total_h_pt) / 2.0

        for k in range(sheets_needed):
            # Lado Frontal del Pliego k
            p_front_left_idx = (padded_p - 1) - (2 * k)
            p_front_right_idx = 2 * k

            sheet_front = out_doc.new_page(width=sheet_w_pt, height=sheet_h_pt)

            rect_fl = pymupdf.Rect(x_start, y_start, x_start + pw_pt, y_start + ph_pt)
            rect_fr = pymupdf.Rect(x_start + pw_pt, y_start, x_start + 2 * pw_pt, y_start + ph_pt)

            if p_front_left_idx < total_p:
                sheet_front.show_pdf_page(rect_fl, src_doc, p_front_left_idx)
            if p_front_right_idx < total_p:
                sheet_front.show_pdf_page(rect_fr, src_doc, p_front_right_idx)

            # Marcas y slug en cara frontal
            _decorate_sheet(
                sheet=sheet_front,
                sheet_w_pt=sheet_w_pt,
                sheet_h_pt=sheet_h_pt,
                x_start=x_start,
                y_start=y_start,
                cols=2,
                rows=1,
                pw_pt=pw_pt,
                ph_pt=ph_pt,
                gap_pt=0.0,
                add_marks=add_marks,
                add_reg_crosses=add_reg_crosses,
                add_color_bar=add_color_bar,
                add_slug=add_slug,
                slug_text=f"IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII · Cuadernillo · Pliego {k+1}/{sheets_needed} [Cara A] · Páginas [{p_front_left_idx+1} + {p_front_right_idx+1}]",
                is_booklet=True,
            )

            # Lado Reverso del Pliego k
            p_back_left_idx = 2 * k + 1
            p_back_right_idx = (padded_p - 1) - (2 * k + 1)

            sheet_back = out_doc.new_page(width=sheet_w_pt, height=sheet_h_pt)

            rect_bl = pymupdf.Rect(x_start, y_start, x_start + pw_pt, y_start + ph_pt)
            rect_br = pymupdf.Rect(x_start + pw_pt, y_start, x_start + 2 * pw_pt, y_start + ph_pt)

            if p_back_left_idx < total_p:
                sheet_back.show_pdf_page(rect_bl, src_doc, p_back_left_idx)
            if p_back_right_idx < total_p:
                sheet_back.show_pdf_page(rect_br, src_doc, p_back_right_idx)

            _decorate_sheet(
                sheet=sheet_back,
                sheet_w_pt=sheet_w_pt,
                sheet_h_pt=sheet_h_pt,
                x_start=x_start,
                y_start=y_start,
                cols=2,
                rows=1,
                pw_pt=pw_pt,
                ph_pt=ph_pt,
                gap_pt=0.0,
                add_marks=add_marks,
                add_reg_crosses=add_reg_crosses,
                add_color_bar=add_color_bar,
                add_slug=add_slug,
                slug_text=f"IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII · Cuadernillo · Pliego {k+1}/{sheets_needed} [Cara B] · Páginas [{p_back_left_idx+1} + {p_back_right_idx+1}]",
                is_booklet=True,
            )

    # =========================================================================
    # 2. GENERACIÓN: PASO Y REPETICIÓN (STEP & REPEAT / N-UP)
    # =========================================================================
    else:
        cols = plan["grid"]["cols"]
        rows = plan["grid"]["rows"]
        total_poses_per_sheet = cols * rows
        pw_pt = plan["effective_pose_size_mm"][0] * PT_PER_MM
        ph_pt = plan["effective_pose_size_mm"][1] * PT_PER_MM
        gap_pt = plan["gap_mm"] * PT_PER_MM
        rot = plan.get("rotated_90", False)

        total_grid_w_pt = cols * pw_pt + (cols - 1) * gap_pt
        total_grid_h_pt = rows * ph_pt + (rows - 1) * gap_pt

        x_start = (sheet_w_pt - total_grid_w_pt) / 2.0
        y_start = (sheet_h_pt - total_grid_h_pt) / 2.0

        # Para PDFs de 1 página (ej. flyers o tarjetas), se repite la misma página
        # Para PDFs multipágina (ej. 2-up o 4-up de varias páginas), se van colocando sucesivamente
        num_src_pages = len(src_doc)
        if num_src_pages == 1:
            # Pliego único con la misma página repetida en todas las poses
            sheet = out_doc.new_page(width=sheet_w_pt, height=sheet_h_pt)
            for r in range(rows):
                for c in range(cols):
                    px = x_start + c * (pw_pt + gap_pt)
                    py = y_start + r * (ph_pt + gap_pt)
                    rect_pose = pymupdf.Rect(px, py, px + pw_pt, py + ph_pt)
                    if rot:
                        sheet.show_pdf_page(rect_pose, src_doc, 0, rotate=90)
                    else:
                        sheet.show_pdf_page(rect_pose, src_doc, 0)

            _decorate_sheet(
                sheet=sheet,
                sheet_w_pt=sheet_w_pt,
                sheet_h_pt=sheet_h_pt,
                x_start=x_start,
                y_start=y_start,
                cols=cols,
                rows=rows,
                pw_pt=pw_pt,
                ph_pt=ph_pt,
                gap_pt=gap_pt,
                add_marks=add_marks,
                add_reg_crosses=add_reg_crosses,
                add_color_bar=add_color_bar,
                add_slug=add_slug,
                slug_text=f"IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII · {pdf_path.name} · {sheet_size.upper()} ({sheet_w_mm:.0f}×{sheet_h_mm:.0f} mm) · {total_poses_per_sheet} poses ({cols}×{rows}) · Escala 100%",
                is_booklet=False,
            )
        else:
            # Documento multipágina: calcular pliegos necesarios
            sheets_count = math.ceil(num_src_pages / total_poses_per_sheet)
            page_idx = 0
            for sh_idx in range(sheets_count):
                sheet = out_doc.new_page(width=sheet_w_pt, height=sheet_h_pt)
                for r in range(rows):
                    for c in range(cols):
                        if page_idx < num_src_pages:
                            px = x_start + c * (pw_pt + gap_pt)
                            py = y_start + r * (ph_pt + gap_pt)
                            rect_pose = pymupdf.Rect(px, py, px + pw_pt, py + ph_pt)
                            if rot:
                                sheet.show_pdf_page(rect_pose, src_doc, page_idx, rotate=90)
                            else:
                                sheet.show_pdf_page(rect_pose, src_doc, page_idx)
                            page_idx += 1

                _decorate_sheet(
                    sheet=sheet,
                    sheet_w_pt=sheet_w_pt,
                    sheet_h_pt=sheet_h_pt,
                    x_start=x_start,
                    y_start=y_start,
                    cols=cols,
                    rows=rows,
                    pw_pt=pw_pt,
                    ph_pt=ph_pt,
                    gap_pt=gap_pt,
                    add_marks=add_marks,
                    add_reg_crosses=add_reg_crosses,
                    add_color_bar=add_color_bar,
                    add_slug=add_slug,
                    slug_text=f"IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII · {pdf_path.name} · Pliego {sh_idx+1}/{sheets_count} · {total_poses_per_sheet} poses/pliego",
                    is_booklet=False,
                )

    out_doc.save(str(output_path), deflate=True)
    out_pages = len(out_doc)
    out_doc.close()
    src_doc.close()

    result = dict(plan)
    result["status"] = "success"
    result["output_pdf_path"] = str(output_path)
    result["sheets_generated"] = out_pages
    result["file_size_kb"] = round(output_path.stat().st_size / 1024, 1) if output_path.exists() else 0
    return result


def _decorate_sheet(
    sheet: pymupdf.Page,
    sheet_w_pt: float,
    sheet_h_pt: float,
    x_start: float,
    y_start: float,
    cols: int,
    rows: int,
    pw_pt: float,
    ph_pt: float,
    gap_pt: float,
    add_marks: bool,
    add_reg_crosses: bool,
    add_color_bar: bool,
    add_slug: bool,
    slug_text: str,
    is_booklet: bool = False,
):
    """
    Inyecta marcas de corte vectoriales, cruces de registro, plegado, tiras densitométricas y slug.
    """
    shape = sheet.new_shape()
    mark_len = 5.0 * PT_PER_MM  # 5 mm
    mark_offset = 2.0 * PT_PER_MM  # 2 mm

    # 1. Marcas de corte perimetrales e intermedias
    if add_marks:
        # Cortes verticales en X
        x_positions = []
        for c in range(cols):
            x_left = x_start + c * (pw_pt + gap_pt)
            x_right = x_left + pw_pt
            x_positions.extend([x_left, x_right])

        # Cortes horizontales en Y
        y_positions = []
        for r in range(rows):
            y_top = y_start + r * (ph_pt + gap_pt)
            y_bottom = y_top + ph_pt
            y_positions.extend([y_top, y_bottom])

        # Dibujar marcas verticales en el borde superior e inferior
        y_min = y_start
        y_max = y_start + rows * ph_pt + (rows - 1) * gap_pt
        for xp in x_positions:
            # Arriba
            shape.draw_line(pymupdf.Point(xp, y_min - mark_offset), pymupdf.Point(xp, y_min - mark_offset - mark_len))
            # Abajo
            shape.draw_line(pymupdf.Point(xp, y_max + mark_offset), pymupdf.Point(xp, y_max + mark_offset + mark_len))

        # Dibujar marcas horizontales en el borde izquierdo y derecho
        x_min = x_start
        x_max = x_start + cols * pw_pt + (cols - 1) * gap_pt
        for yp in y_positions:
            # Izquierda
            shape.draw_line(pymupdf.Point(x_min - mark_offset, yp), pymupdf.Point(x_min - mark_offset - mark_len, yp))
            # Derecha
            shape.draw_line(pymupdf.Point(x_max + mark_offset, yp), pymupdf.Point(x_max + mark_offset + mark_len, yp))

        # Si hay calles intermedias (gap > 0), dibujar marcas de corte entre calles
        if gap_pt > 0:
            for c in range(cols - 1):
                x_gutter_l = x_start + (c + 1) * pw_pt + c * gap_pt
                x_gutter_r = x_gutter_l + gap_pt
                # Marcas en calles superiores e inferiores ya están en x_positions
                pass

        # Si es cuadernillo grapado, dibujar marca de plegado (fold mark punteada) en el lomo central
        if is_booklet and cols == 2:
            x_spine = x_start + pw_pt
            shape.draw_line(pymupdf.Point(x_spine, y_min - mark_offset), pymupdf.Point(x_spine, y_min - mark_offset - mark_len))
            shape.draw_line(pymupdf.Point(x_spine, y_max + mark_offset), pymupdf.Point(x_spine, y_max + mark_offset + mark_len))

    shape.finish(color=(0, 0, 0), width=0.35)
    shape.commit()

    # 2. Cruces de registro circulares
    if add_reg_crosses:
        cx_mid = sheet_w_pt / 2.0
        cy_mid = sheet_h_pt / 2.0
        r_cross = 5.0
        reg_margin = 6.0 * PT_PER_MM
        # 4 cruces en los 4 costados
        _draw_registration_cross(sheet, cx_mid, reg_margin, r_cross)
        _draw_registration_cross(sheet, cx_mid, sheet_h_pt - reg_margin, r_cross)
        _draw_registration_cross(sheet, reg_margin, cy_mid, r_cross)
        _draw_registration_cross(sheet, sheet_w_pt - reg_margin, cy_mid, r_cross)

    # 3. Tiras de control densitométrico CMYK
    if add_color_bar:
        # Colocar tira densitométrica centrada en la parte superior
        bar_w = 8 * 15.0
        bar_x = (sheet_w_pt - bar_w) / 2.0 + 35.0
        bar_y = 5.0 * PT_PER_MM
        _draw_cmyk_color_strip(sheet, bar_x, bar_y, patch_w=12.0, patch_h=6.0)

    # 4. Información técnica del pliego (Slug)
    if add_slug:
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        full_slug = f"{slug_text} · {now_str}"
        slug_y = sheet_h_pt - (4.5 * PT_PER_MM)
        sheet.insert_text(
            pymupdf.Point(12 * PT_PER_MM, slug_y),
            full_slug,
            fontsize=6.5,
            fontname="helv",
            color=(0.25, 0.25, 0.25),
        )


def render_imposition_preview_image(
    pdf_path: str | Path,
    sheet_size: str = "SRA3",
    orientation: str = "auto",
    mode: str = "step_and_repeat",
    gap_mm: float = 4.0,
    bleed_mm: float = 2.0,
    sheet_margin_mm: float = 10.0,
    dpi: int = 80,
    user_cols: Optional[int] = None,
    user_rows: Optional[int] = None,
) -> bytes:
    """
    Renderiza una previsualización en JPEG del pliego impuesto generado en memoria.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(suffix="_imp_preview.pdf", delete=False) as tf:
        temp_out = Path(tf.name)

    try:
        generate_imposed_pdf(
            pdf_path=pdf_path,
            output_path=temp_out,
            sheet_size=sheet_size,
            orientation=orientation,
            mode=mode,
            gap_mm=gap_mm,
            bleed_mm=bleed_mm,
            sheet_margin_mm=sheet_margin_mm,
            add_marks=True,
            add_reg_crosses=True,
            add_color_bar=True,
            add_slug=True,
            user_cols=user_cols,
            user_rows=user_rows,
        )

        doc = pymupdf.open(str(temp_out))
        page0 = doc[0]
        zoom = dpi / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page0.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes(output="jpeg")
        doc.close()
        return img_bytes
    finally:
        if temp_out.exists():
            temp_out.unlink()

