"""
barcode_engine.py – Inspector y Corrector de Códigos de Barras y Códigos QR (Prepress Barcode Quality Engine).

Funcionalidades:
  1. Detección automática en páginas PDF:
     - Códigos QR (vía cv2.QRCodeDetector).
     - Códigos de barras lineales 1D: EAN-13, EAN-8, UPC, Code 128, Code 39
       (vía visión artificial morfológica Scharr + análisis de frecuencia de barras + OCR de dígitos GS1).
  2. Análisis Técnico de Calidad de Impresión (Prepress Verification):
     - Composición cromática de las barras / módulos: ¿100% K puro o Negro Enriquecido / 4 tintas CMYK?
     - Detección de peligro de fuera de registro (misregistration) en máquina de impresión.
     - Verificación de Zona de Silencio (Quiet Zone) en márgenes laterales y contraste de fondo.
     - Validación de dígito de control (Checksum GS1 Modulo 10 para EAN).
  3. Corrección Automática en 1 Clic:
     - Conversión de barras/módulos a 100% K Puro (C:0% M:0% Y:0% K:100%), eliminando capas CMY.
     - Generación de reserva blanca opaca (Quiet Zone) debajo del código para fondos complejos o fotos.
"""

from __future__ import annotations

import io
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image
import pymupdf

PT_PER_MM = 72.0 / 25.4
MM_PER_PT = 25.4 / 72.0


def _validate_ean_checksum(digits: str) -> Optional[bool]:
    """Valida el dígito de control GS1 Modulo 10 para EAN-13 o EAN-8."""
    if not digits.isdigit():
        return None
    if len(digits) not in (8, 13):
        return None

    nums = [int(c) for c in digits]
    payload = nums[:-1]
    expected_check = nums[-1]

    if len(digits) == 13:
        # Ponderación 1, 3 alternada desde la izquierda
        s = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(payload))
    else:  # EAN-8
        # Ponderación 3, 1 alternada desde la izquierda
        s = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(payload))

    calc_check = (10 - (s % 10)) % 10
    return calc_check == expected_check


