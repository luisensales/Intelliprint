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
from pdf_utils import atomic_output, preserve_output_intents
from security_limits import bounded_render_dpi, MAX_IMPOSITION_POSES, release_pdf_memory
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


def validate_sheet_size(value):
    if not isinstance(value, str) or value.upper() not in STANDARD_SHEET_SIZES_MM:
        raise ValueError("Formato de pliego no válido. Selecciona un formato del catálogo.")
    return value.upper()


def _get_page_boxes_mm(page: pymupdf.Page) -> Dict[str, Any]:
    """Measure physical boxes, including CropBox offsets, UserUnit and rotation."""
    rotation = page.rotation
    page.set_rotation(0)
    try:
        media = page.mediabox
        crop = page.cropbox
        unit = page.rect.width / crop.width
        # Box properties use unscaled coordinates from the top of MediaBox.
        def physical(rect):
            return pymupdf.Rect((rect.x0 - media.x0) * unit, rect.y0 * unit,
                                (rect.x1 - media.x0) * unit, rect.y1 * unit)

        media_rect = pymupdf.Rect(0, 0, media.width * unit, media.height * unit)
        trim = physical(page.trimbox)
        bleed = physical(page.bleedbox)
        if (not trim.is_valid or trim.is_empty or not media_rect.contains(trim)
                or not bleed.is_valid or not bleed.contains(trim)
                or not media_rect.contains(bleed)):
            raise ValueError("TrimBox y BleedBox deben ser válidas y estar dentro de MediaBox.")
        source_bleed_mm = sum((trim.x0 - bleed.x0, trim.y0 - bleed.y0,
                               bleed.x1 - trim.x1, bleed.y1 - trim.y1)) / 4 * MM_PER_PT
        slug = max(bleed.x0, bleed.y0, media_rect.x1 - bleed.x1,
                   media_rect.y1 - bleed.y1) * MM_PER_PT
        state = ("embedded_marks" if slug >= _EMBEDDED_MARKS_THRESHOLD_MM else
                 "has_bleed" if source_bleed_mm >= _BLEED_THRESHOLD_MM else "no_bleed")
        # Matrix rotation here is clockwise in MuPDF's top-down coordinates.
        display_trim = trim * pymupdf.Matrix(rotation)
        display_bleed = bleed * pymupdf.Matrix(rotation)
        selected = display_bleed if state == "has_bleed" else display_trim
        insets = (display_trim.x0 - selected.x0, display_trim.y0 - selected.y0,
                  selected.x1 - display_trim.x1, selected.y1 - display_trim.y1)
        return {
            "trim_w_mm": display_trim.width * MM_PER_PT,
            "trim_h_mm": display_trim.height * MM_PER_PT,
            "bleed_w_mm": display_bleed.width * MM_PER_PT,
            "bleed_h_mm": display_bleed.height * MM_PER_PT,
            "media_w_mm": (media_rect * pymupdf.Matrix(rotation)).width * MM_PER_PT,
            "media_h_mm": (media_rect * pymupdf.Matrix(rotation)).height * MM_PER_PT,
            "source_bleed_mm": source_bleed_mm,
            "pdf_state": state,
            "clip_rect_pt": trim,
            "bleed_rect_pt": bleed,
            "trim_insets_pt": insets,
            "rotation": rotation,
        }
    finally:
        page.set_rotation(rotation)


