"""
cip3_engine.py
==============
Motor de Cálculo de Cobertura de Tinta por Zonas y Generación CIP3 / PPF (Print Production Format)
para Preajuste de Tinteros en Máquina Offset y Digital.

Desarrollado para:
- CPIFP Salesianos Urnieta LHIPI
- CIFP Mendizabala LHII
- Departamento de Educación del Gobierno Vasco (Eusko Jaurlaritza)

Norma y Especificación Técnica:
- CIP3 / CIP4 Print Production Format (PPF) v3.0
- División estándar: 16, 24 o 32 llaves de tintero longitudinales (eje de cilindro)
- Estimación de consumo de tinta según superficie, tirada y peso de película (g/m²)
- Detección de zonas secas sin aporte de tinta (peligro de fricción/quemado de rodillos)
"""

from __future__ import annotations
import os
import time
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pymupdf
from security_limits import bounded_render_dpi
import numpy as np
from PIL import Image
from pdf_utils import atomic_output, iter_resources
from security_limits import MAX_RENDER_PIXELS, MAX_RENDER_EDGE
import pikepdf


# Factores de peso de capa de tinta estándar (g/m² a 100% de cobertura)
INK_FILM_WEIGHT = {
    "coated": 1.20,       # Papel estucado (Offset comercial estándar)
    "uncoated": 0.95,     # Papel no estucado / Offset natural (mayor absorción)
    "newspaper": 0.85,    # Papel prensa (rotativa)
    "carton": 1.30        # Cartoncillo para packaging
}