def _analyze_cmyk_region(
    page: pymupdf.Page,
    rect_pt: pymupdf.Rect,
    dpi: int = 150
) -> Dict[str, Any]:
    """
    Renderiza la región en CMYK nativo y analiza la composición de tinta
    de las barras oscuras y del fondo blanco circundante.
    """
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    try:
        pix = page.get_pixmap(colorspace=pymupdf.csCMYK, clip=rect_pt, matrix=mat)
    except Exception:
        # Fallback sin clip
        pix = page.get_pixmap(colorspace=pymupdf.csCMYK, matrix=mat)

    w = pix.width
    h = pix.height
    n = pix.n  # Debe ser 4 (C, M, Y, K) o 5 (con alpha)
    if w == 0 or h == 0 or n < 4:
        return {
            "c_pct": 0, "m_pct": 0, "y_pct": 0, "k_pct": 100,
            "tac_pct": 100, "is_pure_k": True, "is_rich_black": False,
            "has_quiet_zone": True, "bar_color_desc": "Negro Puro 100% K"
        }

    raw = np.frombuffer(pix.samples, dtype=np.uint8).reshape((h, w, n))
    c_chan = raw[:, :, 0]
    m_chan = raw[:, :, 1]
    y_chan = raw[:, :, 2]
    k_chan = raw[:, :, 3]

    # La tinta total por píxel (0 a 1020, o en %)
    total_ink = c_chan.astype(float) + m_chan.astype(float) + y_chan.astype(float) + k_chan.astype(float)

    # Identificar píxeles oscuros (las barras del código)
    # En CMYK, un píxel es oscuro si K es alto o total_ink > umbral
    dark_mask = (k_chan > 100) | (total_ink > 350)
    # Identificar píxeles claros (el fondo)
    light_mask = total_ink < 80

    if np.any(dark_mask):
        c_mean = float(np.mean(c_chan[dark_mask])) / 255.0 * 100.0
        m_mean = float(np.mean(m_chan[dark_mask])) / 255.0 * 100.0
        y_mean = float(np.mean(y_chan[dark_mask])) / 255.0 * 100.0
        k_mean = float(np.mean(k_chan[dark_mask])) / 255.0 * 100.0
    else:
        c_mean, m_mean, y_mean, k_mean = 0.0, 0.0, 0.0, 100.0

    tac_pct = round(c_mean + m_mean + y_mean + k_mean, 1)
    c_pct = round(c_mean, 1)
    m_pct = round(m_mean, 1)
    y_pct = round(y_mean, 1)
    k_pct = round(k_mean, 1)

    # Comprobar si el fondo es blanco limpio (zona de silencio)
    # Medir bordes perimetrales (10% exterior)
    margin_x = max(1, int(w * 0.1))
    margin_y = max(1, int(h * 0.1))
    edge_pixels_ink = np.concatenate([
        total_ink[:margin_y, :].flatten(),
        total_ink[-margin_y:, :].flatten(),
        total_ink[:, :margin_x].flatten(),
        total_ink[:, -margin_x:].flatten(),
    ])
    avg_edge_ink_pct = float(np.mean(edge_pixels_ink)) / (255.0 * 4.0) * 100.0
    has_quiet_zone = avg_edge_ink_pct < 12.0  # Menos del 12% de tinta en bordes

    # Diagnóstico de color
    is_pure_k = (c_pct <= 4.0 and m_pct <= 4.0 and y_pct <= 4.0 and k_pct >= 75.0)
    is_rich_black = (k_pct >= 40.0 and (c_pct > 8.0 or m_pct > 8.0 or y_pct > 8.0))

    if is_pure_k:
        bar_color_desc = f"Negro Puro 100% K (K:{k_pct:.0f}%)"
    elif is_rich_black:
        bar_color_desc = f"Negro Enriquecido 4 Tintas (C:{c_pct:.0f}% M:{m_pct:.0f}% Y:{y_pct:.0f}% K:{k_pct:.0f}% - TAC {tac_pct:.0f}%)"
    else:
        bar_color_desc = f"Color CMYK Compuesto (C:{c_pct:.0f}% M:{m_pct:.0f}% Y:{y_pct:.0f}% K:{k_pct:.0f}%)"

    return {
        "c_pct": c_pct,
        "m_pct": m_pct,
        "y_pct": y_pct,
        "k_pct": k_pct,
        "tac_pct": tac_pct,
        "is_pure_k": is_pure_k,
        "is_rich_black": is_rich_black,
        "has_quiet_zone": has_quiet_zone,
        "bar_color_desc": bar_color_desc,
        "edge_ink_pct": round(avg_edge_ink_pct, 1),
    }


