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

Gestión de los 3 estados de PDF de entrada:
  - CASO A: PDF sin sangre (MediaBox ≈ TrimBox): el motor añade las marcas exteriores.
            Aviso: sin sangre en el original → riesgo de borde blanco tras guillotina.
  - CASO B: PDF con sangre pero sin marcas (BleedBox > TrimBox, típicamente +3mm):
            Correcto: se renderiza la BleedBox completa en la pose, y las marcas de corte
            se dibujan en la posición exacta del TrimBox (inset por source_bleed_mm desde el borde).
  - CASO C: PDF con marcas de corte ya incrustadas en la MediaBox (slug area):
            Se detecta (MediaBox >> BleedBox en ≥8mm), se extrae solo el TrimBox vía clip,
            y se avisa de que el PDF ya tenía marcas de impresora. No se duplican marcas.
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
    "SRA3": (320.0, 450.0),    # Estándar imprenta digital (Ancho x Alto en vertical)
    "500X700": (500.0, 700.0), # Pliego 500 × 700 mm (B2 Offset comercial)
    "50X70": (500.0, 700.0),   # Alias 50 × 70 cm
    "B2": (500.0, 700.0),      # Formato B2 Offset
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "B3": (350.0, 500.0),      # Medio pliego offset pequeño formato
    "SRA4": (225.0, 320.0),
}

# Umbral mínimo para considerar que hay sangre real (≥1 mm de diferencia)
_BLEED_THRESHOLD_MM = 1.0
# Umbral para detectar marcas incrustadas en MediaBox (zona de slug/marcas ≥8mm extra)
_EMBEDDED_MARKS_THRESHOLD_MM = 7.0


def _get_page_boxes_mm(page: pymupdf.Page) -> Dict[str, Any]:
    """
    Obtiene las dimensiones y estado de boxes de la página en milímetros.

    Detecta automáticamente el estado del PDF:
      - 'no_bleed':        MediaBox ≈ TrimBox, sin sangre.
      - 'has_bleed':       BleedBox > TrimBox en ≥1mm → sangre real sin marcas.
      - 'embedded_marks':  MediaBox >> BleedBox (o TrimBox) en ≥8mm → marcas de taller incrustadas.

    Devuelve un dict con:
      trim_w_mm, trim_h_mm        : dimensiones netas de corte (TrimBox)
      bleed_w_mm, bleed_h_mm      : dimensiones con sangre (BleedBox o MediaBox)
      media_w_mm, media_h_mm      : MediaBox completo (puede incluir slug)
      source_bleed_mm             : sangre detectada en mm por lado (promedio)
      pdf_state                   : 'no_bleed' | 'has_bleed' | 'embedded_marks'
      clip_rect_pt                : pymupdf.Rect del TrimBox en pt, para clipping
    """
    # --- MediaBox (siempre disponible) ---
    media_rect = page.rect
    media_w_mm = media_rect.width * MM_PER_PT
    media_h_mm = media_rect.height * MM_PER_PT

    # --- TrimBox ---
    trim_rect = page.rect  # fallback
    try:
        tb = page.trimbox
        if tb and tb.is_valid and tb.width > 20 and tb.height > 20:
            trim_rect = tb
    except Exception:
        pass
    trim_w_mm = trim_rect.width * MM_PER_PT
    trim_h_mm = trim_rect.height * MM_PER_PT

    # --- BleedBox ---
    bleed_rect = trim_rect  # fallback al TrimBox si no hay BleedBox
    try:
        bb = page.bleedbox
        if bb and bb.is_valid and bb.width > 20 and bb.height > 20:
            bleed_rect = bb
    except Exception:
        pass
    bleed_w_mm = bleed_rect.width * MM_PER_PT
    bleed_h_mm = bleed_rect.height * MM_PER_PT

    # --- Sangre detectada (diferencia BleedBox - TrimBox) ---
    bleed_diff_w = (bleed_w_mm - trim_w_mm) / 2.0
    bleed_diff_h = (bleed_h_mm - trim_h_mm) / 2.0
    source_bleed_mm = round(max(0.0, (bleed_diff_w + bleed_diff_h) / 2.0), 2)

    # --- Slug/Marks extra (diferencia MediaBox - BleedBox) ---
    slug_extra_w = (media_w_mm - bleed_w_mm) / 2.0
    slug_extra_h = (media_h_mm - bleed_h_mm) / 2.0
    slug_extra_mm = max(slug_extra_w, slug_extra_h)

    # --- Clasificación del estado ---
    if slug_extra_mm >= _EMBEDDED_MARKS_THRESHOLD_MM:
        pdf_state = "embedded_marks"
    elif source_bleed_mm >= _BLEED_THRESHOLD_MM:
        pdf_state = "has_bleed"
    else:
        pdf_state = "no_bleed"

    return {
        "trim_w_mm": round(trim_w_mm, 2),
        "trim_h_mm": round(trim_h_mm, 2),
        "bleed_w_mm": round(bleed_w_mm, 2),
        "bleed_h_mm": round(bleed_h_mm, 2),
        "media_w_mm": round(media_w_mm, 2),
        "media_h_mm": round(media_h_mm, 2),
        "source_bleed_mm": source_bleed_mm,
        "pdf_state": pdf_state,
        "clip_rect_pt": trim_rect,  # TrimBox en puntos (para clip en show_pdf_page)
    }