def calculate_ink_zone_coverage(
    pdf_path: str,
    page_number: int = 0,
    num_zones: int = 32,
    run_length: int = 1000,
    paper_type: str = "coated"
) -> Dict[str, Any]:
    """
    Calcula el porcentaje de cobertura de tinta CMYK por franjas longitudinales (zonas de tintero)
    a lo largo del ancho del pliego y estima el consumo total de tinta para la tirada especificada.
    
    Retorna un diccionario con:
    - Metadatos del pliego (ancho, alto en mm y pt, superficie en m²)
    - Coberturas medias globales por color (%)
    - Estimación de consumo en gramos y kilogramos (C, M, Y, K)
    - Desglose por zona (1 a num_zones): ancho, % de cobertura y % de apertura recomendada
    - Alertas técnicas de fricción en rodillos para zonas sin tinta
    """
    if num_zones not in (16, 24, 32):
        raise ValueError("Selecciona 16, 24 o 32 zonas de tintero.")
    if not 1 <= run_length <= 10_000_000:
        raise ValueError("La tirada debe estar entre 1 y 10.000.000 ejemplares.")
    with pymupdf.open(pdf_path) as doc:
        if not 0 <= page_number < len(doc):
            raise ValueError("Página de cálculo CIP3 fuera de rango.")
        page = doc[page_number]
        w_pt, h_pt = page.rect.width, page.rect.height
        pix = page.get_pixmap(colorspace=pymupdf.csCMYK,
                             dpi=bounded_render_dpi(page.rect, 72), alpha=False, annots=False)
    w_mm = round(w_pt * 25.4 / 72.0, 1)
    h_mm = round(h_pt * 25.4 / 72.0, 1)
    sheet_area_m2 = (w_pt * 0.000352778) * (h_pt * 0.000352778)

    img_h, img_w = pix.height, pix.width
    
    # Extraer array numpy uint8 (alto, ancho, 4 canales: C, M, Y, K)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((img_h, img_w, 4))
    
    # Calcular cobertura media global
    global_c = float(np.mean(arr[..., 0]) / 255.0 * 100.0)
    global_m = float(np.mean(arr[..., 1]) / 255.0 * 100.0)
    global_y = float(np.mean(arr[..., 2]) / 255.0 * 100.0)
    global_k = float(np.mean(arr[..., 3]) / 255.0 * 100.0)
    
    film_w = INK_FILM_WEIGHT.get(paper_type, 1.20)
    
    # Consumo en gramos = Área(m²) * (Cobertura / 100) * film_weight(g/m²) * tirada
    cons_c_g = sheet_area_m2 * (global_c / 100.0) * film_w * run_length
    cons_m_g = sheet_area_m2 * (global_m / 100.0) * film_w * run_length
    cons_y_g = sheet_area_m2 * (global_y / 100.0) * film_w * run_length
    cons_k_g = sheet_area_m2 * (global_k / 100.0) * film_w * run_length
    
    # División por zonas (de izquierda a derecha: x=0 a x=img_w)
    zones = []
    zone_px_w = img_w / float(num_zones)
    zone_mm_w = round(w_mm / float(num_zones), 2)
    columns = np.mean(arr, axis=0)
    integral = np.vstack((np.zeros((1, 4)), np.cumsum(columns, axis=0)))

    def integrated_at(position):
        index = min(int(position), img_w)
        return integral[index] + (position - index) * columns[min(index, img_w - 1)]
    
    for i in range(num_zones):
        x0, x1 = i * zone_px_w, min((i + 1) * zone_px_w, img_w)
        # Split boundary pixels proportionally, including pages narrower than 32 px.
        coverage = (integrated_at(x1) - integrated_at(x0)) / (x1 - x0) / 255 * 100
        zc, zm, zy, zk = map(float, coverage)
        
        # Apertura recomendada de llave de tintero (% opening):
        # Mínimo lubricante de 3.0% para evitar desgaste metal-metal de la cuchilla dosificadora
        # Ganancia progresiva para compensar transferencia de batería
        def calc_opening(cov: float) -> float:
            if cov <= 0.05:
                return 2.5
            return round(min(100.0, 3.5 + cov * 1.15), 1)

        op_c = calc_opening(zc)
        op_m = calc_opening(zm)
        op_y = calc_opening(zy)
        op_k = calc_opening(zk)
        
        x_start_mm = round(i * zone_mm_w, 1)
        x_end_mm = round((i + 1) * zone_mm_w, 1) if i < num_zones - 1 else w_mm
        
        zones.append({
            "zone_index": i + 1,
            "x_start_mm": x_start_mm,
            "x_end_mm": x_end_mm,
            "width_mm": zone_mm_w,
            "c_coverage": round(zc, 1),
            "m_coverage": round(zm, 1),
            "y_coverage": round(zy, 1),
            "k_coverage": round(zk, 1),
            "c_opening": op_c,
            "m_opening": op_m,
            "y_opening": op_y,
            "k_opening": op_k,
            "is_dry_friction_risk": False
        })
        
    # Detectar zonas de fricción seca (rodillos desprotegidos)
    # Si una zona tiene cobertura casi 0% mientras las contiguas tienen carga > 15%
    for i in range(num_zones):
        z = zones[i]
        total_cov = z["c_coverage"] + z["m_coverage"] + z["y_coverage"] + z["k_coverage"]
        if total_cov < 2.0:
            left_cov = (zones[i-1]["c_coverage"] + zones[i-1]["m_coverage"] + zones[i-1]["y_coverage"] + zones[i-1]["k_coverage"]) if i > 0 else 0
            right_cov = (zones[i+1]["c_coverage"] + zones[i+1]["m_coverage"] + zones[i+1]["y_coverage"] + zones[i+1]["k_coverage"]) if i < num_zones - 1 else 0
            if left_cov > 20.0 or right_cov > 20.0:
                z["is_dry_friction_risk"] = True

    return {
        "timestamp": datetime.now().isoformat(),
        "num_zones": num_zones,
        "run_length": run_length,
        "paper_type": paper_type,
        "paper_film_weight_g_m2": film_w,
        "sheet_info": {
            "width_mm": w_mm,
            "height_mm": h_mm,
            "width_pt": round(w_pt, 1),
            "height_pt": round(h_pt, 1),
            "area_m2": round(sheet_area_m2, 4),
            "zone_width_mm": zone_mm_w
        },
        "coverage_summary": {
            "c": round(global_c, 1),
            "m": round(global_m, 1),
            "y": round(global_y, 1),
            "k": round(global_k, 1),
            "total_cmyk": round(global_c + global_m + global_y + global_k, 1)
        },
        "ink_consumption": {
            "run_length": run_length,
            "c_g": round(cons_c_g, 1),
            "m_g": round(cons_m_g, 1),
            "y_g": round(cons_y_g, 1),
            "k_g": round(cons_k_g, 1),
            "total_g": round(cons_c_g + cons_m_g + cons_y_g + cons_k_g, 1),
            "c_kg": round(cons_c_g / 1000.0, 3),
            "m_kg": round(cons_m_g / 1000.0, 3),
            "y_kg": round(cons_y_g / 1000.0, 3),
            "k_kg": round(cons_k_g / 1000.0, 3),
            "total_kg": round((cons_c_g + cons_m_g + cons_y_g + cons_k_g) / 1000.0, 3)
        },
        "zones": zones
    }


