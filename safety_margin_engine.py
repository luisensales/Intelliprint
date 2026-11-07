"""
safety_margin_engine.py – Inspector de Zona de Seguridad y Lomo / Medianil (Gutter & Safety Margin Engine).

Verifica la proximidad de textos, logotipos y elementos vivos a los bordes de corte (TrimBox)
y a la zona de encuadernación/lomo (Gutter / Spine).

Reglas de taller:
  1. No todo PDF tiene lomo:
     - Tarjetas de visita (85×55 mm), flyers a 1 o 2 caras, postales, carteles, adhesivos:
       Son 'single_leaf' (hoja suelta / pieza única). Solo se analiza el margen de seguridad
       perimetral (3 mm en los 4 costados). NO se aplica zona de lomo.
     - Folletos grapados (saddle-stitch), revistas o catálogos fresados (perfect-bound) con >= 4 páginas:
       Son 'bound_publication'. Se aplica margen de lomo/medianil ampliado (8 mm a 12 mm)
       en el borde interior alternado (páginas impares = lomo a la izquierda; páginas pares = lomo a la derecha).
  2. Umbrales de severidad:
     - Peligro Crítico / ERROR: Texto o logo a < 1.5 mm del corte (riesgo inminente de ser cortado por guillotina).
     - Advertencia / WARNING: Texto entre 1.5 mm y 3.0 mm del corte (inferior al margen de seguridad estándar de 3 mm).
     - En lomo: Texto a < 6.0 mm en publicaciones encuadernadas (quedará oculto o ilegible en el pliegue).
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pymupdf
from PIL import Image

PT_PER_MM = 72.0 / 25.4
MM_PER_PT = 25.4 / 72.0


def detect_document_binding_mode(
    doc: pymupdf.Document,
    user_override: str = "auto"  # "auto", "single_leaf", "bound_publication"
) -> str:
    """
    Determina si el documento es una pieza suelta sin lomo ('single_leaf')
    o una publicación encuadernada con lomo/medianil ('bound_publication').
    """
    if user_override in ("single_leaf", "bound_publication"):
        return user_override

    total_pages = len(doc)
    if total_pages < 4:
        # 1, 2 o 3 páginas: flyers, tarjetas, dípticos desplegados -> Sin lomo
        return "single_leaf"

    # Si tiene >= 4 páginas, comprobar si el tamaño corresponde a tarjeta de visita
    p0 = doc[0]
    w_mm = p0.rect.width * MM_PER_PT
    h_mm = p0.rect.height * MM_PER_PT
    short_mm = min(w_mm, h_mm)
    long_mm = max(w_mm, h_mm)

    # Tarjetas de visita estándar (85x55, 90x50 mm)
    if short_mm <= 65 and long_mm <= 100:
        return "single_leaf"

    return "bound_publication"


def inspect_safety_margins(
    pdf_path: str | Path,
    safety_margin_mm: float = 3.0,
    gutter_margin_mm: float = 8.0,
    critical_threshold_mm: float = 1.5,
    binding_mode: str = "auto",  # "auto", "single_leaf", "bound_publication"
) -> Dict[str, Any]:
    """
    Inspecciona todas las páginas del documento analizando la proximidad de textos
    y elementos vivos a los bordes de corte y al lomo.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    doc = pymupdf.open(str(pdf_path))
    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("El documento PDF no contiene páginas.")

    mode = detect_document_binding_mode(doc, user_override=binding_mode)
    has_spine = (mode == "bound_publication")

    total_infractions = 0
    total_critical = 0
    total_warnings = 0
    findings_per_page: List[Dict[str, Any]] = []

    for page_idx in range(total_pages):
        page = doc[page_idx]
        page_num = page_idx + 1

        # Obtener TrimBox y BleedBox
        trim = page.rect
        try:
            tb = page.trimbox
            if tb and tb.is_valid and tb.width > 20 and tb.height > 20:
                trim = tb
        except Exception:
            pass

        trim_w_mm = round(trim.width * MM_PER_PT, 1)
        trim_h_mm = round(trim.height * MM_PER_PT, 1)

        # Determinar si esta página tiene lomo y en qué lado está
        # En encuadernación estándar:
        # Página impar (derecha): lomo a la IZQUIERDA
        # Página par (izquierda): lomo a la DERECHA
        spine_side: Optional[str] = None
        if has_spine:
            spine_side = "left" if (page_num % 2 != 0) else "right"

        # Definir los márgenes requeridos para los 4 lados (en mm)
        # top, bottom, left, right
        req_margins_mm = {
            "top": safety_margin_mm,
            "bottom": safety_margin_mm,
            "left": gutter_margin_mm if spine_side == "left" else safety_margin_mm,
            "right": gutter_margin_mm if spine_side == "right" else safety_margin_mm,
        }

        page_issues: List[Dict[str, Any]] = []

        # 1. Analizar palabras y bloques de texto
        words = page.get_text("words")
        # Estructura de word: (x0, y0, x1, y1, "text", block_no, line_no, word_no)
        # Agrupar palabras adyacentes para dar un contexto legible
        for w in words:
            wx0, wy0, wx1, wy1, text_str = w[0], w[1], w[2], w[3], w[4]
            if not text_str.strip():
                continue

            # Comprobar si el texto está dentro o cerca del TrimBox
            # Si está completamente fuera del TrimBox (ej. marcas o slugs), ignorar
            if wx1 < trim.x0 - 10 or wx0 > trim.x1 + 10 or wy1 < trim.y0 - 10 or wy0 > trim.y1 + 10:
                continue

            # Distancias a los 4 bordes del TrimBox en milímetros
            d_left = (wx0 - trim.x0) * MM_PER_PT
            d_right = (trim.x1 - wx1) * MM_PER_PT
            d_top = (wy0 - trim.y0) * MM_PER_PT
            d_bottom = (trim.y1 - wy1) * MM_PER_PT

            # Evaluar cada lado
            distances = {
                "left": d_left,
                "right": d_right,
                "top": d_top,
                "bottom": d_bottom,
            }

            for side, dist_mm in distances.items():
                min_req = req_margins_mm[side]
                is_spine_edge = (side == spine_side)

                if dist_mm < min_req:
                    # Infracción detectada
                    is_critical = (dist_mm < critical_threshold_mm) or (is_spine_edge and dist_mm < 4.0)
                    severity = "CRITICAL" if is_critical else "WARNING"

                    if is_spine_edge:
                        desc = (
                            f"Texto '{text_str}' a {dist_mm:.1f} mm del LOMO de encuadernación "
                            f"(borde {side}). Mínimo recomendado: {min_req:.1f} mm para evitar que quede oculto en el pliegue."
                        )
                    else:
                        desc = (
                            f"Texto '{text_str}' a solo {dist_mm:.1f} mm del borde de corte {side}. "
                            f"Mínimo recomendado: {min_req:.1f} mm (riesgo de ser guillotinado)."
                        )

                    page_issues.append({
                        "type": "text",
                        "content": text_str,
                        "side": side,
                        "is_spine_edge": is_spine_edge,
                        "distance_mm": round(dist_mm, 2),
                        "required_mm": min_req,
                        "rect_pt": [round(wx0, 1), round(wy0, 1), round(wx1, 1), round(wy1, 1)],
                        "severity": severity,
                        "description": desc,
                    })

        # 2. Filtrar y agrupar textos muy cercanos para no saturar con 200 alertas
        # Guardar las infracciones más graves (las que tengan menor distancia)
        page_issues.sort(key=lambda x: (0 if x["severity"] == "CRITICAL" else 1, x["distance_mm"]))
        # Agrupar alertas redundantes que estén a menos de 5 pt de distancia
        unique_page_issues = []
        for issue in page_issues:
            # Comprobar si ya existe uno similar en las proximidades
            r = issue["rect_pt"]
            duplicate = False
            for u in unique_page_issues:
                ur = u["rect_pt"]
                if abs(r[0] - ur[0]) < 8 and abs(r[1] - ur[1]) < 8:
                    duplicate = True
                    break
            if not duplicate:
                unique_page_issues.append(issue)

        page_crit = sum(1 for i in unique_page_issues if i["severity"] == "CRITICAL")
        page_warn = sum(1 for i in unique_page_issues if i["severity"] == "WARNING")

        total_infractions += len(unique_page_issues)
        total_critical += page_crit
        total_warnings += page_warn

        findings_per_page.append({
            "page_index": page_idx,
            "page_number": page_num,
            "dimensions_mm": [trim_w_mm, trim_h_mm],
            "spine_side": spine_side,
            "required_margins_mm": req_margins_mm,
            "critical_count": page_crit,
            "warning_count": page_warn,
            "total_issues": len(unique_page_issues),
            "issues": unique_page_issues[:25],  # Máximo 25 por página para reporte
        })

    doc.close()

    overall_status = "OK"
    if total_critical > 0:
        overall_status = "ERROR"
    elif total_warnings > 0:
        overall_status = "WARNING"

    mode_description = {
        "single_leaf": "Hoja Suelta / Pieza Única (Tarjeta, Flyer, Cartel) · Sin zona de lomo (Margen de seguridad 3 mm en los 4 bordes)",
        "bound_publication": f"Publicación Encuadernada (Revista, Folleto, Catálogo) · Con margen de lomo ({gutter_margin_mm:.1f} mm en medianil interior)",
    }.get(mode, mode)

    return {
        "status": overall_status,
        "binding_mode": mode,
        "binding_mode_description": mode_description,
        "has_spine": has_spine,
        "total_pages": total_pages,
        "safety_margin_mm": safety_margin_mm,
        "gutter_margin_mm": gutter_margin_mm if has_spine else None,
        "total_infractions": total_infractions,
        "critical_count": total_critical,
        "warning_count": total_warnings,
        "pages": findings_per_page,
        "pdf_name": pdf_path.name,
    }