def calculate_imposition_plan(
    pdf_path: str | Path,
    sheet_size: str = "SRA3",
    orientation: str = "auto",  # "auto", "landscape", "portrait"
    mode: str = "step_and_repeat",  # "step_and_repeat", "booklet", "2up", "4up"
    gap_mm: float = 4.0,  # Calle intermedia entre poses
    bleed_mm: float = 2.0,  # Sangrado por pose en la imposición (mínimo de seguridad)
    sheet_margin_mm: float = 10.0,  # Margen perimetral para pinza de máquina y marcas
    user_cols: Optional[int] = None,
    user_rows: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Calcula el plan geométrico de imposición y aprovechamiento del pliego.

    Detecta automáticamente el estado del PDF de origen (sin sangre / con sangre / con marcas
    incrustadas) y adapta el plan geométrico en consecuencia.
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
    boxes = _get_page_boxes_mm(p0)
    doc.close()

    trim_w_mm = boxes["trim_w_mm"]
    trim_h_mm = boxes["trim_h_mm"]
    bleed_w_mm = boxes["bleed_w_mm"]
    bleed_h_mm = boxes["bleed_h_mm"]
    source_bleed_mm = boxes["source_bleed_mm"]
    pdf_state = boxes["pdf_state"]

    # La pose "efectiva" incluye la sangre cuando el PDF la tiene nativamente,
    # para que el contenido sangrado se renderice completo en el pliego.
    if pdf_state == "has_bleed":
        pose_base_w = bleed_w_mm
        pose_base_h = bleed_h_mm
    else:
        # 'no_bleed' o 'embedded_marks': usamos TrimBox (en embedded_marks haremos clip)
        pose_base_w = trim_w_mm
        pose_base_h = trim_h_mm

    base_sheet = STANDARD_SHEET_SIZES_MM.get(sheet_size.upper(), STANDARD_SHEET_SIZES_MM["SRA3"])
    sheet_short_mm, sheet_long_mm = min(base_sheet), max(base_sheet)

    # Avisos pedagógicos para el operario
    warnings_list: List[str] = []
    if pdf_state == "no_bleed":
        warnings_list.append(
            "⚠ El PDF no tiene sangre. Se recomienda aplicar 'Mirror Bleed' antes de imponer "
            "para evitar bordes blancos tras la guillotina."
        )
    elif pdf_state == "embedded_marks":
        warnings_list.append(
            "ℹ El PDF ya contiene marcas de corte incrustadas (zona de slug detectada). "
            "El motor extraerá solo el TrimBox para evitar marcas duplicadas."
        )
    elif pdf_state == "has_bleed":
        warnings_list.append(
            f"✓ Sangrado de {source_bleed_mm:.1f} mm detectado. Las poses incluirán la sangre "
            "completa y las marcas de corte se situarán en la línea de TrimBox."
        )

    # =========================================================================
    # 1. PLAN MODO CUADERNILLO (BOOKLET SADDLE-STITCH)
    # =========================================================================
    if mode == "booklet":
        sheet_w_mm = sheet_long_mm
        sheet_h_mm = sheet_short_mm
        avail_w = sheet_w_mm - 2 * sheet_margin_mm
        avail_h = sheet_h_mm - 2 * sheet_margin_mm
        fits_normal = (trim_w_mm * 2 <= avail_w and trim_h_mm <= avail_h)

        padded_pages = total_doc_pages
        remainder = padded_pages % 4
        if remainder != 0:
            padded_pages += (4 - remainder)

        sheets_needed = padded_pages // 4
        eff = round(((trim_w_mm * 2 * trim_h_mm) / (sheet_w_mm * sheet_h_mm)) * 100, 1)

        warning_text = None if fits_normal else "El formato de página excede el tamaño del pliego seleccionado para cuadernillo."

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
            "pose_with_bleed_mm": [pose_base_w, pose_base_h],
            "grid": {"cols": 2, "rows": 1, "total_poses": 2},
            "rotated_90": False,
            "gap_mm": 0.0,
            "bleed_mm": bleed_mm,
            "source_bleed_mm": source_bleed_mm,
            "pdf_state": pdf_state,
            "sheet_margin_mm": sheet_margin_mm,
            "efficiency_percent": eff,
            "fits": fits_normal,
            "warning": warning_text,
            "pdf_warnings": warnings_list,
        }

    # =========================================================================
    # 2. PLAN MODO PASO Y REPETICIÓN (STEP & REPEAT / N-UP)
    # El tamaño de celda para calcular el grid usa pose_base (con sangre si la hay)
    # para que las poses no se solapen.
    # =========================================================================
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

        # Variantes de rotación de la pose (usando el tamaño con sangre si la hay)
        pose_variants = [
            {"rot": False, "w": pose_base_w, "h": pose_base_h},
            {"rot": True,  "w": pose_base_h, "h": pose_base_w},
        ]

        for pv in pose_variants:
            pw, ph = pv["w"], pv["h"]
            if pw <= 0 or ph <= 0:
                continue

            # El gap entre poses no necesita duplicar la sangre porque la sangre
            # de poses adyacentes se solaparía igualmente (como en prepress real).
            # Usamos gap_mm como calle de corte entre líneas de TrimBox.
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

            # Eficiencia sobre TrimBox (el área útil real)
            used_area = poses * trim_w_mm * trim_h_mm
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
                    "pose_with_bleed_mm": [pose_base_w, pose_base_h],
                    "grid": {"cols": c, "rows": r, "total_poses": poses},
                    "rotated_90": pv["rot"],
                    "effective_pose_size_mm": [pw, ph],  # Tamaño de celda (incluye sangre si la hay)
                    "gap_mm": gap_mm,
                    "bleed_mm": bleed_mm,
                    "source_bleed_mm": source_bleed_mm,
                    "pdf_state": pdf_state,
                    "sheet_margin_mm": sheet_margin_mm,
                    "efficiency_percent": eff,
                    "fits": True,
                    "warning": None,
                    "pdf_warnings": warnings_list,
                }

    if not best_option:
        s_w, s_h = sheet_long_mm, sheet_short_mm
        return {
            "mode": mode,
            "sheet_size": sheet_size.upper(),
            "sheet_dimensions_mm": [s_w, s_h],
            "orientation": "landscape",
            "original_pages": total_doc_pages,
            "pose_size_mm": [trim_w_mm, trim_h_mm],
            "pose_with_bleed_mm": [pose_base_w, pose_base_h],
            "grid": {"cols": 1, "rows": 1, "total_poses": 1},
            "rotated_90": False,
            "effective_pose_size_mm": [trim_w_mm, trim_h_mm],
            "gap_mm": gap_mm,
            "bleed_mm": bleed_mm,
            "source_bleed_mm": source_bleed_mm,
            "pdf_state": pdf_state,
            "sheet_margin_mm": sheet_margin_mm,
            "efficiency_percent": round(((trim_w_mm * trim_h_mm) / (s_w * s_h)) * 100, 1),
            "fits": False,
            "warning": "El documento excede el área útil del pliego (incluyendo márgenes de pinza).",
            "pdf_warnings": warnings_list,
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


def _draw_cmyk_color_strip(
    page: pymupdf.Page,
    x_start: float,
    y_top: float,
    patch_w: float = 6.0,
    patch_h: float = 6.0,
    max_x: Optional[float] = None,
    skip_zones: Optional[List[Tuple[float, float]]] = None
):
    """Dibuja la tira de control FOGRA / ISO 12647-2 (repetida a todo lo ancho si se define max_x)."""
    try:
        from control_strip_engine import draw_repeated_fogra_strip, draw_fogra_control_strip
        if max_x is not None and max_x > x_start:
            draw_repeated_fogra_strip(
                page,
                x_start=x_start,
                y=y_top - 1.0,
                max_x=max_x,
                swatch_w=patch_w,
                swatch_h=patch_h,
                show_labels=True,
                skip_zones=skip_zones
            )
        else:
            draw_fogra_control_strip(page, x_start, y_top - 1.0, swatch_w=patch_w, swatch_h=patch_h, show_labels=True)
    except Exception:
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
        limit_x = max_x if max_x is not None else (x_start + len(colors) * (patch_w + 1.5))
        shape = page.new_shape()
        while cur_x + patch_w <= limit_x:
            for col in colors:
                if cur_x + patch_w > limit_x:
                    break
                shape.draw_rect(pymupdf.Rect(cur_x, y_top, cur_x + patch_w, y_top + patch_h))
                shape.finish(fill=col, color=(0.4, 0.4, 0.4), width=0.3)
                cur_x += patch_w + 1.5
            if max_x is None:
                break
        shape.commit()


def _place_pose(
    sheet: pymupdf.Page,
    src_doc: pymupdf.Document,
    page_idx: int,
    rect_pose: pymupdf.Rect,
    rotate: int,
    pdf_state: str,
    clip_rect_pt: pymupdf.Rect,
):
    """
    Coloca una pose en el pliego, respetando el estado del PDF:
      - 'has_bleed':       Renderiza la BleedBox completa en rect_pose (sangre incluida).
      - 'embedded_marks':  Clipea al TrimBox para excluir las marcas incrustadas.
      - 'no_bleed':        Renderiza sin clip (igual que el comportamiento anterior).
    """
    if pdf_state == "embedded_marks":
        # Clip al TrimBox: descartamos la zona de slug/marcas de la MediaBox
        sheet.show_pdf_page(rect_pose, src_doc, page_idx, rotate=rotate, clip=clip_rect_pt)
    else:
        # 'has_bleed' o 'no_bleed': renderizar el contenido completo en la pose
        sheet.show_pdf_page(rect_pose, src_doc, page_idx, rotate=rotate)


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
    job_id: Optional[str] = None,
    base_url: str = "",
    user_cols: Optional[int] = None,
    user_rows: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Genera el archivo PDF impuesto en pliego de máquina listo para ripeo y CTP/Digital.

    Gestiona correctamente los 3 estados del PDF de origen:
      CASO A (no_bleed):       Poses sin sangre + marcas exteriores + aviso.
      CASO B (has_bleed):      Poses con sangre completa + marcas en posición TrimBox.
      CASO C (embedded_marks): Clip al TrimBox, se elimina la zona de marcas incrustadas.
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

    pdf_state = plan.get("pdf_state", "no_bleed")
    source_bleed_mm = plan.get("source_bleed_mm", 0.0)

    # Obtener clip_rect_pt del PDF real (siempre lo necesitamos para embedded_marks)
    p0 = src_doc[0]
    boxes = _get_page_boxes_mm(p0)
    clip_rect_pt = boxes["clip_rect_pt"]

    # =========================================================================
    # 1. GENERACIÓN: MODO CUADERNILLO GRAPADO (SADDLE-STITCH BOOKLET)
    # =========================================================================
    if mode == "booklet":
        total_p = plan["original_pages"]
        padded_p = plan["padded_pages"]
        sheets_needed = plan["sheets_needed"]

        # En cuadernillo siempre usamos TrimBox (tamaño neto de la página)
        pw_pt = plan["pose_size_mm"][0] * PT_PER_MM
        ph_pt = plan["pose_size_mm"][1] * PT_PER_MM

        total_w_pt = pw_pt * 2
        total_h_pt = ph_pt
        x_start = (sheet_w_pt - total_w_pt) / 2.0
        y_start = (sheet_h_pt - total_h_pt) / 2.0

        for k in range(sheets_needed):
            p_front_left_idx  = (padded_p - 1) - (2 * k)
            p_front_right_idx = 2 * k

            sheet_front = out_doc.new_page(width=sheet_w_pt, height=sheet_h_pt)

            rect_fl = pymupdf.Rect(x_start, y_start, x_start + pw_pt, y_start + ph_pt)
            rect_fr = pymupdf.Rect(x_start + pw_pt, y_start, x_start + 2 * pw_pt, y_start + ph_pt)

            if p_front_left_idx < total_p:
                _place_pose(sheet_front, src_doc, p_front_left_idx, rect_fl, 0, pdf_state, clip_rect_pt)
            if p_front_right_idx < total_p:
                _place_pose(sheet_front, src_doc, p_front_right_idx, rect_fr, 0, pdf_state, clip_rect_pt)

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
                source_bleed_mm=0.0,  # cuadernillo: marks en borde del TrimBox
                add_marks=add_marks,
                add_reg_crosses=add_reg_crosses,
                add_color_bar=add_color_bar,
                add_slug=add_slug,
                slug_text=f"IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII · Cuadernillo · Pliego {k+1}/{sheets_needed} [Cara A] · Páginas [{p_front_left_idx+1} + {p_front_right_idx+1}]",
                is_booklet=True,
                job_id=job_id,
                base_url=base_url,
            )

            # Lado Reverso
            p_back_left_idx  = 2 * k + 1
            p_back_right_idx = (padded_p - 1) - (2 * k + 1)

            sheet_back = out_doc.new_page(width=sheet_w_pt, height=sheet_h_pt)

            rect_bl = pymupdf.Rect(x_start, y_start, x_start + pw_pt, y_start + ph_pt)
            rect_br = pymupdf.Rect(x_start + pw_pt, y_start, x_start + 2 * pw_pt, y_start + ph_pt)

            if p_back_left_idx < total_p:
                _place_pose(sheet_back, src_doc, p_back_left_idx, rect_bl, 0, pdf_state, clip_rect_pt)
            if p_back_right_idx < total_p:
                _place_pose(sheet_back, src_doc, p_back_right_idx, rect_br, 0, pdf_state, clip_rect_pt)

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
                source_bleed_mm=0.0,
                add_marks=add_marks,
                add_reg_crosses=add_reg_crosses,
                add_color_bar=add_color_bar,
                add_slug=add_slug,
                slug_text=f"IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII · Cuadernillo · Pliego {k+1}/{sheets_needed} [Cara B] · Páginas [{p_back_left_idx+1} + {p_back_right_idx+1}]",
                is_booklet=True,
                job_id=job_id,
                base_url=base_url,
            )

    # =========================================================================
    # 2. GENERACIÓN: PASO Y REPETICIÓN (STEP & REPEAT / N-UP)
    # =========================================================================
    else:
        cols = plan["grid"]["cols"]
        rows = plan["grid"]["rows"]
        total_poses_per_sheet = cols * rows
        # effective_pose_size_mm ya incluye la sangre cuando hay 'has_bleed'
        pw_pt = plan["effective_pose_size_mm"][0] * PT_PER_MM
        ph_pt = plan["effective_pose_size_mm"][1] * PT_PER_MM
        gap_pt = plan["gap_mm"] * PT_PER_MM
        rot = plan.get("rotated_90", False)

        total_grid_w_pt = cols * pw_pt + (cols - 1) * gap_pt
        total_grid_h_pt = rows * ph_pt + (rows - 1) * gap_pt

        x_start = (sheet_w_pt - total_grid_w_pt) / 2.0
        y_start = (sheet_h_pt - total_grid_h_pt) / 2.0

        num_src_pages = len(src_doc)
        rotate_val = 90 if rot else 0

        def _fill_sheet_step_repeat(sheet: pymupdf.Page, sh_idx: int, start_page_idx: int) -> int:
            """Rellena un pliego de Paso y Repetición. Devuelve el índice de página actualizado."""
            page_idx_local = start_page_idx
            for r in range(rows):
                for c in range(cols):
                    src_page_idx = page_idx_local if num_src_pages > 1 else 0
                    if num_src_pages > 1 and page_idx_local >= num_src_pages:
                        break
                    px = x_start + c * (pw_pt + gap_pt)
                    py = y_start + r * (ph_pt + gap_pt)
                    rect_pose = pymupdf.Rect(px, py, px + pw_pt, py + ph_pt)
                    _place_pose(sheet, src_doc, src_page_idx, rect_pose, rotate_val, pdf_state, clip_rect_pt)
                    if num_src_pages > 1:
                        page_idx_local += 1
            return page_idx_local

        if num_src_pages == 1:
            sheet = out_doc.new_page(width=sheet_w_pt, height=sheet_h_pt)
            _fill_sheet_step_repeat(sheet, 0, 0)

            pdf_state_label = {
                "no_bleed":       "SIN SANGRE",
                "has_bleed":      f"SANGRE {source_bleed_mm:.1f}mm",
                "embedded_marks": "MARCAS INCRUSTADAS",
            }.get(pdf_state, "")

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
                source_bleed_mm=source_bleed_mm,
                add_marks=add_marks,
                add_reg_crosses=add_reg_crosses,
                add_color_bar=add_color_bar,
                add_slug=add_slug,
                slug_text=(
                    f"IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII · {pdf_path.name} · "
                    f"{sheet_size.upper()} ({sheet_w_mm:.0f}×{sheet_h_mm:.0f} mm) · "
                    f"{total_poses_per_sheet} poses ({cols}×{rows}) · 100% · {pdf_state_label}"
                ),
                is_booklet=False,
                job_id=job_id,
                base_url=base_url,
            )
        else:
            sheets_count = math.ceil(num_src_pages / total_poses_per_sheet)
            page_idx = 0
            for sh_idx in range(sheets_count):
                sheet = out_doc.new_page(width=sheet_w_pt, height=sheet_h_pt)
                page_idx = _fill_sheet_step_repeat(sheet, sh_idx, page_idx)

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
                    source_bleed_mm=source_bleed_mm,
                    add_marks=add_marks,
                    add_reg_crosses=add_reg_crosses,
                    add_color_bar=add_color_bar,
                    add_slug=add_slug,
                    slug_text=f"IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII · {pdf_path.name} · Pliego {sh_idx+1}/{sheets_count} · {total_poses_per_sheet} poses/pliego",
                    is_booklet=False,
                    job_id=job_id,
                    base_url=base_url,
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
    source_bleed_mm: float,
    add_marks: bool,
    add_reg_crosses: bool,
    add_color_bar: bool,
    add_slug: bool,
    slug_text: str,
    is_booklet: bool = False,
    job_id: Optional[str] = None,
    base_url: str = "",
):
    """
    Inyecta marcas de corte vectoriales, cruces de registro, plegado, tiras densitométricas y slug.

    Parámetro clave: source_bleed_mm
      - 0.0  → Las marcas de corte se dibujan en el borde de la pose (modo sin sangre o cuadernillo).
      - >0.0 → Las marcas de corte se desplazan HACIA ADENTRO por source_bleed_mm desde el borde
               de la pose, señalando la línea real de TrimBox (porque la pose incluye la sangre).
    """
    shape_halo = sheet.new_shape()
    shape_mark = sheet.new_shape()
    mark_len = 5.0 * PT_PER_MM   # 5 mm
    mark_offset = 2.0 * PT_PER_MM  # 2 mm gap entre corte y marca
    bleed_pt = source_bleed_mm * PT_PER_MM  # offset inward para TrimBox

    def _draw_mark_line(p1: pymupdf.Point, p2: pymupdf.Point):
        shape_halo.draw_line(p1, p2)
        shape_mark.draw_line(p1, p2)

    # 1. Marcas de corte
    if add_marks:
        # Posiciones de corte X por columna [(x_left, x_right), ...]
        x_cuts = []
        for c in range(cols):
            x_left  = x_start + c * (pw_pt + gap_pt) + bleed_pt
            x_right = x_left + pw_pt - 2 * bleed_pt
            x_cuts.append((x_left, x_right))

        # Posiciones de corte Y por fila [(y_top, y_bottom), ...]
        y_cuts = []
        for r in range(rows):
            y_top    = y_start + r * (ph_pt + gap_pt) + bleed_pt
            y_bottom = y_top + ph_pt - 2 * bleed_pt
            y_cuts.append((y_top, y_bottom))

        all_x = [pos for pair in x_cuts for pos in pair]
        all_y = [pos for pair in y_cuts for pos in pair]

        # Límites de la rejilla
        total_grid_w_calc = cols * pw_pt + (cols - 1) * gap_pt
        total_grid_h_calc = rows * ph_pt + (rows - 1) * gap_pt
        y_min_grid = y_start
        y_max_grid = y_start + total_grid_h_calc
        x_min_grid = x_start
        x_max_grid = x_start + total_grid_w_calc

        # A) Marcas verticales exteriores (borde superior e inferior del pliego)
        for xp in all_x:
            y_top_mark = y_min_grid + bleed_pt - mark_offset
            _draw_mark_line(pymupdf.Point(xp, y_top_mark), pymupdf.Point(xp, y_top_mark - mark_len))
            y_bot_mark = y_max_grid - bleed_pt + mark_offset
            _draw_mark_line(pymupdf.Point(xp, y_bot_mark), pymupdf.Point(xp, y_bot_mark + mark_len))

        # B) Marcas horizontales exteriores (borde izquierdo y derecho del pliego)
        for yp in all_y:
            x_left_mark = x_min_grid + bleed_pt - mark_offset
            _draw_mark_line(pymupdf.Point(x_left_mark, yp), pymupdf.Point(x_left_mark - mark_len, yp))
            x_right_mark = x_max_grid - bleed_pt + mark_offset
            _draw_mark_line(pymupdf.Point(x_right_mark, yp), pymupdf.Point(x_right_mark + mark_len, yp))

        # C) MARCAS INTERNAS VERTICALES (en cada calle horizontal entre filas)
        for r in range(1, rows):
            y_prev_bottom = y_cuts[r-1][1]  # línea de corte inferior de la fila anterior
            y_curr_top    = y_cuts[r][0]    # línea de corte superior de la fila actual
            gutter_h = y_curr_top - y_prev_bottom

            inner_len = min(mark_len, max(2.0 * PT_PER_MM, (gutter_h - 2 * mark_offset) / 2))

            for xp in all_x:
                if gutter_h >= 2 * mark_offset + 2.0:
                    _draw_mark_line(
                        pymupdf.Point(xp, y_prev_bottom + mark_offset),
                        pymupdf.Point(xp, y_prev_bottom + mark_offset + inner_len)
                    )
                    _draw_mark_line(
                        pymupdf.Point(xp, y_curr_top - mark_offset),
                        pymupdf.Point(xp, y_curr_top - mark_offset - inner_len)
                    )
                else:
                    y_mid = (y_prev_bottom + y_curr_top) / 2
                    _draw_mark_line(
                        pymupdf.Point(xp, y_mid - 2.0 * PT_PER_MM),
                        pymupdf.Point(xp, y_mid + 2.0 * PT_PER_MM)
                    )

        # D) MARCAS INTERNAS HORIZONTALES (en cada calle vertical entre columnas)
        for c in range(1, cols):
            x_prev_right = x_cuts[c-1][1]   # línea de corte derecha de la columna anterior
            x_curr_left  = x_cuts[c][0]     # línea de corte izquierda de la columna actual
            gutter_w = x_curr_left - x_prev_right

            inner_len = min(mark_len, max(2.0 * PT_PER_MM, (gutter_w - 2 * mark_offset) / 2))

            for yp in all_y:
                if gutter_w >= 2 * mark_offset + 2.0:
                    _draw_mark_line(
                        pymupdf.Point(x_prev_right + mark_offset, yp),
                        pymupdf.Point(x_prev_right + mark_offset + inner_len, yp)
                    )
                    _draw_mark_line(
                        pymupdf.Point(x_curr_left - mark_offset, yp),
                        pymupdf.Point(x_curr_left - mark_offset - inner_len, yp)
                    )
                else:
                    x_mid = (x_prev_right + x_curr_left) / 2
                    _draw_mark_line(
                        pymupdf.Point(x_mid - 2.0 * PT_PER_MM, yp),
                        pymupdf.Point(x_mid + 2.0 * PT_PER_MM, yp)
                    )

        # Marca de plegado (fold mark) en cuadernillo
        if is_booklet and cols == 2:
            x_spine = x_start + pw_pt
            y_top_mark = y_min_grid + bleed_pt - mark_offset
            y_bot_mark = y_max_grid - bleed_pt + mark_offset
            _draw_mark_line(pymupdf.Point(x_spine, y_top_mark), pymupdf.Point(x_spine, y_top_mark - mark_len))
            _draw_mark_line(pymupdf.Point(x_spine, y_bot_mark), pymupdf.Point(x_spine, y_bot_mark + mark_len))

    # Primero el halo blanco de fondo (0.85 pt) para contraste sobre tintas oscuras o fondos
    shape_halo.finish(color=(1, 1, 1), width=0.85)
    shape_halo.commit()
    # Encima el trazo negro de corte nítido (0.35 pt)
    shape_mark.finish(color=(0, 0, 0), width=0.35)
    shape_mark.commit()

    # 2. Cruces de registro circulares
    if add_reg_crosses:
        cx_mid = sheet_w_pt / 2.0
        cy_mid = sheet_h_pt / 2.0
        r_cross = 5.0
        reg_margin = 6.0 * PT_PER_MM
        _draw_registration_cross(sheet, cx_mid, reg_margin, r_cross)
        _draw_registration_cross(sheet, cx_mid, sheet_h_pt - reg_margin, r_cross)
        _draw_registration_cross(sheet, reg_margin, cy_mid, r_cross)
        _draw_registration_cross(sheet, sheet_w_pt - reg_margin, cy_mid, r_cross)

    # 3. Tira de control densitométrico FOGRA / ISO 12647-2 (Repetida a todo lo ancho del pliego)
    if add_color_bar:
        # Arranca a la izquierda del pliego y se repite de forma modular continua hasta el margen derecho
        bar_y = 5.0 * PT_PER_MM
        x_left = 6.0 * PT_PER_MM
        x_right = sheet_w_pt - 6.0 * PT_PER_MM

        # Protección para la cruz de registro central superior para evitar solapes
        skip_list = []
        if add_reg_crosses:
            cx_mid = sheet_w_pt / 2.0
            skip_list.append((cx_mid - 9.0, cx_mid + 9.0))

        _draw_cmyk_color_strip(
            sheet,
            x_start=x_left,
            y_top=bar_y,
            patch_w=6.0,
            patch_h=6.0,
            max_x=x_right,
            skip_zones=skip_list,
        )

    # 4. Información técnica del pliego (Slug)
    if add_slug:
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        full_slug = f"{slug_text} · {now_str}"
        slug_y = sheet_h_pt - (4.5 * PT_PER_MM)
        sheet.insert_text(
            pymupdf.Point(14 * PT_PER_MM, slug_y),
            full_slug,
            fontsize=6.5,
            fontname="helv",
            color=(0.25, 0.25, 0.25),
        )

        # Inyectar Código QR de Trazabilidad para el Maquinista en el margen
        if job_id:
            try:
                from traceability_engine import embed_traceability_qr
                qr_sz = 9.0 * PT_PER_MM  # 9 mm
                qr_x0 = 3.0 * PT_PER_MM
                qr_y0 = sheet_h_pt - 10.5 * PT_PER_MM
                qr_rect = pymupdf.Rect(qr_x0, qr_y0, qr_x0 + qr_sz, qr_y0 + qr_sz)
                embed_traceability_qr(sheet, qr_rect, job_id=job_id, base_url=base_url)
            except Exception:
                pass


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