# CIP3 PPF 3.0, sections 3.2, 3.4, 3.5 and 3.6:
# https://www.cip4.org/files/cip4/documents/CIP3%20PPF%20Spec%203.0.pdf
PPF_HEADER = b"%!PS-Adobe-3.0\n%%CIP3-File Version 3.0\n%%Creator: IntelliPrint PPF 3.0\n"


def is_current_ppf(path):
    """Invalidate the legacy files that contained invented ink-zone dictionaries."""
    try:
        with open(path, "rb") as stream:
            return stream.read(len(PPF_HEADER)) == PPF_HEADER
    except OSError:
        return False


def _ps_string(value):
    text = str(value)
    raw = text.encode("ascii") if text.isascii() else b"\xfe\xff" + text.encode("utf-16-be")
    # Escape every delimiter and non-printable byte, including CR and LF.
    return "(" + "".join(chr(b) if 32 <= b <= 126 and b not in (40, 41, 92)
                         else "\\%03o" % b for b in raw) + ")"


def _render_ppf_preview(page):
    """Render line art above 300 dpi in bounded tiles, then area-average to ~50.8 dpi."""
    rect = page.rect
    width = math.ceil(rect.width * 50.8 / 72)
    height = math.ceil(rect.height * 50.8 / 72)
    if width * height > MAX_RENDER_PIXELS or max(width, height) > MAX_RENDER_EDGE:
        raise ValueError("El pliego excede el tamaño admitido para exportar PPF.")
    # Six samples per preview pixel: >=304.8 dpi, without one huge native raster.
    sx, sy = width * 6 / rect.width, height * 6 / rect.height
    preview = Image.new("CMYK", (width, height))
    for y in range(0, height, 256):
        for x in range(0, width, 256):
            x1, y1 = min(x + 256, width), min(y + 256, height)
            clip = pymupdf.Rect(x * 6 / sx, y * 6 / sy, x1 * 6 / sx, y1 * 6 / sy)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(sx, sy), clip=clip,
                                  colorspace=pymupdf.csCMYK, alpha=False, annots=False)
            tile = Image.frombytes("CMYK", (pix.width, pix.height), pix.samples)
            tile = tile.crop((x * 6 - pix.x, y * 6 - pix.y,
                              x1 * 6 - pix.x, y1 * 6 - pix.y))
            preview.paste(tile.resize((x1 - x, y1 - y), Image.Resampling.BOX), (x, y))
    return preview


def _require_process_colors(pdf_path):
    """Do not silently flatten extra printing inks into a four-color PPF."""
    process = {"/Cyan", "/Magenta", "/Yellow", "/Black", "/All", "/None"}
    with pikepdf.open(pdf_path) as pdf:
        for _, resources in iter_resources(pdf):
            for cs in resources.get("/ColorSpace", {}).values():
                if not isinstance(cs, pikepdf.Array) or len(cs) < 2:
                    continue
                names = ([cs[1]] if str(cs[0]) == "/Separation" else
                         cs[1] if str(cs[0]) == "/DeviceN" else [])
                if any(str(name) not in process for name in names):
                    raise ValueError("El PPF CMYK requiere convertir primero las tintas planas a proceso.")