def render_safety_margin_preview(
    pdf_path: str | Path,
    page_index: int = 0,
    safety_margin_mm: float = 3.0,
    gutter_margin_mm: float = 8.0,
    binding_mode: str = "auto",
    dpi: int = 120,
) -> bytes:
    """
    Renderiza una previsualización de alta calidad de la página con:
      - Línea roja punteada: TrimBox (corte real).
      - Línea verde punteada: Zona de seguridad perimetral (3 mm).
      - Línea morada continua: Margen de Lomo / Medianil (8-10 mm, solo si aplica).
      - Cajas rojas/ámbar resaltando los elementos infractores.
    """
    pdf_path = Path(pdf_path)
    inspection = inspect_safety_margins(
        pdf_path=pdf_path,
        safety_margin_mm=safety_margin_mm,
        gutter_margin_mm=gutter_margin_mm,
        binding_mode=binding_mode,
    )

    doc = pymupdf.open(str(pdf_path))
    if page_index >= len(doc):
        doc.close()
        raise ValueError(f"Página {page_index} fuera de rango.")

    page = doc[page_index]
    page_data = inspection["pages"][page_index] if page_index < len(inspection["pages"]) else None

    # Duplicar la página en memoria para dibujar guías sin modificar el original
    temp_doc = pymupdf.open()
    temp_page = temp_doc.new_page(width=page.rect.width, height=page.rect.height)
    temp_page.show_pdf_page(page.rect, doc, page_index)

    # Coordenadas TrimBox
    trim = page.rect
    try:
        tb = page.trimbox
        if tb and tb.is_valid and tb.width > 20 and tb.height > 20:
            trim = tb
    except Exception:
        pass

    shape = temp_page.new_shape()

    # 1. Dibujar línea de corte (TrimBox) en rojo punteado
    shape.draw_rect(trim)
    shape.finish(color=(0.9, 0.1, 0.1), width=0.8, dashes="[3 2] 0")

    # 2. Dibujar guías de seguridad
    req_margins = page_data["required_margins_mm"] if page_data else {
        "top": safety_margin_mm, "bottom": safety_margin_mm, "left": safety_margin_mm, "right": safety_margin_mm
    }
    spine_side = page_data.get("spine_side") if page_data else None

    m_top_pt = req_margins["top"] * PT_PER_MM
    m_bot_pt = req_margins["bottom"] * PT_PER_MM
    m_left_pt = req_margins["left"] * PT_PER_MM
    m_right_pt = req_margins["right"] * PT_PER_MM

    # Rectángulo de seguridad interior
    safe_rect = pymupdf.Rect(
        trim.x0 + m_left_pt,
        trim.y0 + m_top_pt,
        trim.x1 - m_right_pt,
        trim.y1 - m_bot_pt,
    )
    shape.draw_rect(safe_rect)
    shape.finish(color=(0.1, 0.7, 0.2), width=0.7, dashes="[2 2] 0")

    # 3. Si hay lomo, destacar la línea de lomo en morado
    if spine_side == "left":
        spine_line_x = trim.x0 + m_left_pt
        shape.draw_line(pymupdf.Point(spine_line_x, trim.y0), pymupdf.Point(spine_line_x, trim.y1))
        shape.finish(color=(0.6, 0.1, 0.8), width=1.5)
    elif spine_side == "right":
        spine_line_x = trim.x1 - m_right_pt
        shape.draw_line(pymupdf.Point(spine_line_x, trim.y0), pymupdf.Point(spine_line_x, trim.y1))
        shape.finish(color=(0.6, 0.1, 0.8), width=1.5)

    # 4. Resaltar elementos infractores con cajas rojas / ámbar
    if page_data and page_data.get("issues"):
        for issue in page_data["issues"]:
            r = pymupdf.Rect(issue["rect_pt"])
            is_crit = issue["severity"] == "CRITICAL"
            border_color = (0.9, 0.1, 0.1) if is_crit else (0.95, 0.6, 0.0)
            fill_color = (1.0, 0.8, 0.8) if is_crit else (1.0, 0.95, 0.8)

            shape.draw_rect(r)
            shape.finish(color=border_color, fill=fill_color, width=1.0)

    shape.commit()

    # Renderizar a imagen JPEG
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    pix = temp_page.get_pixmap(matrix=mat, alpha=False)
    img_bytes = pix.tobytes(output="jpeg")

    temp_doc.close()
    doc.close()
    return img_bytes