def calculate_imposition_plan(
    pdf_path: str | Path,
    sheet_size: str = "SRA3",
    orientation: str = "auto",  # "auto", "landscape", "portrait"
    mode: str = "step_and_repeat",  # "step_and_repeat", "booklet", "2up", "4up"
    gap_mm: float = 4.0,  # Calle intermedia entre poses (fallback si no se especifica gap_x/gap_y)
    bleed_mm: float = 2.0,  # Sangrado por pose en la imposición (mínimo de seguridad)
    sheet_margin_mm: float = 10.0,  # Margen perimetral para pinza de máquina y marcas
    user_cols: Optional[int] = None,
    user_rows: Optional[int] = None,
    gap_x_mm: Optional[float] = None,
    gap_y_mm: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calcula el plan geométrico de imposición y aprovechamiento del pliego.

    Detecta automáticamente el estado del PDF de origen (sin sangre / con sangre / con marcas
    incrustadas) y adapta el plan geométrico en consecuencia.
    """
    sheet_size = validate_sheet_size(sheet_size)
    for value in (gap_mm, bleed_mm, sheet_margin_mm,
                  gap_x_mm if gap_x_mm is not None else gap_mm,
                  gap_y_mm if gap_y_mm is not None else gap_mm):
        if not math.isfinite(float(value)) or not 0 <= float(value) <= 200:
            raise ValueError("Los márgenes y calles deben ser finitos y estar entre 0 y 200 mm.")
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    doc = pymupdf.open(str(pdf_path))
    total_doc_pages = len(doc)
    if total_doc_pages == 0:
        doc.close()
        raise ValueError("El documento PDF no contiene páginas.")

    try:
        boxes = _get_page_boxes_mm(doc[0])
        keys = (("trim_w_mm", "trim_h_mm") if mode == "booklet" else
                ("trim_w_mm", "trim_h_mm", "bleed_w_mm", "bleed_h_mm", "pdf_state", "trim_insets_pt"))
        for page in doc:
            other = _get_page_boxes_mm(page)
            for key in keys:
                left, right = boxes[key], other[key]
                if isinstance(left, tuple):
                    equal = all(abs(x - y) < 0.01 for x, y in zip(left, right))
                elif isinstance(left, str):
                    equal = left == right
                else:
                    equal = abs(left - right) < 0.001
                if not equal:
                    raise ValueError("La imposición a escala 100% requiere páginas con las mismas dimensiones de corte y sangre.")
    finally:
        doc.close()

    trim_w_mm = boxes["trim_w_mm"]
    trim_h_mm = boxes["trim_h_mm"]
    bleed_w_mm = boxes["bleed_w_mm"]
    bleed_h_mm = boxes["bleed_h_mm"]
    source_bleed_mm = boxes["source_bleed_mm"]
    pdf_state = boxes["pdf_state"]

    gx_mm = float(gap_x_mm) if gap_x_mm is not None else float(gap_mm)
    gy_mm = float(gap_y_mm) if gap_y_mm is not None else float(gap_mm)

    # La pose "efectiva" incluye la sangre cuando el PDF la tiene nativamente,
    # para que el contenido sangrado se renderice completo en el pliego.
    if pdf_state == "has_bleed":
        pose_base_w = bleed_w_mm
        pose_base_h = bleed_h_mm
    else:
        # 'no_bleed' o 'embedded_marks': usamos TrimBox (en embedded_marks haremos clip)
        pose_base_w = trim_w_mm
        pose_base_h = trim_h_mm

    base_sheet = STANDARD_SHEET_SIZES_MM[sheet_size]
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
    # 1. PLAN MODO CUADERNILLO (BOOKLET SADDLE-STITCH, 1 O 2 EJEMPLARES/PLIEGO)
    # =========================================================================
    if mode == "booklet":
        target_orient = orientation.lower() if orientation else "auto"
        if target_orient not in ("landscape", "portrait", "auto"):
            target_orient = "auto"

        allow_double = not (user_cols == 1 or user_rows == 1)

        options = {}
        for s_orient in ("landscape", "portrait"):
            s_w = sheet_long_mm if s_orient == "landscape" else sheet_short_mm
            s_h = sheet_short_mm if s_orient == "landscape" else sheet_long_mm
            avail_w = s_w - 2 * sheet_margin_mm
            avail_h = s_h - 2 * sheet_margin_mm

            # Spread normal (rot=False): 2 páginas lado a lado (2*trim_w × trim_h), lomo vertical
            fits_side_1 = (trim_w_mm * 2 <= avail_w and trim_h_mm <= avail_h)
            fits_side_2 = allow_double and fits_side_1 and (trim_h_mm * 2 + gy_mm <= avail_h)

            # Spread rotado 90° (rot=True): 2 páginas apiladas (trim_h × 2*trim_w), lomo horizontal
            fits_rot_1 = (trim_h_mm <= avail_w and trim_w_mm * 2 <= avail_h)
            fits_rot_2 = allow_double and fits_rot_1 and (trim_h_mm * 2 + gx_mm <= avail_w)

            candidates = []
            if fits_side_2:
                candidates.append({"rot": False, "cols": 2, "rows": 2, "copies": 2, "poses": 4, "gx": 0.0, "gy": gy_mm, "fits": True, "pref": 1 if s_orient == "landscape" else 0})
            elif fits_side_1:
                candidates.append({"rot": False, "cols": 2, "rows": 1, "copies": 1, "poses": 2, "gx": 0.0, "gy": 0.0, "fits": True, "pref": 1 if s_orient == "landscape" else 0})

            if fits_rot_2:
                candidates.append({"rot": True, "cols": 2, "rows": 2, "copies": 2, "poses": 4, "gx": gx_mm, "gy": 0.0, "fits": True, "pref": 1 if s_orient == "portrait" else 0})
            elif fits_rot_1:
                candidates.append({"rot": True, "cols": 1, "rows": 2, "copies": 1, "poses": 2, "gx": 0.0, "gy": 0.0, "fits": True, "pref": 1 if s_orient == "portrait" else 0})

            if candidates:
                best_cand = max(candidates, key=lambda c: (c["poses"], c["pref"]))
            else:
                if s_orient == "landscape":
                    best_cand = {"rot": False, "cols": 2, "rows": 1, "copies": 1, "poses": 2, "gx": 0.0, "gy": 0.0, "fits": False, "pref": 1}
                else:
                    best_cand = {"rot": True, "cols": 1, "rows": 2, "copies": 1, "poses": 2, "gx": 0.0, "gy": 0.0, "fits": False, "pref": 1}

            eff = round(((trim_w_mm * trim_h_mm * best_cand["poses"]) / (s_w * s_h)) * 100, 1)
            options[s_orient] = {
                "sheet_w_mm": s_w,
                "sheet_h_mm": s_h,
                "rotated_90": best_cand["rot"],
                "cols": best_cand["cols"],
                "rows": best_cand["rows"],
                "copies": best_cand["copies"],
                "poses": best_cand["poses"],
                "gx": best_cand["gx"],
                "gy": best_cand["gy"],
                "eff": eff,
                "fits": best_cand["fits"],
            }

        if target_orient == "portrait":
            chosen_orient = "portrait"
        elif target_orient == "landscape":
            chosen_orient = "landscape"
        else:  # "auto"
            if options["landscape"]["fits"] and not options["portrait"]["fits"]:
                chosen_orient = "landscape"
            elif options["portrait"]["fits"] and not options["landscape"]["fits"]:
                chosen_orient = "portrait"
            elif options["portrait"]["poses"] > options["landscape"]["poses"]:
                chosen_orient = "portrait"
            else:
                chosen_orient = "landscape"

        opt = options[chosen_orient]
        sheet_w_mm = opt["sheet_w_mm"]
        sheet_h_mm = opt["sheet_h_mm"]
        rot_90 = opt["rotated_90"]
        grid_cols = opt["cols"]
        grid_rows = opt["rows"]
        copies_per_sheet = opt["copies"]
        total_poses = opt["poses"]
        eff_gx = opt["gx"]
        eff_gy = opt["gy"]
        eff = opt["eff"]
        fits_normal = opt["fits"]

        padded_pages = total_doc_pages
        remainder = padded_pages % 4
        if remainder != 0:
            padded_pages += (4 - remainder)

        sheets_needed = padded_pages // 4
        warning_text = None if fits_normal else "El formato de página excede el tamaño del pliego seleccionado para cuadernillo."

        return {
            "mode": "booklet",
            "sheet_size": sheet_size.upper(),
            "sheet_dimensions_mm": [sheet_w_mm, sheet_h_mm],
            "orientation": chosen_orient,
            "original_pages": total_doc_pages,
            "padded_pages": padded_pages,
            "sheets_needed": sheets_needed,
            "copies_per_sheet": copies_per_sheet,
            "pages_per_sheet_side": total_poses,
            "pose_size_mm": [trim_w_mm, trim_h_mm],
            "pose_with_bleed_mm": [pose_base_w, pose_base_h],
            "grid": {"cols": grid_cols, "rows": grid_rows, "total_poses": total_poses},
            "rotated_90": rot_90,
            "gap_mm": max(eff_gx, eff_gy),
            "gap_x_mm": eff_gx,
            "gap_y_mm": eff_gy,
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
                req_w = c * pw + (c - 1) * gx_mm
                req_h = r * ph + (r - 1) * gy_mm
                if req_w > avail_w or req_h > avail_h:
                    continue
            else:
                c = int((avail_w + gx_mm) // (pw + gx_mm))
                r = int((avail_h + gy_mm) // (ph + gy_mm))

            poses = c * r
            if poses > MAX_IMPOSITION_POSES:
                raise ValueError("La imposición supera el límite de 2500 poses por cara.")
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
                    "gap_mm": gx_mm,
                    "gap_x_mm": gx_mm,
                    "gap_y_mm": gy_mm,
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
            "gap_mm": gx_mm,
            "gap_x_mm": gx_mm,
            "gap_y_mm": gy_mm,
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


def _draw_registration_cross(page: pymupdf.Page, cx: float, cy: float, radius: float = 5.0):
    """Dibuja una cruz de registro circular estilo prepress en coordenadas (cx, cy) con halo blanco."""
    shape_halo = page.new_shape()
    shape_halo.draw_circle(pymupdf.Point(cx, cy), radius + 1.5)
    shape_halo.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0.8)
    shape_halo.commit()

    shape = page.new_shape()
    shape.draw_circle(pymupdf.Point(cx, cy), radius)
    shape.draw_line(pymupdf.Point(cx - radius - 3.5, cy), pymupdf.Point(cx + radius + 3.5, cy))
    shape.draw_line(pymupdf.Point(cx, cy - radius - 3.5), pymupdf.Point(cx, cy + radius + 3.5))
    shape.finish(color=(0, 0, 0), width=0.45)
    shape.commit()


_CACHED_STRIP_PDF: Optional[pymupdf.Document] = None
_CACHED_STRIP_CROP = pymupdf.Rect(15.0, 155.0, 1348.5, 188.5)


def _inline_svg_css(svg_bytes: bytes) -> bytes:
    """Convierte clases CSS de bloques <style> a atributos XML inline para compatibilidad con MuPDF."""
    try:
        import re
        import xml.etree.ElementTree as ET
        svg_text = svg_bytes.decode("utf-8", errors="ignore")
        style_match = re.search(r"<style[^>]*>(.*?)</style>", svg_text, re.DOTALL)
        if not style_match:
            return svg_bytes

        css_content = style_match.group(1)
        rules = {}
        for block in re.finditer(r"([^{]+)\{([^}]+)\}", css_content):
            selectors = [s.strip() for s in block.group(1).split(",")]
            props = {}
            for decl in block.group(2).split(";"):
                if ":" in decl:
                    k, v = decl.split(":", 1)
                    props[k.strip()] = v.strip()
            for sel in selectors:
                if sel.startswith("."):
                    rules.setdefault(sel[1:], {}).update(props)

        ET.register_namespace("", "http://www.w3.org/2000/svg")
        tree = ET.fromstring(svg_text)
        for elem in tree.iter():
            classes = elem.attrib.get("class", "").split()
            merged = {}
            for c in classes:
                if c in rules:
                    merged.update(rules[c])
            if "font-family" in merged:
                merged["font-family"] = "Helvetica, Arial, sans-serif"
            for k, v in merged.items():
                if k not in elem.attrib:
                    elem.attrib[k] = v
            # También estilo inline directo
            parts = [f"{k}: {v}" for k, v in merged.items()]
            if parts:
                cur_st = elem.attrib.get("style", "")
                if cur_st and not cur_st.endswith(";"):
                    cur_st += "; "
                elem.attrib["style"] = cur_st + "; ".join(parts)

        return ET.tostring(tree, encoding="utf-8")
    except Exception:
        return svg_bytes


def _get_strip_pdf_doc() -> Optional[pymupdf.Document]:
    """Carga y convierte a PDF vectorial en memoria la Tira de control 25-50-75.svg."""
    global _CACHED_STRIP_PDF
    if _CACHED_STRIP_PDF is not None:
        return _CACHED_STRIP_PDF

    possible_paths = [
        Path("assets/Tira de control 25-50-75.svg"),
        Path(__file__).parent / "assets" / "Tira de control 25-50-75.svg",
    ]
    for p in possible_paths:
        if p.exists():
            try:
                raw_svg = p.read_bytes()
                inlined_svg = _inline_svg_css(raw_svg)
                svg_doc = pymupdf.open("svg", inlined_svg)
                pdf_bytes = svg_doc.convert_to_pdf()
                svg_doc.close()
                _CACHED_STRIP_PDF = pymupdf.open("pdf", pdf_bytes)
                return _CACHED_STRIP_PDF
            except Exception as e:
                print(f"Error cargando tira de control SVG: {e}")
    return None


def _draw_custom_color_strip(
    page: pymupdf.Page,
    x_start: float,
    x_end: float,
    y_top: float,
    target_h_pt: float = 10.0 * PT_PER_MM,
):
    """
    Embebe la tira de control 25-50-75 (vectorial nativa) a todo lo ancho del pliego/trabajo,
    repitiéndola tantas veces como sea necesario para cubrir de x_start a x_end,
    y recortando limpiamente el último módulo si excede x_end.
    Altura mínima garantizada: 10 mm.
    """
    strip_doc = _get_strip_pdf_doc()
    h_pt = max(target_h_pt, 10.0 * PT_PER_MM)

    if strip_doc is not None:
        try:
            orig_crop = _CACHED_STRIP_CROP
            cw = orig_crop.width
            ch = orig_crop.height
            if cw > 0 and ch > 0:
                scale = h_pt / ch
                tile_w = cw * scale

                curr_x = x_start
                while curr_x < x_end - 0.5:
                    avail_w = x_end - curr_x
                    if avail_w >= tile_w:
                        dest_rect = pymupdf.Rect(curr_x, y_top, curr_x + tile_w, y_top + h_pt)
                        page.show_pdf_page(dest_rect, strip_doc, 0, clip=orig_crop)
                        curr_x += tile_w
                    else:
                        frac = avail_w / tile_w
                        clip_w = cw * frac
                        tile_crop = pymupdf.Rect(orig_crop.x0, orig_crop.y0, orig_crop.x0 + clip_w, orig_crop.y1)
                        dest_rect = pymupdf.Rect(curr_x, y_top, curr_x + avail_w, y_top + h_pt)
                        page.show_pdf_page(dest_rect, strip_doc, 0, clip=tile_crop)
                        curr_x += avail_w
                return
        except Exception as e:
            print(f"Error renderizando tira vectorial: {e}")

    # Fallback: tira de control de emergencia CMYK con porcentajes 25-50-75-100%
    colors = [
        (0.0, 0.65, 0.90), (0.3, 0.75, 0.93), (0.6, 0.88, 0.96),  # Cyan 100, 50, 25%
        (0.85, 0.05, 0.45), (0.90, 0.45, 0.70), (0.95, 0.75, 0.85), # Magenta 100, 50, 25%
        (0.98, 0.85, 0.05), (0.99, 0.92, 0.50), (0.99, 0.96, 0.75), # Yellow 100, 50, 25%
        (0.10, 0.10, 0.10), (0.45, 0.45, 0.45), (0.75, 0.75, 0.75), # Black 100, 50, 25%
    ]
    patch_w = 12.0
    cur_x = x_start
    shape = page.new_shape()
    while cur_x + patch_w <= x_end:
        for col in colors:
            if cur_x + patch_w > x_end:
                break
            shape.draw_rect(pymupdf.Rect(cur_x, y_top, cur_x + patch_w, y_top + h_pt))
            shape.finish(fill=col, color=(0.7, 0.7, 0.7), width=0.3)
            cur_x += patch_w + 1.0
        if cur_x >= x_end:
            break
    shape.commit()


def _place_pose(sheet, src_doc, page_idx, rect_pose, rotate, boxes, trim_only=False):
    """Place the exact box used for planning, without shrinking MediaBox into it."""
    clip = (boxes["bleed_rect_pt"] if boxes["pdf_state"] == "has_bleed" and not trim_only
            else boxes["clip_rect_pt"])
    angle = (rotate - boxes["rotation"]) % 360
    width, height = (clip.height, clip.width) if angle % 180 else (clip.width, clip.height)
    if abs(width - rect_pose.width) > 0.02 or abs(height - rect_pose.height) > 0.02:
        raise ValueError("La pose no coincide con el tamaño físico del original a escala 100%.")
    sheet.show_pdf_page(rect_pose, src_doc, page_idx, rotate=angle, clip=clip)


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
    gap_x_mm: Optional[float] = None,
    gap_y_mm: Optional[float] = None,
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
        gap_x_mm=gap_x_mm,
        gap_y_mm=gap_y_mm,
    )

    if not plan.get("fits", True):
        raise ValueError("El original no cabe en el pliego seleccionado a escala 100%.")
    src_doc = pymupdf.open(str(pdf_path))
    out_doc = pymupdf.open()
    page_boxes = [_get_page_boxes_mm(page) for page in src_doc]
    # Import from the entire MediaBox, so a restrictive CropBox cannot truncate bleed.
    # These changes affect only the in-memory source document.
    for page in src_doc:
        media = page.mediabox
        page.set_rotation(0)
        page.set_cropbox(pymupdf.Rect(media.x0, 0, media.x1, media.height))
    sheet_w_mm, sheet_h_mm = plan["sheet_dimensions_mm"]
    sheet_w_pt, sheet_h_pt = sheet_w_mm * PT_PER_MM, sheet_h_mm * PT_PER_MM
    pdf_state = plan.get("pdf_state", "no_bleed")
    source_bleed_mm = plan.get("source_bleed_mm", 0.0)
    trim_insets = page_boxes[0]["trim_insets_pt"]
    if plan.get("rotated_90", False):
        trim_insets = (trim_insets[1], trim_insets[2], trim_insets[3], trim_insets[0])

    # =========================================================================
    # 1. GENERACIÓN: MODO CUADERNILLO GRAPADO (SADDLE-STITCH BOOKLET)
    # =========================================================================
    if mode == "booklet":
        total_p = plan["original_pages"]
        padded_p = plan["padded_pages"]
        sheets_needed = plan["sheets_needed"]
        copies = plan.get("copies_per_sheet", 1)
        rot = plan.get("rotated_90", False)
        rot_val = 90 if rot else 0

        # En cuadernillo siempre usamos TrimBox (tamaño neto de la página)
        trim_w_pt = plan["pose_size_mm"][0] * PT_PER_MM
        trim_h_pt = plan["pose_size_mm"][1] * PT_PER_MM
        gx_pt = plan.get("gap_x_mm", 0.0) * PT_PER_MM
        gy_pt = plan.get("gap_y_mm", 0.0) * PT_PER_MM

        if rot:
            pw_pt = trim_h_pt
            ph_pt = trim_w_pt
            cols = 2 if copies == 2 else 1
            rows = 2
            gap_x_pt = gx_pt if copies == 2 else 0.0
            gap_y_pt = 0.0
        else:
            pw_pt = trim_w_pt
            ph_pt = trim_h_pt
            cols = 2
            rows = 2 if copies == 2 else 1
            gap_x_pt = 0.0
            gap_y_pt = gy_pt if copies == 2 else 0.0

        total_w_pt = cols * pw_pt + (cols - 1) * gap_x_pt
        total_h_pt = rows * ph_pt + (rows - 1) * gap_y_pt
        x_start = (sheet_w_pt - total_w_pt) / 2.0
        y_start = (sheet_h_pt - total_h_pt) / 2.0
        copies_label = " · Doble producción (2 ej./pliego)" if copies == 2 else ""

        for k in range(sheets_needed):
            p_front_left_idx  = (padded_p - 1) - (2 * k)
            p_front_right_idx = 2 * k

            sheet_front = out_doc.new_page(width=sheet_w_pt, height=sheet_h_pt)

            for copy_idx in range(copies):
                if rot:
                    cx = x_start + copy_idx * (pw_pt + gap_x_pt)
                    rect_fl = pymupdf.Rect(cx, y_start, cx + pw_pt, y_start + ph_pt)
                    rect_fr = pymupdf.Rect(cx, y_start + ph_pt, cx + pw_pt, y_start + 2 * ph_pt)
                else:
                    ry = y_start + copy_idx * (ph_pt + gap_y_pt)
                    rect_fl = pymupdf.Rect(x_start, ry, x_start + pw_pt, ry + ph_pt)
                    rect_fr = pymupdf.Rect(x_start + pw_pt, ry, x_start + 2 * pw_pt, ry + ph_pt)

                if p_front_left_idx < total_p:
                    _place_pose(sheet_front, src_doc, p_front_left_idx, rect_fl, rot_val, page_boxes[p_front_left_idx], trim_only=True)
                if p_front_right_idx < total_p:
                    _place_pose(sheet_front, src_doc, p_front_right_idx, rect_fr, rot_val, page_boxes[p_front_right_idx], trim_only=True)

            _decorate_sheet(
                sheet=sheet_front,
                sheet_w_pt=sheet_w_pt,
                sheet_h_pt=sheet_h_pt,
                x_start=x_start,
                y_start=y_start,
                cols=cols,
                rows=rows,
                pw_pt=pw_pt,
                ph_pt=ph_pt,
                gap_pt=0.0,
                gap_x_pt=gap_x_pt,
                gap_y_pt=gap_y_pt,
                source_bleed_mm=0.0,  # cuadernillo: marks en borde del TrimBox
                add_marks=add_marks,
                add_reg_crosses=add_reg_crosses,
                add_color_bar=add_color_bar,
                add_slug=add_slug,
                slug_text=f"IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII · Cuadernillo{copies_label} · Pliego {k+1}/{sheets_needed} [Cara A] · Páginas [{p_front_left_idx+1} + {p_front_right_idx+1}]",
                is_booklet=True,
                booklet_rot=rot,
                job_id=job_id,
                base_url=base_url,
            )

            # Lado Reverso
            p_back_left_idx  = 2 * k + 1
            p_back_right_idx = (padded_p - 1) - (2 * k + 1)

            sheet_back = out_doc.new_page(width=sheet_w_pt, height=sheet_h_pt)

            for copy_idx in range(copies):
                if rot:
                    cx = x_start + copy_idx * (pw_pt + gap_x_pt)
                    rect_bl = pymupdf.Rect(cx, y_start, cx + pw_pt, y_start + ph_pt)
                    rect_br = pymupdf.Rect(cx, y_start + ph_pt, cx + pw_pt, y_start + 2 * ph_pt)
                else:
                    ry = y_start + copy_idx * (ph_pt + gap_y_pt)
                    rect_bl = pymupdf.Rect(x_start, ry, x_start + pw_pt, ry + ph_pt)
                    rect_br = pymupdf.Rect(x_start + pw_pt, ry, x_start + 2 * pw_pt, ry + ph_pt)

                if p_back_left_idx < total_p:
                    _place_pose(sheet_back, src_doc, p_back_left_idx, rect_bl, rot_val, page_boxes[p_back_left_idx], trim_only=True)
                if p_back_right_idx < total_p:
                    _place_pose(sheet_back, src_doc, p_back_right_idx, rect_br, rot_val, page_boxes[p_back_right_idx], trim_only=True)

            _decorate_sheet(
                sheet=sheet_back,
                sheet_w_pt=sheet_w_pt,
                sheet_h_pt=sheet_h_pt,
                x_start=x_start,
                y_start=y_start,
                cols=cols,
                rows=rows,
                pw_pt=pw_pt,
                ph_pt=ph_pt,
                gap_pt=0.0,
                gap_x_pt=gap_x_pt,
                gap_y_pt=gap_y_pt,
                source_bleed_mm=0.0,
                add_marks=add_marks,
                add_reg_crosses=add_reg_crosses,
                add_color_bar=add_color_bar,
                add_slug=add_slug,
                slug_text=f"IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII · Cuadernillo{copies_label} · Pliego {k+1}/{sheets_needed} [Cara B] · Páginas [{p_back_left_idx+1} + {p_back_right_idx+1}]",
                is_booklet=True,
                booklet_rot=rot,
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
        gap_x_pt = plan.get("gap_x_mm", plan.get("gap_mm", 4.0)) * PT_PER_MM
        gap_y_pt = plan.get("gap_y_mm", plan.get("gap_mm", 4.0)) * PT_PER_MM
        rot = plan.get("rotated_90", False)

        total_grid_w_pt = cols * pw_pt + (cols - 1) * gap_x_pt
        total_grid_h_pt = rows * ph_pt + (rows - 1) * gap_y_pt

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
                    px = x_start + c * (pw_pt + gap_x_pt)
                    py = y_start + r * (ph_pt + gap_y_pt)
                    rect_pose = pymupdf.Rect(px, py, px + pw_pt, py + ph_pt)
                    _place_pose(sheet, src_doc, src_page_idx, rect_pose, rotate_val, page_boxes[src_page_idx])
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
                gap_pt=gap_x_pt,
                gap_x_pt=gap_x_pt,
                gap_y_pt=gap_y_pt,
                source_bleed_mm=source_bleed_mm,
                trim_insets_pt=trim_insets,
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
                    gap_pt=gap_x_pt,
                    gap_x_pt=gap_x_pt,
                    gap_y_pt=gap_y_pt,
                    source_bleed_mm=source_bleed_mm,
                    trim_insets_pt=trim_insets,
                    add_marks=add_marks,
                    add_reg_crosses=add_reg_crosses,
                    add_color_bar=add_color_bar,
                    add_slug=add_slug,
                    slug_text=f"IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII · {pdf_path.name} · Pliego {sh_idx+1}/{sheets_count} · {total_poses_per_sheet} poses/pliego",
                    is_booklet=False,
                    job_id=job_id,
                    base_url=base_url,
                )

    out_pages = len(out_doc)
    with atomic_output(output_path) as temporary:
        out_doc.save(str(temporary), deflate=True)
        out_doc.close()
        src_doc.close()
        preserve_output_intents(pdf_path, temporary)
    release_pdf_memory()


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
    gap_pt: float = 0.0,
    source_bleed_mm: float = 0.0,
    add_marks: bool = True,
    add_reg_crosses: bool = True,
    add_color_bar: bool = True,
    add_slug: bool = True,
    slug_text: str = "",
    is_booklet: bool = False,
    booklet_rot: bool = False,
    job_id: Optional[str] = None,
    base_url: str = "",
    gap_x_pt: Optional[float] = None,
    gap_y_pt: Optional[float] = None,
    trim_insets_pt: Optional[Tuple[float, float, float, float]] = None,
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

    left, top, right, bottom = trim_insets_pt or (bleed_pt,) * 4

    gx_pt = gap_x_pt if gap_x_pt is not None else gap_pt
    gy_pt = gap_y_pt if gap_y_pt is not None else gap_pt

    def _draw_mark_line(p1: pymupdf.Point, p2: pymupdf.Point):
        shape_halo.draw_line(p1, p2)
        shape_mark.draw_line(p1, p2)

    # 1. Marcas de corte
    if add_marks:
        # Posiciones de corte X por columna [(x_left, x_right), ...]
        x_cuts = []
        for c in range(cols):
            x_left  = x_start + c * (pw_pt + gx_pt) + left
            x_right = x_start + c * (pw_pt + gx_pt) + pw_pt - right
            x_cuts.append((x_left, x_right))

        # Posiciones de corte Y por fila [(y_top, y_bottom), ...]
        y_cuts = []
        for r in range(rows):
            y_top    = y_start + r * (ph_pt + gy_pt) + top
            y_bottom = y_start + r * (ph_pt + gy_pt) + ph_pt - bottom
            y_cuts.append((y_top, y_bottom))

        all_x = [pos for pair in x_cuts for pos in pair]
        all_y = [pos for pair in y_cuts for pos in pair]

        # Límites de la rejilla
        total_grid_w_calc = cols * pw_pt + (cols - 1) * gx_pt
        total_grid_h_calc = rows * ph_pt + (rows - 1) * gy_pt
        y_min_grid = y_start
        y_max_grid = y_start + total_grid_h_calc
        x_min_grid = x_start
        x_max_grid = x_start + total_grid_w_calc

        # A) Marcas verticales exteriores (borde superior e inferior del pliego)
        for xp in all_x:
            y_top_mark = y_min_grid + top - mark_offset
            _draw_mark_line(pymupdf.Point(xp, y_top_mark), pymupdf.Point(xp, y_top_mark - mark_len))
            y_bot_mark = y_max_grid - bottom + mark_offset
            _draw_mark_line(pymupdf.Point(xp, y_bot_mark), pymupdf.Point(xp, y_bot_mark + mark_len))

        # B) Marcas horizontales exteriores (borde izquierdo y derecho del pliego)
        for yp in all_y:
            x_left_mark = x_min_grid + left - mark_offset
            _draw_mark_line(pymupdf.Point(x_left_mark, yp), pymupdf.Point(x_left_mark - mark_len, yp))
            x_right_mark = x_max_grid - right + mark_offset
            _draw_mark_line(pymupdf.Point(x_right_mark, yp), pymupdf.Point(x_right_mark + mark_len, yp))

        # C) MARCAS INTERNAS VERTICALES (en cada calle horizontal entre filas)
        # En cuadernillo con lomo horizontal (booklet_rot=True), la unión entre filas es pliegue, no corte.
        if not (is_booklet and booklet_rot):
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
        # En cuadernillo con lomo vertical (booklet_rot=False), la unión entre columnas es pliegue, no corte.
        if not (is_booklet and not booklet_rot):
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
        if is_booklet and not booklet_rot and cols == 2:
            x_spine = x_start + pw_pt
            y_top_mark = y_min_grid + top - mark_offset
            y_bot_mark = y_max_grid - bottom + mark_offset
            _draw_mark_line(pymupdf.Point(x_spine, y_top_mark), pymupdf.Point(x_spine, y_top_mark - mark_len))
            _draw_mark_line(pymupdf.Point(x_spine, y_bot_mark), pymupdf.Point(x_spine, y_bot_mark + mark_len))
        elif is_booklet and booklet_rot and rows == 2:
            y_spine = y_start + ph_pt
            x_left_mark = x_min_grid + left - mark_offset
            x_right_mark = x_max_grid - right + mark_offset
            _draw_mark_line(pymupdf.Point(x_left_mark, y_spine), pymupdf.Point(x_left_mark - mark_len, y_spine))
            _draw_mark_line(pymupdf.Point(x_right_mark, y_spine), pymupdf.Point(x_right_mark + mark_len, y_spine))

    # Primero el halo blanco de fondo (0.85 pt) para contraste sobre tintas oscuras o fondos
    shape_halo.finish(color=(1, 1, 1), width=0.85)
    shape_halo.commit()
    # Encima el trazo negro de corte nítido (0.35 pt)
    shape_mark.finish(color=(0, 0, 0), width=0.35)
    shape_mark.commit()

    # 2. Tira de control 25-50-75 (mínimo 10 mm de altura, repetida a todo lo ancho del trabajo/pliego)
    if add_color_bar:
        strip_h_pt = 10.0 * PT_PER_MM
        # Posición Y en el margen superior: 3.5 mm
        bar_y = 3.5 * PT_PER_MM
        top_cut_limit = y_min_grid + top - mark_offset - mark_len
        if top_cut_limit > strip_h_pt + 3.0 * PT_PER_MM:
            bar_y = max(2.5 * PT_PER_MM, min(4.0 * PT_PER_MM, (top_cut_limit - strip_h_pt) / 2.0))
        elif top_cut_limit > strip_h_pt + 1.0 * PT_PER_MM:
            bar_y = max(1.5 * PT_PER_MM, top_cut_limit - strip_h_pt - 1.0 * PT_PER_MM)

        # Cubre todo el ancho del trabajo y pliego útil
        x_left = min(x_min_grid, 6.0 * PT_PER_MM)
        x_right = max(x_max_grid, sheet_w_pt - 6.0 * PT_PER_MM)

        _draw_custom_color_strip(
            sheet,
            x_start=x_left,
            x_end=x_right,
            y_top=bar_y,
            target_h_pt=strip_h_pt,
        )

    # 3. Cruces de registro circulares (con halo blanco para no empastarse con la tira)
    if add_reg_crosses:
        cx_mid = sheet_w_pt / 2.0
        cy_mid = sheet_h_pt / 2.0
        r_cross = 5.0
        reg_margin = 6.0 * PT_PER_MM
        _draw_registration_cross(sheet, cx_mid, reg_margin, r_cross)
        _draw_registration_cross(sheet, cx_mid, sheet_h_pt - reg_margin, r_cross)
        _draw_registration_cross(sheet, reg_margin, cy_mid, r_cross)
        _draw_registration_cross(sheet, sheet_w_pt - reg_margin, cy_mid, r_cross)

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
    gap_x_mm: Optional[float] = None,
    gap_y_mm: Optional[float] = None,
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
            gap_x_mm=gap_x_mm,
            gap_y_mm=gap_y_mm,
        )

        doc = pymupdf.open(str(temp_out))
        page0 = doc[0]
        zoom = bounded_render_dpi(page0.rect, dpi) / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page0.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes(output="jpeg")
        del pix
        doc.close()
        release_pdf_memory()
        return img_bytes
    finally:
        if temp_out.exists():
            temp_out.unlink()