def generate_cip3_ppf(
    cip3_data: Dict[str, Any],
    output_ppf_path: str,
    job_id: str,
    job_title: str = "IntelliPrint_CIP3_Job",
    *,
    pdf_path: str | Path | None = None,
    page_number: int = 0,
) -> str:
    """Write one sheet/front with a real composite CMYK preview, as specified by PPF 3.0.

    Console-specific orientation, calibration and import compatibility must be
    verified on the target press. Zone openings remain estimates in the PDF report.
    """
    if pdf_path is None:
        raise ValueError("La exportación PPF necesita el PDF original del pliego.")
    _require_process_colors(pdf_path)
    with pymupdf.open(pdf_path) as doc:
        if not 0 <= page_number < len(doc):
            raise ValueError("Página PPF fuera de rango.")
        page = doc[page_number]
        w_pt, h_pt = page.rect.width, page.rect.height
        sheet = cip3_data["sheet_info"]
        if abs(w_pt - sheet["width_pt"]) > 0.1 or abs(h_pt - sheet["height_pt"]) > 0.1:
            raise ValueError("El PDF no coincide con las dimensiones del cálculo de cobertura.")
        preview = _render_ppf_preview(page)
    width, height = preview.size
    # Composite CMYK uses 0=no ink, 255=full ink; MuPDF has the same polarity.
    hex_data = preview.tobytes().hex().upper()
    payload = ("\n".join(hex_data[i:i + 128] for i in range(0, len(hex_data), 128)) + "\n>").encode("ascii")
    body = f"""CIP3BeginSheet
/CIP3AdmJobName {_ps_string(job_title)} def
/CIP3AdmJobCode {_ps_string(job_id)} def
/CIP3AdmSheetName (Sheet_1) def
/CIP3AdmSoftware (IntelliPrint) def
/CIP3AdmCreationTime ({datetime.now().strftime('D:%Y%m%d%H%M%S')}) def
/CIP3AdmPrintVolume {max(1, int(cip3_data['run_length']))} def
/CIP3AdmPSExtent [{w_pt:.8f} {h_pt:.8f}] def
/CIP3AdmSeparationNames [(Cyan) (Magenta) (Yellow) (Black)] def
/CIP3TransferFilmCurveData [0 0 1 1] def
/CIP3TransferPlateCurveData [0 0 1 1] def
CIP3BeginFront
CIP3BeginPreviewImage
/CIP3PreviewImageWidth {width} def
/CIP3PreviewImageHeight {height} def
/CIP3PreviewImageBitsPerComp 8 def
/CIP3PreviewImageComponents 4 def
/CIP3PreviewImageMatrix [{width} 0 0 {-height} 0 {height}] def
/CIP3PreviewImageResolution [{width * 72 / w_pt:.8f} {height * 72 / h_pt:.8f}] def
/CIP3PreviewImageEncoding /ASCIIHexDecode def
/CIP3PreviewImageCompression /None def
/CIP3PreviewImageDataSize {len(payload)} def
CIP3PreviewImage
"""
    with atomic_output(output_ppf_path) as temporary:
        with open(temporary, "wb") as stream:
            stream.write(PPF_HEADER)
            stream.write(body.encode("ascii"))
            stream.write(payload)
            stream.write(b"\nCIP3EndPreviewImage\nCIP3EndFront\nCIP3EndSheet\n%%CIP3EndOfFile\n")
    return output_ppf_path