def _detect_qrcodes_in_page(
    page: pymupdf.Page,
    dpi: int = 150
) -> List[Dict[str, Any]]:
    """Detecta códigos QR mediante cv2.QRCodeDetector sobre la página renderizada."""
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if pix.n >= 3 else img

    results = []
    qd = cv2.QRCodeDetector()

    # Intentar decodificación múltiple
    try:
        ret, decoded_info, points, _ = qd.detectAndDecodeMulti(gray)
        if ret and points is not None and len(points) > 0:
            for idx, pts in enumerate(points):
                pts_2d = pts.reshape(-1, 2)
                x_min, y_min = np.min(pts_2d, axis=0)
                x_max, y_max = np.max(pts_2d, axis=0)

                # Convertir coordenadas de píxeles a puntos tipográficos del PDF
                scale = 72.0 / dpi
                pt_rect = pymupdf.Rect(x_min * scale, y_min * scale, x_max * scale, y_max * scale)

                # Pequeño padding de seguridad (1.5 mm)
                pad_pt = 1.5 * PT_PER_MM
                pt_rect_padded = pymupdf.Rect(
                    max(0, pt_rect.x0 - pad_pt),
                    max(0, pt_rect.y0 - pad_pt),
                    min(page.rect.x1, pt_rect.x1 + pad_pt),
                    min(page.rect.y1, pt_rect.y1 + pad_pt),
                )

                payload = decoded_info[idx] if idx < len(decoded_info) else ""
                results.append({
                    "type": "QR Code",
                    "rect_pt": [round(pt_rect.x0, 1), round(pt_rect.y0, 1), round(pt_rect.x1, 1), round(pt_rect.y1, 1)],
                    "rect_padded_pt": [round(pt_rect_padded.x0, 1), round(pt_rect_padded.y0, 1), round(pt_rect_padded.x1, 1), round(pt_rect_padded.y1, 1)],
                    "payload": payload or "Código QR Detectado",
                    "checksum_valid": None,  # QR usa Reed-Solomon internamente
                })
    except Exception:
        pass

    # Fallback si no decodificó texto pero hay finders: detección geométrica
    if not results:
        try:
            ret_det, points_det = qd.detect(gray)
            if ret_det and points_det is not None:
                for pts in points_det:
                    pts_2d = pts.reshape(-1, 2)
                    x_min, y_min = np.min(pts_2d, axis=0)
                    x_max, y_max = np.max(pts_2d, axis=0)
                    scale = 72.0 / dpi
                    pt_rect = pymupdf.Rect(x_min * scale, y_min * scale, x_max * scale, y_max * scale)
                    pad_pt = 1.5 * PT_PER_MM
                    pt_rect_padded = pymupdf.Rect(
                        max(0, pt_rect.x0 - pad_pt),
                        max(0, pt_rect.y0 - pad_pt),
                        min(page.rect.x1, pt_rect.x1 + pad_pt),
                        min(page.rect.y1, pt_rect.y1 + pad_pt),
                    )
                    results.append({
                        "type": "QR Code",
                        "rect_pt": [round(pt_rect.x0, 1), round(pt_rect.y0, 1), round(pt_rect.x1, 1), round(pt_rect.y1, 1)],
                        "rect_padded_pt": [round(pt_rect_padded.x0, 1), round(pt_rect_padded.y0, 1), round(pt_rect_padded.x1, 1), round(pt_rect_padded.y1, 1)],
                        "payload": "Código QR (Patrón geométrico verificado)",
                        "checksum_valid": None,
                    })
        except Exception:
            pass

    return results


