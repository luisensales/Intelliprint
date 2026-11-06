"""
geometry_fixer.py - Ajuste y normalización de cajas de página (TrimBox, BleedBox, MediaBox)
y sangrado reglamentario de 3.0 mm según especificación ISO 12647 / ISO 15930 (PDF/X).
"""

import math
from pathlib import Path
from typing import Dict, Any, List, Optional
import pikepdf


# Tamaños estándar ISO/ANSI en milímetros (ancho, alto)
STANDARD_PAGE_SIZES_MM = [
    ("A4", 210.0, 297.0),
    ("A3", 297.0, 420.0),
    ("A5", 148.0, 210.0),
    ("A6", 105.0, 148.0),
    ("A2", 420.0, 594.0),
    ("A1", 594.0, 841.0),
    ("Letter", 215.9, 279.4),
    ("Legal", 215.9, 355.6),
    ("Tabloid", 279.4, 431.8),
    ("B5", 176.0, 250.0),
    ("B4", 250.0, 353.0),
]


def mm_to_pt(mm: float) -> float:
    return mm * 72.0 / 25.4


def pt_to_mm(pt: float) -> float:
    return pt * 25.4 / 72.0


def _matches_size(w_mm: float, h_mm: float, target_w: float, target_h: float, tol_mm: float = 1.5) -> bool:
    # Comprobar orientación normal y apaisada
    match_normal = abs(w_mm - target_w) <= tol_mm and abs(h_mm - target_h) <= tol_mm
    match_rotated = abs(w_mm - target_h) <= tol_mm and abs(h_mm - target_w) <= tol_mm
    return match_normal or match_rotated


def fix_pdf_boxes_and_bleed(
    pdf_path: str,
    output_path: str,
    target_bleed_mm: float = 3.0
) -> Dict[str, Any]:
    """
    Normaliza y define las cajas de página TrimBox y BleedBox a 3.0 mm en un documento PDF.

    Reglas de ajuste:
    1. Si la página ya tiene un TrimBox explícito distinto de MediaBox:
       - Respeta el TrimBox original del diseñador.
       - Configura BleedBox = TrimBox + target_bleed_mm en todos los cuatro bordes.
       - Expande MediaBox si es necesario para asegurar que contenga completamente el BleedBox.

    2. Si la página no tiene TrimBox (o TrimBox == MediaBox):
       - Si las dimensiones del MediaBox coinciden con un formato estándar + 2*sangrado (ej. 216x303 mm):
         El documento ya incluía el sangrado en el lienzo:
         TrimBox = MediaBox inset en target_bleed_mm.
         BleedBox = MediaBox original.
       - En cualquier otro caso (el lienzo es el tamaño neto de corte o formato personalizado):
         TrimBox = MediaBox actual (tamaño final de corte).
         BleedBox = TrimBox + target_bleed_mm.
         MediaBox = BleedBox (se expande el lienzo 3 mm para alojar el sangrado).

    Preserva intactos todos los flujos de contenido, texto, fuentes, imágenes y perfiles.
    """
    bleed_pt = mm_to_pt(target_bleed_mm)
    pages_modified = 0
    pages_detail = []

    with pikepdf.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages):
            p_num = idx + 1
            # Obtener MediaBox
            if "/MediaBox" in page:
                mbox = [float(x) for x in page.MediaBox]
            else:
                # Inherit o default a A4 si no existe
                mbox = [0.0, 0.0, 595.28, 841.89]

            m_llx, m_lly, m_urx, m_ury = mbox
            m_w_pt = abs(m_urx - m_llx)
            m_h_pt = abs(m_ury - m_lly)
            m_w_mm = pt_to_mm(m_w_pt)
            m_h_mm = pt_to_mm(m_h_pt)

            has_explicit_trim = False
            if "/TrimBox" in page:
                tbox = [float(x) for x in page.TrimBox]
                # Distinto de MediaBox por más de 1 pt
                if (abs(tbox[0] - m_llx) > 1.0 or abs(tbox[1] - m_lly) > 1.0 or
                    abs(tbox[2] - m_urx) > 1.0 or abs(tbox[3] - m_ury) > 1.0):
                    has_explicit_trim = True

            action_taken = ""

            if has_explicit_trim:
                # Caso 1: Mantener TrimBox explícito, ajustar BleedBox a 3 mm
                t_llx, t_lly, t_urx, t_ury = [float(x) for x in page.TrimBox]
                b_llx = t_llx - bleed_pt
                b_lly = t_lly - bleed_pt
                b_urx = t_urx + bleed_pt
                b_ury = t_ury + bleed_pt

                # MediaBox debe contener BleedBox
                new_m_llx = min(m_llx, b_llx)
                new_m_lly = min(m_lly, b_lly)
                new_m_urx = max(m_urx, b_urx)
                new_m_ury = max(m_ury, b_ury)

                page.BleedBox = [b_llx, b_lly, b_urx, b_ury]
                page.MediaBox = [new_m_llx, new_m_lly, new_m_urx, new_m_ury]
                action_taken = "BleedBox ajustado a +3 mm respecto a TrimBox existente"
            else:
                # Caso 2: No hay TrimBox explícito
                # Comprobar si MediaBox ya incluye sangrado (tamaño estándar + 2*sangrado)
                already_has_bleed_space = False
                for name, std_w, std_h in STANDARD_PAGE_SIZES_MM:
                    if _matches_size(m_w_mm, m_h_mm, std_w + (2 * target_bleed_mm), std_h + (2 * target_bleed_mm)):
                        already_has_bleed_space = True
                        break

                if already_has_bleed_space:
                    # Insetar TrimBox a 3 mm hacia adentro
                    t_llx = m_llx + bleed_pt
                    t_lly = m_lly + bleed_pt
                    t_urx = m_urx - bleed_pt
                    t_ury = m_ury - bleed_pt

                    page.TrimBox = [t_llx, t_lly, t_urx, t_ury]
                    page.BleedBox = [m_llx, m_lly, m_urx, m_ury]
                    action_taken = "TrimBox calculado hacia adentro (el lienzo ya contenía sangrado)"
                else:
                    # El MediaBox es el corte neto: definir TrimBox igual al neto y expandir BleedBox +3 mm
                    t_llx, t_lly, t_urx, t_ury = m_llx, m_lly, m_urx, m_ury
                    b_llx = t_llx - bleed_pt
                    b_lly = t_lly - bleed_pt
                    b_urx = t_urx + bleed_pt
                    b_ury = t_ury + bleed_pt

                    page.TrimBox = [t_llx, t_lly, t_urx, t_ury]
                    page.BleedBox = [b_llx, b_lly, b_urx, b_ury]
                    page.MediaBox = [b_llx, b_lly, b_urx, b_ury]
                    action_taken = "TrimBox asignado a formato neto y BleedBox expandido a +3 mm"

            # Si existe CropBox, asegurar que abarque el BleedBox
            if "/CropBox" in page:
                page.CropBox = page.MediaBox

            pages_modified += 1
            pages_detail.append({
                "page": p_num,
                "action": action_taken,
                "trim_box": [round(float(x), 2) for x in page.TrimBox],
                "bleed_box": [round(float(x), 2) for x in page.BleedBox],
                "media_box": [round(float(x), 2) for x in page.MediaBox]
            })

        # Guardar en output_path
        pdf.save(output_path)

    return {
        "status": "success",
        "pages_modified": pages_modified,
        "bleed_mm": target_bleed_mm,
        "details": pages_detail
    }