def generate_cip3_pdf_sheet(
    cip3_data: Dict[str, Any],
    output_pdf_path: str,
    job_id: str,
    job_title: str = "Trabajo de Impresión"
) -> str:
    """
    Genera la Ficha Técnica de Ajuste de Tinteros CIP3 en PDF A4 horizontal para el maquinista.
    Diseño visual con cabecera institucional, métricas de consumo en kg, gráfico de barras y tabla de apertura de llaves.
    """
    # A4 horizontal (841.89 x 595.28 pt)
    w_pt = 841.89
    h_pt = 595.28
    
    doc = pymupdf.open()
    page = doc.new_page(width=w_pt, height=h_pt)
    
    teal_dark = (0.05, 0.15, 0.25)
    teal_brand = (0.05, 0.58, 0.53)
    gray_bg = (0.96, 0.97, 0.98)
    gray_border = (0.82, 0.86, 0.90)
    
    # 1. Cabecera técnica
    page.draw_rect(pymupdf.Rect(0, 0, w_pt, 70), fill=teal_dark, width=0)
    page.draw_line(pymupdf.Point(0, 70), pymupdf.Point(w_pt, 70), color=teal_brand, width=2.5)
    
    page.insert_text(
        pymupdf.Point(36, 28),
        "INTELLIPRINT PREPRESS SUITE  |  FICHA TÉCNICA CIP3 / PREAJUSTE DE TINTEROS",
        fontsize=12,
        fontname="helv",
        color=(1, 1, 1)
    )
    page.insert_text(
        pymupdf.Point(36, 46),
        f"Hoja de Consumos y Curvas de Apertura de Llaves de Tintero (Zonas 1 a {cip3_data['num_zones']})",
        fontsize=9.5,
        fontname="helv",
        color=(0.3, 0.8, 0.75)
    )
    page.insert_text(
        pymupdf.Point(36, 60),
        "Centros de Referencia: CPIFP Salesianos Urnieta LHIPI  •  CIFP Mendizabala LHII  •  Hezkuntza Saila (Eusko Jaurlaritza)",
        fontsize=7.5,
        fontname="helv",
        color=(0.7, 0.75, 0.82)
    )
    page.insert_text(
        pymupdf.Point(w_pt - 180, 46),
        f"ID: {job_id[:12]}",
        fontsize=9,
        fontname="helv",
        color=(1, 1, 1)
    )
    
    # 2. Tarjetas de Resumen de Trabajo y Consumo (Fila superior)
    sheet = cip3_data["sheet_info"]
    ink = cip3_data["ink_consumption"]
    cov = cip3_data["coverage_summary"]
    
    # Caja Metadatos
    page.draw_rect(pymupdf.Rect(36, 82, 260, 155), fill=gray_bg, color=gray_border, width=0.8)
    page.insert_text(pymupdf.Point(46, 98), "DATOS DE PRODUCCIÓN", fontsize=8.5, fontname="helv", color=(0.1, 0.2, 0.3))
    page.insert_text(pymupdf.Point(46, 113), f"• Pliego de Entrada: {sheet['width_mm']} x {sheet['height_mm']} mm", fontsize=7.5, fontname="helv")
    page.insert_text(pymupdf.Point(46, 126), f"• Tirada Programada: {ink['run_length']:,} pliegos", fontsize=7.5, fontname="helv")
    page.insert_text(pymupdf.Point(46, 139), f"• Tipo de Papel: {cip3_data['paper_type'].capitalize()} ({cip3_data['paper_film_weight_g_m2']} g/m²)", fontsize=7.5, fontname="helv")
    page.insert_text(pymupdf.Point(46, 150), f"• Llaves de Tintero: {cip3_data['num_zones']} zonas ({sheet['zone_width_mm']} mm/zona)", fontsize=7.5, fontname="helv")
    
    # Cajas de Consumo CMYK
    colors_meta = [
        {"name": "CIAN", "cov": cov["c"], "g": ink["c_g"], "kg": ink["c_kg"], "color": (0.0, 0.6, 0.85)},
        {"name": "MAGENTA", "cov": cov["m"], "g": ink["m_g"], "kg": ink["m_kg"], "color": (0.85, 0.1, 0.5)},
        {"name": "AMARILLO", "cov": cov["y"], "g": ink["y_g"], "kg": ink["y_kg"], "color": (0.85, 0.75, 0.0)},
        {"name": "NEGRO", "cov": cov["k"], "g": ink["k_g"], "kg": ink["k_kg"], "color": (0.15, 0.15, 0.18)}
    ]
    card_w = (w_pt - 36 - 280) / 4.0
    for idx, c_info in enumerate(colors_meta):
        cx = 275 + idx * card_w
        page.draw_rect(pymupdf.Rect(cx, 82, cx + card_w - 8, 155), fill=gray_bg, color=gray_border, width=0.8)
        # Barra de color distintiva
        page.draw_rect(pymupdf.Rect(cx, 82, cx + card_w - 8, 86), fill=c_info["color"], width=0)
        page.insert_text(pymupdf.Point(cx + 8, 100), c_info["name"], fontsize=8.5, fontname="helv", color=c_info["color"])
        page.insert_text(pymupdf.Point(cx + 8, 116), f"Cob: {c_info['cov']:.1f}%", fontsize=8, fontname="helv")
        page.insert_text(pymupdf.Point(cx + 8, 132), f"Tinta: {c_info['g']:.1f} g", fontsize=8, fontname="helv")
        page.insert_text(pymupdf.Point(cx + 8, 147), f"Total: {c_info['kg']:.3f} kg", fontsize=9, fontname="helv", color=(0.1, 0.15, 0.2))

    # 3. Gráfico de Barras de Apertura de Tinteros por Zonas (Zona 1 a 32)
    chart_y = 170.0
    chart_h = 135.0
    chart_w = w_pt - 72
    page.draw_rect(pymupdf.Rect(36, chart_y, 36 + chart_w, chart_y + chart_h), fill=(1, 1, 1), color=gray_border, width=0.8)
    page.insert_text(pymupdf.Point(46, chart_y + 16), "PERFIL GRÁFICO DE APERTURA ESTIMADA DE LLAVES (% OPENING - EJE LONGITUDINAL DEL CILINDRO)", fontsize=8, fontname="helv", color=(0.2, 0.25, 0.35))
    
    # Líneas guía de escala 25%, 50%, 75%, 100%
    base_bar_y = chart_y + chart_h - 22.0
    max_bar_h = 80.0
    for grid_val in [25, 50, 75, 100]:
        gy = base_bar_y - (grid_val / 100.0) * max_bar_h
        page.draw_line(pymupdf.Point(55, gy), pymupdf.Point(36 + chart_w - 15, gy), color=(0.90, 0.92, 0.94), width=0.5)
        page.insert_text(pymupdf.Point(38, gy + 3), f"{grid_val}%", fontsize=5.5, fontname="helv", color=(0.55, 0.6, 0.65))

    num_z = cip3_data["num_zones"]
    bar_slot_w = (chart_w - 30) / float(num_z)
    sub_bar_w = max(1.2, (bar_slot_w - 2.0) / 4.0)

    for i, z in enumerate(cip3_data["zones"]):
        zx = 55 + i * bar_slot_w
        
        # 4 barritas: C, M, Y, K
        openings = [z["c_opening"], z["m_opening"], z["y_opening"], z["k_opening"]]
        for c_idx, op_val in enumerate(openings):
            bh = (op_val / 100.0) * max_bar_h
            bx = zx + c_idx * sub_bar_w
            by = base_bar_y - bh
            c_fill = colors_meta[c_idx]["color"]
            page.draw_rect(pymupdf.Rect(bx, by, bx + sub_bar_w - 0.2, base_bar_y), fill=c_fill, width=0)
            
        # Número de zona abajo
        page.insert_text(pymupdf.Point(zx + 1, base_bar_y + 10), str(z["zone_index"]), fontsize=5.5, fontname="helv", color=(0.3, 0.35, 0.4))
        
        # Advertencia de fricción seca
        if z.get("is_dry_friction_risk"):
            page.draw_rect(pymupdf.Rect(zx - 1, base_bar_y + 12, zx + bar_slot_w - 1, base_bar_y + 18), fill=(0.95, 0.2, 0.2), width=0)
            page.insert_text(pymupdf.Point(zx, base_bar_y + 17), "FRIC", fontsize=4.2, fontname="helv", color=(1, 1, 1))

    # 4. Tabla Numérica de Apertura de Tornillos de Tintero (Zona 1 a 32)
    tbl_y = 315.0
    tbl_h = 245.0
    page.draw_rect(pymupdf.Rect(36, tbl_y, 36 + chart_w, tbl_y + tbl_h), fill=(1, 1, 1), color=gray_border, width=0.8)
    page.insert_text(pymupdf.Point(46, tbl_y + 15), "TABLA TÉCNICA DE REGLAJE DE TORNILLOS (VALORES EN % DE APERTURA PARA CONSOLA)", fontsize=8, fontname="helv", color=(0.2, 0.25, 0.35))
    
    # Dividir las 32 zonas en 2 bloques de 16 para máxima legibilidad
    block_w = (chart_w - 30) / 2.0
    
    def render_zone_subtable(sub_zones: List[Dict[str, Any]], start_tx: float):
        row_y = tbl_y + 25.0
        # Cabecera de subtabla
        page.draw_rect(pymupdf.Rect(start_tx, row_y, start_tx + block_w, row_y + 14), fill=(0.1, 0.15, 0.25), width=0)
        page.insert_text(pymupdf.Point(start_tx + 4, row_y + 10), "ZONA", fontsize=6, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(start_tx + 36, row_y + 10), "ANCHO (mm)", fontsize=6, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(start_tx + 95, row_y + 10), "CIAN %", fontsize=6, fontname="helv", color=(0.3, 0.8, 1))
        page.insert_text(pymupdf.Point(start_tx + 140, row_y + 10), "MAGENTA %", fontsize=6, fontname="helv", color=(1, 0.4, 0.7))
        page.insert_text(pymupdf.Point(start_tx + 195, row_y + 10), "AMARILLO %", fontsize=6, fontname="helv", color=(1, 0.9, 0.2))
        page.insert_text(pymupdf.Point(start_tx + 255, row_y + 10), "NEGRO %", fontsize=6, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(start_tx + 300, row_y + 10), "ESTADO", fontsize=6, fontname="helv", color=(1, 1, 1))
        
        row_y += 14.0
        for sz in sub_zones:
            bg_c = (0.96, 0.97, 0.98) if sz["zone_index"] % 2 == 0 else (1, 1, 1)
            page.draw_rect(pymupdf.Rect(start_tx, row_y, start_tx + block_w, row_y + 11.5), fill=bg_c, width=0)
            page.insert_text(pymupdf.Point(start_tx + 6, row_y + 8.5), f"Z{sz['zone_index']:02d}", fontsize=6.2, fontname="helv", color=(0.1, 0.15, 0.2))
            page.insert_text(pymupdf.Point(start_tx + 36, row_y + 8.5), f"{sz['x_start_mm']}-{sz['x_end_mm']}", fontsize=5.8, fontname="helv", color=(0.4, 0.45, 0.5))
            page.insert_text(pymupdf.Point(start_tx + 95, row_y + 8.5), f"{sz['c_opening']:.1f}%", fontsize=6.2, fontname="helv", color=(0.0, 0.4, 0.7))
            page.insert_text(pymupdf.Point(start_tx + 140, row_y + 8.5), f"{sz['m_opening']:.1f}%", fontsize=6.2, fontname="helv", color=(0.7, 0.0, 0.4))
            page.insert_text(pymupdf.Point(start_tx + 195, row_y + 8.5), f"{sz['y_opening']:.1f}%", fontsize=6.2, fontname="helv", color=(0.6, 0.5, 0.0))
            page.insert_text(pymupdf.Point(start_tx + 255, row_y + 8.5), f"{sz['k_opening']:.1f}%", fontsize=6.2, fontname="helv", color=(0.1, 0.1, 0.1))
            
            status_txt = "OK"
            status_col = (0.05, 0.5, 0.3)
            if sz.get("is_dry_friction_risk"):
                status_txt = "FRICCIÓN"
                status_col = (0.85, 0.15, 0.1)
            page.insert_text(pymupdf.Point(start_tx + 300, row_y + 8.5), status_txt, fontsize=5.8, fontname="helv", color=status_col)
            row_y += 11.5

    half_n = len(cip3_data["zones"]) // 2
    render_zone_subtable(cip3_data["zones"][:half_n], start_tx=46)
    render_zone_subtable(cip3_data["zones"][half_n:], start_tx=46 + block_w + 15)

    # 5. Pie institucional
    page.draw_line(pymupdf.Point(36, 570), pymupdf.Point(w_pt - 36, 570), color=(0.8, 0.85, 0.9), width=0.5)
    page.insert_text(
        pymupdf.Point(36, 582),
        "IntelliPrint Engine CIP3 v3.0 • Específicamente desarrollado para formación profesional gráfica en Euskadi • ISO 12647-2",
        fontsize=6.8,
        fontname="helv",
        color=(0.5, 0.55, 0.6)
    )
    page.insert_text(
        pymupdf.Point(w_pt - 180, 582),
        f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        fontsize=6.8,
        fontname="helv",
        color=(0.1, 0.4, 0.35)
    )

    doc.save(output_pdf_path)
    doc.close()
    return output_pdf_path