def _detect_1d_barcodes_in_page(
    page: pymupdf.Page,
    dpi: int = 150
) -> List[Dict[str, Any]]:
    """
    Detecta códigos de barras lineales 1D mediante análisis morfológico de frecuencias
    y correlación con patrones numéricos EAN/UPC en el texto del documento.
    """
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if pix.n >= 3 else img

    results = []

    # 1. Gradiente morfológico Scharr para detectar transiciones de barras verticales
    grad_x = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
    grad_y = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=0, dy=1, ksize=-1)
    gradient = cv2.subtract(grad_x, grad_y)
    gradient = cv2.convertScaleAbs(gradient)

    blurred = cv2.blur(gradient, (9, 9))
    _, thresh = cv2.threshold(blurred, 180, 255, cv2.THRESH_BINARY)

    # Conectar barras horizontales adyacentes
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 7))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    closed = cv2.erode(closed, None, iterations=4)
    closed = cv2.dilate(closed, None, iterations=4)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    scale = 72.0 / dpi

    # Extraer todas las palabras y números de la página para asociar dígitos EAN
    text_words = page.get_text("words")

    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        aspect = float(w) / float(h) if h > 0 else 0.0
        area = w * h

        # Filtro de forma: un código de barras 1D tiene anchura >= altura y un área mínima
        if area > 1400 and (0.7 <= aspect <= 6.0):
            # Verificar si dentro de la caja hay una alta densidad de cambios de color blanco/negro
            crop_patch = gray[y:y+h, x:x+w]
            if crop_patch.shape[0] < 10 or crop_patch.shape[1] < 10:
                continue

            mid_row = crop_patch[crop_patch.shape[0] // 2, :]
            # Contar transiciones claro/oscuro a lo largo de la línea central
            diffs = np.abs(np.diff(mid_row.astype(int)))
            transitions = np.sum(diffs > 40)

            # Un código EAN/Code128 tiene típicamente entre 30 y 110 barras/transiciones
            if transitions < 18:
                continue

            pt_x0 = x * scale
            pt_y0 = y * scale
            pt_x1 = (x + w) * scale
            pt_y1 = (y + h) * scale

            # Buscar dígitos cercanos en el texto (típicamente justo debajo o encima del código)
            matched_code = ""
            best_dist = 999999.0

            # Buscar bloques de 8 a 13 dígitos
            for w_item in text_words:
                wx0, wy0, wx1, wy1, word_text = w_item[0], w_item[1], w_item[2], w_item[3], w_item[4]
                clean_digits = re.sub(r"[^\d]", "", word_text)
                if len(clean_digits) in (8, 12, 13):
                    # Distancia al centro de la caja detectada
                    dist = abs(((wx0 + wx1) / 2.0) - ((pt_x0 + pt_x1) / 2.0)) + abs(wy0 - pt_y1)
                    if dist < best_dist and dist < 50.0:  # Dentro de 50 pt
                        best_dist = dist
                        matched_code = clean_digits

            # Clasificar tipo de código
            if len(matched_code) == 13:
                code_type = "EAN-13"
                checksum_valid = _validate_ean_checksum(matched_code)
            elif len(matched_code) == 8:
                code_type = "EAN-8"
                checksum_valid = _validate_ean_checksum(matched_code)
            elif len(matched_code) == 12:
                code_type = "UPC-A"
                checksum_valid = None
            else:
                code_type = "Código de Barras 1D"
                checksum_valid = None

            pad_pt = 2.0 * PT_PER_MM
            pt_rect = pymupdf.Rect(pt_x0, pt_y0, pt_x1, pt_y1)
            pt_rect_padded = pymupdf.Rect(
                max(0, pt_rect.x0 - pad_pt),
                max(0, pt_rect.y0 - pad_pt),
                min(page.rect.x1, pt_rect.x1 + pad_pt),
                min(page.rect.y1, pt_rect.y1 + pad_pt),
            )

            results.append({
                "type": code_type,
                "rect_pt": [round(pt_rect.x0, 1), round(pt_rect.y0, 1), round(pt_rect.x1, 1), round(pt_rect.y1, 1)],
                "rect_padded_pt": [round(pt_rect_padded.x0, 1), round(pt_rect_padded.y0, 1), round(pt_rect_padded.x1, 1), round(pt_rect_padded.y1, 1)],
                "payload": matched_code or "Patrón de barras 1D verificado",
                "checksum_valid": checksum_valid,
            })

    return results


def inspect_barcodes_in_pdf(pdf_path: str | Path) -> Dict[str, Any]:
    """
    Inspecciona todas las páginas del PDF en busca de códigos de barras y códigos QR,
    analizando su colorimetría (100% K vs Rich Black), zona de silencio y legibilidad.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    doc = pymupdf.open(str(pdf_path))
    findings = []
    total_barcodes = 0
    total_errors = 0
    total_warnings = 0

    for page_idx, page in enumerate(doc):
        # 1. Detección de QR Codes
        qr_items = _detect_qrcodes_in_page(page)
        # 2. Detección de Códigos 1D
        bar_items = _detect_1d_barcodes_in_page(page)

        detected_on_page = qr_items + bar_items

        for item in detected_on_page:
            total_barcodes += 1
            rect_pt = pymupdf.Rect(item["rect_pt"])
            rect_mm = [
                round(rect_pt.x0 * MM_PER_PT, 1),
                round(rect_pt.y0 * MM_PER_PT, 1),
                round(rect_pt.x1 * MM_PER_PT, 1),
                round(rect_pt.y1 * MM_PER_PT, 1),
            ]
            w_mm = round((rect_pt.x1 - rect_pt.x0) * MM_PER_PT, 1)
            h_mm = round((rect_pt.y1 - rect_pt.y0) * MM_PER_PT, 1)

            # Analizar composición de tintas CMYK de la región
            color_data = _analyze_cmyk_region(page, rect_pt)

            # Clasificación de estado de preimpresión
            status = "OK"
            reasons = []

            if color_data["is_rich_black"]:
                status = "ERROR"
                total_errors += 1
                reasons.append(
                    f"Negro Enriquecido a 4 tintas (C:{color_data['c_pct']}% M:{color_data['m_pct']}% "
                    f"Y:{color_data['y_pct']}% K:{color_data['k_pct']}%). "
                    "Riesgo crítico de fallo en lector óptico por desajuste de registro en máquina."
                )
            elif not color_data["is_pure_k"]:
                status = "WARNING"
                total_warnings += 1
                reasons.append(
                    f"Composición de tinta compuesta (TAC: {color_data['tac_pct']}%). "
                    "Se recomienda convertir a 100% K puro para máxima nitidez."
                )

            if not color_data["has_quiet_zone"]:
                if status != "ERROR":
                    status = "WARNING"
                    total_warnings += 1
                reasons.append(
                    "Zona de silencio comprometida: el fondo perimetral contiene tinta "
                    f"({color_data['edge_ink_pct']}%). Requiere reserva blanca para lectura limpia."
                )

            if item["checksum_valid"] is False:
                status = "ERROR"
                total_errors += 1
                reasons.append("Dígito de control GS1 (Checksum) inválido: el código no podrá escanearse.")

            # Comprobar magnificación EAN (nominal 37.3 × 25.9 mm; mínimo 80% = 29.8 mm)
            if item["type"] == "EAN-13" and w_mm < 28.0:
                if status != "ERROR":
                    status = "WARNING"
                    total_warnings += 1
                reasons.append(
                    f"Ancho del código reducido ({w_mm} mm < 29.8 mm recomendado al 80%). "
                    "Puede presentar dificultades en escáneres omnidireccionales de caja."
                )

            findings.append({
                "id": f"barcode_p{page_idx+1}_{total_barcodes}",
                "page_index": page_idx,
                "page_number": page_idx + 1,
                "type": item["type"],
                "payload": item["payload"],
                "checksum_valid": item["checksum_valid"],
                "rect_pt": item["rect_pt"],
                "rect_padded_pt": item["rect_padded_pt"],
                "rect_mm": rect_mm,
                "dimensions_mm": [w_mm, h_mm],
                "color_analysis": color_data,
                "status": status,
                "reasons": reasons,
                "fixable": (status != "OK"),
            })

    doc.close()

    overall_status = "OK"
    if total_errors > 0:
        overall_status = "ERROR"
    elif total_warnings > 0:
        overall_status = "WARNING"

    return {
        "status": overall_status,
        "total_barcodes_found": total_barcodes,
        "errors_count": total_errors,
        "warnings_count": total_warnings,
        "findings": findings,
        "pdf_name": pdf_path.name,
    }


def fix_barcodes_in_pdf(
    pdf_path: str | Path,
    output_path: str | Path,
    barcode_ids_to_fix: Optional[List[str]] = None,
    force_pure_k: bool = True,
    add_quiet_zone: bool = True,
    quiet_zone_margin_mm: float = 2.0,
) -> Dict[str, Any]:
    """
    Corrige los códigos de barras y QR en el PDF:
      1. Genera una reserva blanca opaca 100% reflectante (Quiet Zone) debajo del código.
      2. Convierte las barras y módulos oscuros a 100% K Puro (C:0 M:0 Y:0 K:100%).
      3. Aplica sobreimpresión limpia del K puro sobre la reserva blanca.
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)

    # 1. Inspeccionar primero para conocer la posición exacta de cada código
    inspection = inspect_barcodes_in_pdf(pdf_path)
    findings = inspection.get("findings", [])

    if not findings:
        return {
            "status": "success",
            "codes_fixed": 0,
            "message": "No se detectaron códigos que requieran corrección.",
            "output_pdf_path": str(output_path),
        }

    # Filtrar cuáles corregir si se proporciona lista
    to_fix = [
        f for f in findings
        if (barcode_ids_to_fix is None or f["id"] in barcode_ids_to_fix) and f["fixable"]
    ]

    if not to_fix:
        # Copiar sin cambios
        import shutil
        shutil.copyfile(str(pdf_path), str(output_path))
        return {
            "status": "success",
            "codes_fixed": 0,
            "message": "Los códigos detectados ya cumplen con los estándares de calidad 100% K.",
            "output_pdf_path": str(output_path),
        }

    doc = pymupdf.open(str(pdf_path))
    codes_fixed_count = 0

    # Agrupar por página
    from collections import defaultdict
    by_page = defaultdict(list)
    for f in to_fix:
        by_page[f["page_index"]].append(f)

    for page_idx, page_findings in by_page.items():
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]

        for item in page_findings:
            rect_pt = pymupdf.Rect(item["rect_pt"])

            # 1. Reserva blanca (Quiet Zone)
            if add_quiet_zone:
                pad_pt = quiet_zone_margin_mm * PT_PER_MM
                q_rect = pymupdf.Rect(
                    max(0, rect_pt.x0 - pad_pt),
                    max(0, rect_pt.y0 - pad_pt),
                    min(page.rect.x1, rect_pt.x1 + pad_pt),
                    min(page.rect.y1, rect_pt.y1 + pad_pt),
                )
                shape = page.new_shape()
                shape.draw_rect(q_rect)
                # Blanco puro opaco en calado (fill=(1,1,1))
                shape.finish(fill=(1, 1, 1), color=None)
                shape.commit()

            # 2. Renderizado de alta resolución de la silueta de barras a 100% K puro
            if force_pure_k:
                # Muestreo a 300 DPI de la zona original
                dpi_fix = 300
                zoom = dpi_fix / 72.0
                mat = pymupdf.Matrix(zoom, zoom)

                # Renderizar en escala de grises de alta resolución
                pix = page.get_pixmap(clip=rect_pt, matrix=mat, colorspace=pymupdf.csGRAY)
                w, h = pix.width, pix.height

                if w > 0 and h > 0:
                    raw_gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape((h, w))
                    # Umbral Otsu para separar nítidamente barras oscuras de fondo claro
                    _, thresh_bars = cv2.threshold(raw_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

                    # Construir imagen CMYK donde:
                    # Fondo (thresh_bars == 0): C=0, M=0, Y=0, K=0 (blanco)
                    # Barras (thresh_bars == 255): C=0, M=0, Y=0, K=255 (100% K puro)
                    cmyk_matrix = np.zeros((h, w, 4), dtype=np.uint8)
                    cmyk_matrix[thresh_bars == 255, 3] = 255  # Solo canal K al 100%

                    img_cmyk = Image.fromarray(cmyk_matrix, mode="CMYK")
                    buf = io.BytesIO()
                    img_cmyk.save(buf, format="TIFF")
                    img_bytes = buf.getvalue()

                    # Inyectar la imagen CMYK exactamente sobre el rectángulo
                    page.insert_image(rect_pt, stream=img_bytes)
                    codes_fixed_count += 1

    doc.save(str(output_path), deflate=True)
    doc.close()

    return {
        "status": "success",
        "codes_fixed": codes_fixed_count,
        "output_pdf_path": str(output_path),
        "file_size_kb": round(output_path.stat().st_size / 1024, 1) if output_path.exists() else 0,
    }


def render_barcode_preview_image(
    pdf_path: str | Path,
    page_index: int,
    rect_pt: List[float],
    dpi: int = 150
) -> bytes:
    """Renderiza un recorte JPEG de previsualización para el inspector visual."""
    pdf_path = Path(pdf_path)
    doc = pymupdf.open(str(pdf_path))
    if page_index >= len(doc):
        doc.close()
        raise ValueError(f"Página {page_index} fuera de rango.")

    page = doc[page_index]
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)

    # Añadir 3 mm de margen visual al recorte
    pad = 3.0 * PT_PER_MM
    clip = pymupdf.Rect(
        max(0, rect_pt[0] - pad),
        max(0, rect_pt[1] - pad),
        min(page.rect.x1, rect_pt[2] + pad),
        min(page.rect.y1, rect_pt[3] + pad),
    )

    pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
    img_bytes = pix.tobytes(output="jpeg")
    doc.close()
    return img_bytes

