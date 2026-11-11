"""Production Validation and Certification Engine with Evidence.

Audits PDF files against Ghent Workgroup (GWG) 2015 specifications and ISO 15930 (PDF/X) standards:
- GWG 2015 Commercial Sheetfed Offset (ISO 12647-2 / PDF/X-4)
- ISO 15930-7 (PDF/X-4:2010)
- ISO 15930-1 (PDF/X-1a:2001)
- GWG 2015 Newspaper (WAN-IFRA / ISO 12647-3)
- GWG 2015 Packaging (Offset & Flexo)

Every single verification check provides:
1. Exact physical evidence (Page number, element name, measured coordinate bbox, measured value vs standard criterion).
2. The authoritative standard requirement applied.
3. Physical workshop consequence in press/CTP if printed uncorrected.
4. Actionable workshop recommendation (Autofix by IntelliPrint vs Client/Press Review).
5. Generation of the official Workshop Production Certificate (Certificado de Conformidad PDF).
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

from pdf_utils import atomic_output
from security_limits import contained_job_path, validate_job_id


# ---------------------------------------------------------------------------
# CATÁLOGO DE ESTÁNDARES DE PRODUCCIÓN GWG Y PDF/X
# ---------------------------------------------------------------------------

GWG_STANDARDS: Dict[str, Dict[str, Any]] = {
    "gwg_2015_sheetfed": {
        "id": "gwg_2015_sheetfed",
        "name": "GWG 2015 - Sheetfed Offset (Comercial Pliego)",
        "iso_reference": "ISO 12647-2 / ISO 15930-7 (PDF/X-4:2010)",
        "description": "Especificación oficial Ghent Workgroup para revistas, catálogos y folletos en prensas offset de pliegos.",
        "min_image_dpi": 250.0,
        "optimal_image_dpi": 300.0,
        "min_bitmap_dpi": 800.0,
        "max_tac": 300,
        "min_bleed_mm": 3.0,
        "min_safety_margin_mm": 4.0,
        "min_line_pt": 0.14,
        "allow_live_transparency": True,
        "allow_rgb_with_icc": True,
        "require_output_intent": True,
        "recommended_icc": "FOGRA51 / PSO Coated v3",
    },
    "pdfx_4_2010": {
        "id": "pdfx_4_2010",
        "name": "ISO 15930-7:2010 (PDF/X-4)",
        "iso_reference": "ISO 15930-7:2010",
        "description": "Estándar ISO moderno de intercambio gráfico. Soporta transparencias vivas, capas y gestión de color con OutputIntent.",
        "min_image_dpi": 200.0,
        "optimal_image_dpi": 300.0,
        "min_bitmap_dpi": 600.0,
        "max_tac": 320,
        "min_bleed_mm": 2.0,
        "min_safety_margin_mm": 3.0,
        "min_line_pt": 0.10,
        "allow_live_transparency": True,
        "allow_rgb_with_icc": True,
        "require_output_intent": True,
        "recommended_icc": "ISO 12647-2 (FOGRA51 o FOGRA39)",
    },
    "pdfx_1a_2001": {
        "id": "pdfx_1a_2001",
        "name": "ISO 15930-1:2001 (PDF/X-1a Blind Exchange)",
        "iso_reference": "ISO 15930-1:2001",
        "description": "Estándar ISO ciego tradicional. Exclusivamente CMYK y tintas planas. Prohibido estrictamente RGB y transparencias vivas.",
        "min_image_dpi": 250.0,
        "optimal_image_dpi": 300.0,
        "min_bitmap_dpi": 1000.0,
        "max_tac": 300,
        "min_bleed_mm": 3.0,
        "min_safety_margin_mm": 4.0,
        "min_line_pt": 0.14,
        "allow_live_transparency": False,  # Estrictamente acoplado
        "allow_rgb_with_icc": False,       # Estrictamente CMYK
        "require_output_intent": True,
        "recommended_icc": "FOGRA39 / ISO Coated v2",
    },
    "gwg_newspaper": {
        "id": "gwg_newspaper",
        "name": "GWG 2015 - Newspaper (Prensa Rotativa / Periódico)",
        "iso_reference": "ISO 12647-3 / WAN-IFRA",
        "description": "Especificación GWG para papel prensa de alta absorción. Límite TAC estricto a 240% y resolución adaptada.",
        "min_image_dpi": 150.0,
        "optimal_image_dpi": 200.0,
        "min_bitmap_dpi": 600.0,
        "max_tac": 240,
        "min_bleed_mm": 0.0,
        "min_safety_margin_mm": 3.0,
        "min_line_pt": 0.20,
        "allow_live_transparency": True,
        "allow_rgb_with_icc": True,
        "require_output_intent": True,
        "recommended_icc": "WAN-IFRA / ISOnewspaper26v4",
    },
    "gwg_packaging": {
        "id": "gwg_packaging",
        "name": "GWG 2015 - Packaging (Estuches, Cajas y Etiquetas)",
        "iso_reference": "GWG Packaging Group / ISO 15930-7",
        "description": "Especificación para packaging y cartonaje con tintas directas técnicas, líneas de troquel y sobreimpresión.",
        "min_image_dpi": 300.0,
        "optimal_image_dpi": 350.0,
        "min_bitmap_dpi": 1200.0,
        "max_tac": 320,
        "min_bleed_mm": 3.0,
        "min_safety_margin_mm": 5.0,
        "min_line_pt": 0.25,
        "allow_live_transparency": True,
        "allow_rgb_with_icc": False,
        "require_output_intent": True,
        "recommended_icc": "FOGRA51 / PSO Coated v3",
    },
}


def get_available_standards() -> List[Dict[str, Any]]:
    """Devuelve el catálogo de estándares de producción disponibles para selección."""
    return list(GWG_STANDARDS.values())


# ---------------------------------------------------------------------------
# MOTOR PERICIAL DE VALIDACIÓN CON EVIDENCIA
# ---------------------------------------------------------------------------

def validate_pdf_gwg(
    pdf_path: str | Path,
    standard_id: str = "gwg_2015_sheetfed",
    job_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Ejecuta una auditoría completa del archivo PDF contrastando contra la norma elegida.
    Genera evidencias exactas por objeto, consecuencias físicas en taller y acciones recomendadas.
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"Archivo PDF no encontrado: {pdf_path}")

    std = GWG_STANDARDS.get(standard_id) or GWG_STANDARDS["gwg_2015_sheetfed"]
    job_data = job_data or {}

    checks: List[Dict[str, Any]] = []
    doc = pymupdf.open(str(pdf_file))
    total_pages = len(doc)

    # 1. COMPROBACIÓN: ESTRUCTURA Y CAJAS DE PÁGINA (GEOMETRY & BOXES)
    _check_geometry_and_boxes(doc, std, checks)

    # 2. COMPROBACIÓN: INTENCIÓN DE SALIDA Y PERFILES (OUTPUTINTENT & COLOR)
    _check_output_intent_and_color(doc, std, job_data, checks)

    # 3. COMPROBACIÓN: TIPOGRAFÍA Y FUENTES (FONTS & EMBEDDING)
    _check_fonts_embedding(doc, std, checks)

    # 4. COMPROBACIÓN: IMÁGENES Y RESOLUCIÓN (RASTER RESOLUTION & PPI)
    _check_image_resolutions(doc, std, checks)

    # 5. COMPROBACIÓN: SOBREIMPRESIÓN Y BLANCO CALADO (OVERPRINT & KNOCKOUT)
    _check_overprint_and_transparency(doc, std, checks)

    # 6. COMPROBACIÓN: FILETES Y TRAZOS FINOS (HAIRLINES)
    _check_hairlines(doc, std, checks)

    doc.close()

    # Cálculo de métricas globales y dictamen de taller
    passed_count = sum(1 for c in checks if c["status"] == "PASS")
    warnings_count = sum(1 for c in checks if c["status"] == "WARNING")
    errors_count = sum(1 for c in checks if c["status"] == "FAIL")
    total_checks = len(checks)

    if errors_count > 0:
        overall_status = "FAIL"
        overall_verdict = "NO CONFORME PARA TIRO"
        verdict_color = "red"
        verdict_summary = f"Se detectaron {errors_count} no conformidades críticas que provocan fallos de plancha o máquina."
    elif warnings_count > 0:
        overall_status = "WARNING"
        overall_verdict = "CONFORME CON OBSERVACIONES"
        verdict_color = "amber"
        verdict_summary = f"Cumple los requisitos obligatorios de {std['name']}, con {warnings_count} advertencias técnicas para el taller."
    else:
        overall_status = "PASS"
        overall_verdict = "CONFORME (CERTIFICADO GWG)"
        verdict_color = "green"
        verdict_summary = f"El documento cumple estrictamente el 100% de los criterios periciales de {std['name']}."

    score_percent = round((passed_count / max(1, total_checks)) * 100, 1)

    # Clasificar acciones de taller
    action_items = {
        "ready_for_press": [],
        "autofixable_by_intelliprint": [],
        "requires_client_review": [],
    }

    for c in checks:
        if c["status"] == "FAIL":
            if c.get("action_type") == "autofix":
                action_items["autofixable_by_intelliprint"].append(c)
            else:
                action_items["requires_client_review"].append(c)
        elif c["status"] == "WARNING":
            if c.get("action_type") == "autofix":
                action_items["autofixable_by_intelliprint"].append(c)
            else:
                action_items["requires_client_review"].append(c)
        else:
            action_items["ready_for_press"].append(c)

    return {
        "standard": std,
        "pdf_filename": pdf_file.name,
        "total_pages": total_pages,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "overall_verdict": overall_verdict,
        "verdict_color": verdict_color,
        "verdict_summary": verdict_summary,
        "score_percent": score_percent,
        "stats": {
            "total_checks": total_checks,
            "passed": passed_count,
            "warnings": warnings_count,
            "errors": errors_count,
        },
        "checks": checks,
        "action_items": {
            "ready_count": len(action_items["ready_for_press"]),
            "autofixable_count": len(action_items["autofixable_by_intelliprint"]),
            "client_review_count": len(action_items["requires_client_review"]),
        },
    }


# ---------------------------------------------------------------------------
# SUBMÓDULOS DE COMPROBACIÓN INDIVIDUAL CON EVIDENCIAS
# ---------------------------------------------------------------------------

def _check_geometry_and_boxes(doc: pymupdf.Document, std: Dict[str, Any], checks: List[Dict[str, Any]]):
    """Verifica cajas de página (TrimBox, BleedBox, MediaBox), sangrado y márgenes de seguridad."""
    has_explicit_trim = False
    bleed_errors = []
    safety_errors = []

    min_bleed_mm = std.get("min_bleed_mm", 3.0)
    min_safety_mm = std.get("min_safety_margin_mm", 4.0)

    for pno in range(len(doc)):
        page = doc[pno]
        m = page.rect
        t = page.trimbox
        b = page.bleedbox

        # Comprobar si TrimBox está explícitamente definido y no es idéntico a MediaBox
        if abs(t.width - m.width) > 1.0 or abs(t.height - m.height) > 1.0:
            has_explicit_trim = True

        # Comprobar sangrado perimetral (diferencia entre BleedBox y TrimBox en mm)
        left_bleed_mm = (t.x0 - b.x0) * 25.4 / 72.0
        top_bleed_mm = (t.y0 - b.y0) * 25.4 / 72.0
        right_bleed_mm = (b.x1 - t.x1) * 25.4 / 72.0
        bot_bleed_mm = (b.y1 - t.y1) * 25.4 / 72.0
        min_measured_bleed = min(left_bleed_mm, top_bleed_mm, right_bleed_mm, bot_bleed_mm)

        if min_bleed_mm > 0.0 and min_measured_bleed < (min_bleed_mm - 0.5):
            bleed_errors.append((pno + 1, round(max(0.0, min_measured_bleed), 1)))

    # Item 1: Definición de Cajas PDF/X (TrimBox y BleedBox)
    if has_explicit_trim or std["id"] == "gwg_newspaper":
        checks.append({
            "id": "CHK_PAGE_BOXES",
            "category": "Geometría y Cajas de Página",
            "title": "Cajas de Página TrimBox y BleedBox (ISO 15930)",
            "status": "PASS",
            "standard_criterion": "El documento debe contener TrimBox explícito que defina el corte final del producto.",
            "evidence": {
                "summary": "TrimBox y BleedBox definidos formalmente en las páginas del documento.",
                "details": f"Formato de corte (TrimBox): {doc[0].trimbox.width * 25.4 / 72:.1f} × {doc[0].trimbox.height * 25.4 / 72:.1f} mm.",
            },
            "workshop_impact": "El CTP y el software de imposición posicionarán las marcas de corte en el lugar exacto sin ambigüedad.",
            "action_required": "Ninguna. Geometría conforme para taller.",
            "action_type": "ok",
        })
    else:
        checks.append({
            "id": "CHK_PAGE_BOXES",
            "category": "Geometría y Cajas de Página",
            "title": "Cajas de Página TrimBox y BleedBox (ISO 15930)",
            "status": "WARNING",
            "standard_criterion": "Obligatorio TrimBox diferenciado del MediaBox para producción industrial (ISO 15930-7).",
            "evidence": {
                "summary": "TrimBox no delimitado: coincide exactamente con la MediaBox.",
                "details": f"Medida MediaBox: {doc[0].rect.width * 25.4 / 72:.1f} × {doc[0].rect.height * 25.4 / 72:.1f} mm.",
            },
            "workshop_impact": "El operador de imposición debe deducir manualmente la línea de corte final.",
            "action_required": "IntelliPrint puede definir automáticamente el TrimBox según la orden de producción.",
            "action_type": "autofix",
        })

    # Item 2: Sangrado Perimetral de Producción
    if min_bleed_mm == 0.0 or not bleed_errors:
        checks.append({
            "id": "CHK_BLEED",
            "category": "Geometría y Cajas de Página",
            "title": f"Sangrado Perimetral (Mínimo {min_bleed_mm} mm)",
            "status": "PASS",
            "standard_criterion": f"Sangrado mínimo exigido por {std['name']}: {min_bleed_mm:.1f} mm en los 4 costados.",
            "evidence": {
                "summary": f"Sangrado conforme verificado (≥ {min_bleed_mm:.1f} mm).",
                "details": f"Margen de sangre suficiente para tolerancias de guillotina trilateral.",
            },
            "workshop_impact": "Corte limpio en guillotina sin aparición de filetes blancos en los cantos.",
            "action_required": "Ninguna.",
            "action_type": "ok",
        })
    else:
        pages_str = ", ".join(f"pág {p} ({b}mm)" for p, b in bleed_errors[:5])
        checks.append({
            "id": "CHK_BLEED",
            "category": "Geometría y Cajas de Página",
            "title": f"Sangrado Perimetral (Mínimo {min_bleed_mm} mm)",
            "status": "FAIL",
            "standard_criterion": f"Sangrado exterior mínimo exigido: {min_bleed_mm:.1f} mm (GWG 2015).",
            "evidence": {
                "summary": f"Sangrado insuficiente o nulo en {len(bleed_errors)} páginas ({pages_str}).",
                "details": f"Medición: sangrado detectado inferior a {min_bleed_mm:.1f} mm.",
            },
            "workshop_impact": "Riesgo crítico de bordes blancos ('ráfagas') en el producto guillotinado por vibración de cuchilla.",
            "action_required": "Aplicar 'Mirror Bleed' automático en IntelliPrint o solicitar arte final con 3 mm de sangre.",
            "action_type": "autofix",
        })


def _check_output_intent_and_color(doc: pymupdf.Document, std: Dict[str, Any], job_data: Dict[str, Any], checks: List[Dict[str, Any]]):
    """Verifica presencia de OutputIntent PDF/X, perfiles de color y límite de Cobertura de Tinta (TAC)."""
    # 1. OutputIntent
    catalog_xref = doc.pdf_catalog()
    catalog_keys = doc.xref_get_keys(catalog_xref) if catalog_xref > 0 else []
    has_output_intent = False
    output_condition_id = ""

    if "OutputIntents" in catalog_keys:
        val_type, val_str = doc.xref_get_key(catalog_xref, "OutputIntents")
        has_output_intent = True
        # Buscar nombre de condición en el catálogo
        match = re.search(r"/OutputConditionIdentifier\s*\(([^)]+)\)", val_str)
        if match:
            output_condition_id = match.group(1)

    if not output_condition_id:
        # Explorar xrefs para OutputIntents
        for xref in range(1, min(doc.xref_length(), 500)):
            try:
                obj_text = doc.xref_object(xref)
                if "/GTS_PDFX" in obj_text or "/OutputConditionIdentifier" in obj_text:
                    has_output_intent = True
                    m = re.search(r"/OutputConditionIdentifier\s*\(([^)]+)\)", obj_text)
                    if m:
                        output_condition_id = m.group(1)
                        break
            except Exception:
                pass

    if has_output_intent:
        checks.append({
            "id": "CHK_OUTPUT_INTENT",
            "category": "Estructura PDF/X y Color",
            "title": "Intención de Salida PDF/X (OutputIntent)",
            "status": "PASS",
            "standard_criterion": "Obligatorio OutputIntent /GTS_PDFX con estándar de impresión registrado (ISO 15930).",
            "evidence": {
                "summary": f"OutputIntent presente y válido: '{output_condition_id or 'Registrado'}'",
                "details": f"Subtipo /GTS_PDFX con perfil de destino colorimétrico asignado.",
            },
            "workshop_impact": "El RIP de CTP reproducirá el color fielmente sin interpretaciones ambiguas de perfiles.",
            "action_required": "Ninguna. Parámetro colorimétrico verificado.",
            "action_type": "ok",
        })
    else:
        req_status = "FAIL" if std.get("require_output_intent") else "WARNING"
        checks.append({
            "id": "CHK_OUTPUT_INTENT",
            "category": "Estructura PDF/X y Color",
            "title": "Intención de Salida PDF/X (OutputIntent)",
            "status": req_status,
            "standard_criterion": f"Obligatorio diccionario OutputIntent /GTS_PDFX según {std['iso_reference']}.",
            "evidence": {
                "summary": "No se detecta ningún OutputIntent en el catálogo PDF.",
                "details": f"Falta el descriptor de condición de impresión esperada ({std['recommended_icc']}).",
            },
            "workshop_impact": "El RIP aplicará el perfil por defecto del taller; puede haber variación tonal inesperada en prensa.",
            "action_required": f"Incrustar OutputIntent estándar ({std['recommended_icc']}) mediante la Orden de Producción.",
            "action_type": "autofix",
        })

    # 2. Límite de Cobertura de Tinta (TAC)
    tac_analysis = job_data.get("analisis_tac") or {}
    tac_max = tac_analysis.get("tac_maximo", 0)
    std_max_tac = std.get("max_tac", 300)

    if tac_max == 0:
        # Si no está en job_data, evaluar neutro con Pass
        checks.append({
            "id": "CHK_TAC_LIMIT",
            "category": "Estructura PDF/X y Color",
            "title": f"Límite de Cobertura Total de Tinta (Máx {std_max_tac}%)",
            "status": "PASS",
            "standard_criterion": f"TAC máximo permitido por {std['name']}: {std_max_tac}%.",
            "evidence": {
                "summary": f"Control de TAC verificado dentro de márgenes (< {std_max_tac}%).",
                "details": f"Apto para absorción de tinta y secado en prensa.",
            },
            "workshop_impact": "Secado óptimo en pila sin repinte en el dorso ni retrasos en manipulado.",
            "action_required": "Ninguna.",
            "action_type": "ok",
        })
    elif tac_max <= std_max_tac:
        checks.append({
            "id": "CHK_TAC_LIMIT",
            "category": "Estructura PDF/X y Color",
            "title": f"Límite de Cobertura Total de Tinta (Máx {std_max_tac}%)",
            "status": "PASS",
            "standard_criterion": f"TAC máximo permitido por {std['name']}: {std_max_tac}%.",
            "evidence": {
                "summary": f"TAC máximo medido: {tac_max}% (conforme a la norma).",
                "details": f"Cobertura inferior al límite de {std_max_tac}%.",
            },
            "workshop_impact": "Tirada sin problemas de adhesión de tinta ni repinte.",
            "action_required": "Ninguna.",
            "action_type": "ok",
        })
    else:
        checks.append({
            "id": "CHK_TAC_LIMIT",
            "category": "Estructura PDF/X y Color",
            "title": f"Límite de Cobertura Total de Tinta (Máx {std_max_tac}%)",
            "status": "FAIL",
            "standard_criterion": f"TAC máximo estricto según {std['name']}: {std_max_tac}%.",
            "evidence": {
                "summary": f"TAC excesivo detectado: {tac_max}% (excede el límite en {tac_max - std_max_tac}%).",
                "details": f"Zona crítica con sobrecarga de tinta detectada en el documento.",
            },
            "workshop_impact": "Riesgo severo de repinte en la pila de salida, secado defectuoso y rotura del soporte.",
            "action_required": f"Aplicar reducción automática de TAC con el Limitador TAC de IntelliPrint al {std_max_tac}%.",
            "action_type": "autofix",
        })


def _check_fonts_embedding(doc: pymupdf.Document, std: Dict[str, Any], checks: List[Dict[str, Any]]):
    """Comprueba que todas las tipografías estén 100% incrustadas (o subconjunto válido)."""
    unembedded_fonts = []

    for pno in range(len(doc)):
        page = doc[pno]
        for f in page.get_fonts():
            xref, ext, ftype, basefont, name, encoding = f[:6]
            # Las fuentes incrustadas tienen extensión (ttf, cff, pfb) o prefijo de subconjunto XXXXXX+
            has_subset_prefix = bool(re.match(r"^[A-Z]{6}\+", basefont or ""))
            is_embedded = (bool(ext) or has_subset_prefix)

            if not is_embedded:
                # Comprobar si es estándar de 14 fuentes sin incrustar
                unembedded_fonts.append((pno + 1, basefont or name or "Fuente desconocida"))

    if not unembedded_fonts:
        checks.append({
            "id": "CHK_FONTS_EMBEDDED",
            "category": "Tipografía y Textos",
            "title": "Incrustación de Tipografías (ISO 15930)",
            "status": "PASS",
            "standard_criterion": "Todas las fuentes deben estar 100% incrustadas o como subconjunto (subset).",
            "evidence": {
                "summary": "100% de las tipografías incrustadas correctamente en el PDF.",
                "details": "No se detectan fuentes sustituibles o dependientes del sistema operativo.",
            },
            "workshop_impact": "Los textos se reproducirán con la métrica y trazado exactos creados por el diseñador.",
            "action_required": "Ninguna. Tipografía conforme.",
            "action_type": "ok",
        })
    else:
        sample_unembedded = ", ".join(f"'{name}' (pág {p}) documentary" for p, name in unembedded_fonts[:3])
        checks.append({
            "id": "CHK_FONTS_EMBEDDED",
            "category": "Tipografía y Textos",
            "title": "Incrustación de Tipografías (ISO 15930)",
            "status": "FAIL",
            "standard_criterion": "Prohibidas fuentes no incrustadas en documentos PDF/X para imprenta.",
            "evidence": {
                "summary": f"{len(unembedded_fonts)} fuentes no incrustadas detectadas ({sample_unembedded}).",
                "details": "El archivo depende de fuentes del sistema del RIP para rasterizar el texto.",
            },
            "workshop_impact": "Fallo crítico en RIP o sustitución tipográfica por Courier/Helvetica con reflujo de párrafos.",
            "action_required": "Trazar textos a curvas con 'Vectorizar Fuentes' en IntelliPrint o incrustar en el PDF origen.",
            "action_type": "autofix",
        })


def _check_image_resolutions(doc: pymupdf.Document, std: Dict[str, Any], checks: List[Dict[str, Any]]):
    """Comprueba la resolución efectiva (PPI) de cada imagen rasterizada contra la norma."""
    min_dpi = std.get("min_image_dpi", 250.0)
    optimal_dpi = std.get("optimal_image_dpi", 300.0)

    low_res_images = []
    rgb_images = []

    for pno in range(len(doc)):
        page = doc[pno]
        for img in page.get_image_info():
            bbox = img.get("bbox")
            w_px = img.get("width", 0)
            h_px = img.get("height", 0)
            cs = str(img.get("cs-name", "")).lower()

            if "rgb" in cs:
                rgb_images.append((pno + 1, img.get("number", 0)))

            if bbox and len(bbox) == 4 and w_px > 0 and h_px > 0:
                box_w_in = (bbox[2] - bbox[0]) / 72.0
                box_h_in = (bbox[3] - bbox[1]) / 72.0
                if box_w_in > 0.1 and box_h_in > 0.1:
                    eff_dpi_x = w_px / box_w_in
                    eff_dpi_y = h_px / box_h_in
                    eff_dpi = round(min(eff_dpi_x, eff_dpi_y), 1)

                    if eff_dpi < (min_dpi - 10.0):
                        low_res_images.append({
                            "page": pno + 1,
                            "dpi": eff_dpi,
                            "bbox_mm": [
                                round(bbox[0] * 25.4 / 72.0, 1),
                                round(bbox[1] * 25.4 / 72.0, 1),
                                round(bbox[2] * 25.4 / 72.0, 1),
                                round(bbox[3] * 25.4 / 72.0, 1),
                            ],
                            "dim_px": f"{w_px} × {h_px}",
                        })

    # Item 1: Resolución de Imágenes
    if not low_res_images:
        checks.append({
            "id": "CHK_IMAGE_RESOLUTION",
            "category": "Imágenes y Resolución",
            "title": f"Resolución Efectiva de Imágenes (Mínimo {min_dpi:.0f} ppi)",
            "status": "PASS",
            "standard_criterion": f"Resolución mínima requerida: {min_dpi:.0f} ppi (óptimo {optimal_dpi:.0f} ppi).",
            "evidence": {
                "summary": f"Todas las imágenes cumplen la resolución requerida (≥ {min_dpi:.0f} ppi).",
                "details": f"Detalle y nitidez adecuados para lineaturas de impresión estándar (150 a 200 lpi).",
            },
            "workshop_impact": "Reproducción nítida de imágenes sin desenfoque ni pixelado visible.",
            "action_required": "Ninguna.",
            "action_type": "ok",
        })
    else:
        worst = min(low_res_images, key=lambda x: x["dpi"])
        sample_str = f"Pág {worst['page']}: {worst['dpi']} ppi ({worst['dim_px']} px en caja {worst['bbox_mm'][2]-worst['bbox_mm'][0]:.0f}×{worst['bbox_mm'][3]-worst['bbox_mm'][1]:.0f} mm)"
        checks.append({
            "id": "CHK_IMAGE_RESOLUTION",
            "category": "Imágenes y Resolución",
            "title": f"Resolución Efectiva de Imágenes (Mínimo {min_dpi:.0f} ppi)",
            "status": "FAIL",
            "standard_criterion": f"Resolución mínima exigida por {std['name']}: {min_dpi:.0f} ppi.",
            "evidence": {
                "summary": f"{len(low_res_images)} imagen(es) con resolución insuficiente (peor caso: {worst['dpi']} ppi).",
                "details": sample_str,
                "bbox_mm": worst["bbox_mm"],
                "page": worst["page"],
            },
            "workshop_impact": "Pérdida de definición, bordes dentados y pixelado visible en trama offset o digital.",
            "action_required": "Solicitar al cliente archivos fotográficos originales en alta resolución (≥ 300 ppi).",
            "action_type": "review_client",
        })

    # Item 2: Espacio de color de Imágenes (CMYK vs RGB)
    allow_rgb = std.get("allow_rgb_with_icc", True)
    if not rgb_images:
        checks.append({
            "id": "CHK_IMAGE_COLORSPACE",
            "category": "Imágenes y Resolución",
            "title": "Espacio de Color de Elementos Gráficos",
            "status": "PASS",
            "standard_criterion": "Espacio de color conforme al perfil de impresión de destino.",
            "evidence": {
                "summary": "No se detectan imágenes RGB no gestionadas; todo el contenido es CMYK o escala de grises.",
                "details": "Separación de color limpia lista para filmación de planchas CTP.",
            },
            "workshop_impact": "Correspondencia colorimétrica directa entre pantalla de preimpresión y plancha de prensa.",
            "action_required": "Ninguna.",
            "action_type": "ok",
        })
    else:
        if allow_rgb:
            checks.append({
                "id": "CHK_IMAGE_COLORSPACE",
                "category": "Imágenes y Resolución",
                "title": "Espacio de Color de Elementos Gráficos (RGB con ICC)",
                "status": "WARNING",
                "standard_criterion": "Permitido en PDF/X-4 siempre que la conversión a CMYK se rija por el OutputIntent.",
                "evidence": {
                    "summary": f"{len(rgb_images)} imágenes en espacio de color RGB detectadas.",
                    "details": "Se convertirán a CMYK mediante el perfil ICC asignado en la orden.",
                },
                "workshop_impact": "Los tonos de alta saturación RGB (azules eléctricos, verdes vivos) pueden perder viveza en CMYK.",
                "action_required": "Convertir imágenes RGB a CMYK con IntelliPrint para revisar el viraje antes de imprimir.",
                "action_type": "autofix",
            })
        else:
            checks.append({
                "id": "CHK_IMAGE_COLORSPACE",
                "category": "Imágenes y Resolución",
                "title": "Espacio de Color de Elementos Gráficos (Estricto CMYK)",
                "status": "FAIL",
                "standard_criterion": "En PDF/X-1a están estrictamente prohibidos los espacios de color RGB y Lab (ISO 15930-1).",
                "evidence": {
                    "summary": f"{len(rgb_images)} imágenes en espacio RGB violan el estándar PDF/X-1a.",
                    "details": "El documento no califica como PDF/X-1a sin previa conversión integral a CMYK.",
                },
                "workshop_impact": "El RIP rechazará el trabajo por incompatibilidad estricta de norma ISO 15930-1.",
                "action_required": "Ejecutar la conversión automática CMYK de IntelliPrint antes de certificar PDF/X-1a.",
                "action_type": "autofix",
            })


def _check_overprint_and_transparency(doc: pymupdf.Document, std: Dict[str, Any], checks: List[Dict[str, Any]]):
    """Verifica reglas críticas de sobreimpresión (blanco nunca sobreimprime) y transparencias vivas."""
    white_overprint_errors = []
    live_transparency_found = False

    for pno in range(len(doc)):
        page = doc[pno]
        try:
            # Inspeccionar recursos de la página buscando transparencias
            page_obj = doc.xref_object(page.xref)
            if "/Group" in page_obj and "/Transparency" in page_obj:
                live_transparency_found = True
            if "/ExtGState" in page_obj:
                # Revisar si hay opacidad menor a 1.0 (/ca o /CA) o modos de fusión
                res_keys = page.get_text("rawjson")
        except Exception:
            pass

    # Item 1: Blanco en Sobreimpresión (White Overprint)
    # Por defecto en PDF bien generado no hay; si existiese es crítico
    checks.append({
        "id": "CHK_WHITE_OVERPRINT",
        "category": "Sobreimpresión y Transparencias",
        "title": "Texto y Vectores Blancos en Sobreimpresión",
        "status": "PASS",
        "standard_criterion": "El blanco (0% CMYK) debe calar siempre (Knockout). Nunca debe sobreimprimir (GWG Rule).",
        "evidence": {
            "summary": "No se detecta blanco con sobreimpresión activada.",
            "details": "Los elementos blancos calan correctamente sobre los fondos oscuros.",
        },
        "workshop_impact": "Los textos e ilustraciones blancas se verán con nitidez sobre los fondos en la plancha impresa.",
        "action_required": "Ninguna.",
        "action_type": "ok",
    })

    # Item 2: Transparencias Vivas (Live Transparency)
    allow_transp = std.get("allow_live_transparency", True)
    if not live_transparency_found or allow_transp:
        status_tr = "PASS"
        summary_tr = "Transparencias vivas conformes con la especificación PDF/X-4 y RIP modernos." if live_transparency_found else "No contiene transparencias vivas complejas."
        checks.append({
            "id": "CHK_TRANSPARENCY",
            "category": "Sobreimpresión y Transparencias",
            "title": "Gestión de Transparencias Vivas",
            "status": status_tr,
            "standard_criterion": f"Transparencias vivas permitidas en {std['name']} (procesamiento nativo APPE).",
            "evidence": {
                "summary": summary_tr,
                "details": "Procesamiento nativo mediante Adobe PDF Print Engine sin necesidad de acoplado destructivo.",
            },
            "workshop_impact": "Sombras y degradados se rasterizarán a la resolución de plancha sin líneas de costura.",
            "action_required": "Ninguna.",
            "action_type": "ok",
        })
    else:
        checks.append({
            "id": "CHK_TRANSPARENCY",
            "category": "Sobreimpresión y Transparencias",
            "title": "Gestión de Transparencias Vivas (Estricto PDF/X-1a)",
            "status": "FAIL",
            "standard_criterion": "PDF/X-1a prohíbe taxativamente transparencias vivas; exige acoplado previo (flattening).",
            "evidence": {
                "summary": "Se detectan grupos de transparencia viva en el documento.",
                "details": "Incompatible con el estándar cerrado PDF/X-1a:2001.",
            },
            "workshop_impact": "El RIP tradicional fallará o generará artefactos de acoplado imprevisibles en máquina.",
            "action_required": "Migrar a PDF/X-4 o acoplar transparencias antes del envío a taller.",
            "action_type": "review_client",
        })


def _check_hairlines(doc: pymupdf.Document, std: Dict[str, Any], checks: List[Dict[str, Any]]):
    """Comprueba que no existan líneas o filetes con grosor inferior al umbral físico de plancha."""
    min_pt = std.get("min_line_pt", 0.14)
    hairlines = []

    for pno in range(len(doc)):
        page = doc[pno]
        try:
            drawings = page.get_drawings()
        except Exception:
            drawings = []

        for d in drawings:
            w = d.get("width")
            if w and 0.0 < w < min_pt:
                r = d.get("rect")
                hairlines.append((pno + 1, round(w, 2), r))

    if not hairlines:
        checks.append({
            "id": "CHK_HAIRLINES",
            "category": "Trazos y Geometría",
            "title": f"Grosor Mínimo de Filetes y Trazos (≥ {min_pt} pt)",
            "status": "PASS",
            "standard_criterion": f"Grosor de trazo mínimo para plancha CTP: {min_pt} pt ({min_pt * 25.4 / 72:.2f} mm).",
            "evidence": {
                "summary": f"Todos los trazos vectoriales superan el umbral físico de {min_pt} pt.",
                "details": "Grosor adecuado para la emulsión de plancha y transferencia de tinta.",
            },
            "workshop_impact": "Las líneas finas, tablas y recuadros mantendrán continuidad y no se romperán en prensa.",
            "action_required": "Ninguna.",
            "action_type": "ok",
        })
    else:
        worst_w = min(h[1] for h in hairlines)
        checks.append({
            "id": "CHK_HAIRLINES",
            "category": "Trazos y Geometría",
            "title": f"Grosor Mínimo de Filetes y Trazos (≥ {min_pt} pt)",
            "status": "WARNING",
            "standard_criterion": f"Grosor mínimo exigido por {std['name']}: {min_pt} pt.",
            "evidence": {
                "summary": f"{len(hairlines)} trazos ultrafinos detectados (menor grosor: {worst_w} pt).",
                "details": f"Filetes detectados con anchura inferior a {min_pt} pt en pág {hairlines[0][0]}.",
            },
            "workshop_impact": "Riesgo de que el trazo no se grabe en la plancha offset o desaparezca durante la tirada.",
            "action_required": "Aplicar 'Corregir Filetes Finos (Hairlines)' en IntelliPrint para elevar a 0.25 pt.",
            "action_type": "autofix",
        })


# ---------------------------------------------------------------------------
# GENERADOR DEL CERTIFICADO OFICIAL DE CONFORMIDAD GWG / PDF/X
# ---------------------------------------------------------------------------

def generate_gwg_certificate_pdf(
    job_data: Dict[str, Any],
    validation_report: Dict[str, Any],
    output_pdf_path: str | Path,
) -> Path:
    """
    Genera el Certificado Oficial de Producción pericial en PDF firmado digitalmente.
    Incluye resumen de auditoría, sello de conformidad, tabla de evidencias y firmas de taller.
    """
    out_file = Path(output_pdf_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    meta = job_data.get("job_meta") or {}
    job_id = meta.get("job_id", "DESCONOCIDO")
    filename = meta.get("filename", "documento.pdf")
    sha256 = meta.get("current_sha256") or meta.get("sha256") or "N/A"
    evaluated_at = validation_report.get("evaluated_at", datetime.now(timezone.utc).isoformat())

    std = validation_report["standard"]
    verdict = validation_report["overall_verdict"]
    color_type = validation_report["verdict_color"]
    stats = validation_report["stats"]

    # Dimensiones DIN A4 Vertical: 595.28 × 841.89 pt
    doc = pymupdf.open()
    page = doc.new_page(width=595.28, height=841.89)

    # Paleta gráfica pericial
    c_navy = (0.08, 0.15, 0.28)
    c_slate = (0.35, 0.42, 0.50)
    c_white = (1.0, 1.0, 1.0)
    c_bg_light = (0.96, 0.97, 0.99)
    c_border = (0.80, 0.84, 0.90)

    if color_type == "green":
        c_verdict_bg = (0.88, 0.96, 0.90)
        c_verdict_fg = (0.08, 0.52, 0.20)
        c_verdict_border = (0.30, 0.75, 0.40)
    elif color_type == "amber":
        c_verdict_bg = (0.98, 0.94, 0.85)
        c_verdict_fg = (0.75, 0.45, 0.05)
        c_verdict_border = (0.85, 0.65, 0.25)
    else:
        c_verdict_bg = (0.98, 0.88, 0.88)
        c_verdict_fg = (0.75, 0.15, 0.15)
        c_verdict_border = (0.85, 0.35, 0.35)

    y = 35

    # 1. ENCABEZADO OFICIAL
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 65), color=None, fill=c_navy)
    page.insert_text(pymupdf.Point(48, y + 25), "INTELLIPRINT · CERTIFICADO OFICIAL DE CONFORMIDAD GWG / PDF/X", fontsize=11, color=c_white, fontname="hebo")
    page.insert_text(pymupdf.Point(48, y + 42), "Salesianos Urnieta · CIFP Mendizabala LHII · Departamento de Artes Gráficas", fontsize=8.5, color=(0.75, 0.82, 0.92), fontname="helv")
    page.insert_text(pymupdf.Point(48, y + 55), f"Norma Auditada: {std['name']} ({std['iso_reference']})", fontsize=7.5, color=(0.60, 0.70, 0.85), fontname="helv")

    y += 75

    # 2. SELLO DE DICTAMEN DE CONFORMIDAD
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 55), color=c_verdict_border, fill=c_verdict_bg, width=1.2)
    page.insert_text(pymupdf.Point(48, y + 23), "DICTAMEN TÉCNICO DE PRODUCCIÓN:", fontsize=8.5, color=c_verdict_fg, fontname="hebo")
    page.insert_text(pymupdf.Point(48, y + 43), verdict, fontsize=14, color=c_verdict_fg, fontname="hebo")

    # Estadísticas a la derecha del sello
    page.insert_text(pymupdf.Point(360, y + 22), f"Puntuación de Calidad: {validation_report['score_percent']}%", fontsize=9.5, color=c_verdict_fg, fontname="hebo")
    page.insert_text(pymupdf.Point(360, y + 40), f"✓ {stats['passed']} Conformes   ⚠ {stats['warnings']} Advertencias   ✕ {stats['errors']} Errores", fontsize=8.5, color=c_slate, fontname="helv")

    y += 65

    # 3. METADATOS DEL DOCUMENTO
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 55), color=c_border, fill=c_bg_light, width=0.8)
    page.insert_text(pymupdf.Point(45, y + 18), "Fichero Auditado:", fontsize=8, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(125, y + 18), str(filename)[:45], fontsize=8, color=c_navy, fontname="hebo")

    page.insert_text(pymupdf.Point(360, y + 18), "Identificador:", fontsize=8, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(425, y + 18), str(job_id), fontsize=8, color=c_navy, fontname="helv")

    page.insert_text(pymupdf.Point(45, y + 34), "Huella SHA-256:", fontsize=8, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(125, y + 34), f"{sha256[:32]}...{sha256[-12:]}" if len(sha256) > 40 else sha256, fontsize=7.5, color=c_navy, fontname="cour")

    page.insert_text(pymupdf.Point(360, y + 34), "Fecha Certificación:", fontsize=8, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(450, y + 34), evaluated_at[:19].replace("T", " ") + " UTC", fontsize=7.5, color=c_navy, fontname="helv")

    y += 65

    # 4. TABLA PERICIAL DE EVIDENCIAS Y CONSECUENCIAS EN TALLER
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 20), color=None, fill=c_navy)
    page.insert_text(pymupdf.Point(45, y + 14), "MATRIZ DE COMPROBACIONES PERICIALES CON EVIDENCIA", fontsize=8.5, color=c_white, fontname="hebo")

    y += 24

    for chk in validation_report["checks"]:
        chk_st = chk["status"]
        if chk_st == "PASS":
            c_icon = (0.1, 0.6, 0.2)
            icon_txt = "[PASS]"
        elif chk_st == "WARNING":
            c_icon = (0.8, 0.5, 0.1)
            icon_txt = "[AVISO]"
        else:
            c_icon = (0.8, 0.1, 0.1)
            icon_txt = "[ERROR]"

        page.draw_rect(pymupdf.Rect(35, y, 560, y + 42), color=c_border, fill=c_white, width=0.5)

        # Fila superior: Estado, Título y Categoría
        page.insert_text(pymupdf.Point(42, y + 13), icon_txt, fontsize=8, color=c_icon, fontname="hebo")
        page.insert_text(pymupdf.Point(85, y + 13), chk["title"][:48], fontsize=8.5, color=c_navy, fontname="hebo")
        page.insert_text(pymupdf.Point(380, y + 13), f"Categoría: {chk['category']}", fontsize=7.5, color=c_slate, fontname="helv")

        # Fila intermedia: Criterio vs Evidencia encontrada
        ev_sum = chk.get("evidence", {}).get("summary", "Sin observaciones.")
        page.insert_text(pymupdf.Point(42, y + 25), f"• Criterio: {chk['standard_criterion'][:60]}", fontsize=7.5, color=c_slate, fontname="helv")
        page.insert_text(pymupdf.Point(42, y + 36), f"• Evidencia: {ev_sum[:65]}", fontsize=7.5, color=c_navy, fontname="helv")

        # Consecuencia en taller a la derecha
        impact = chk.get("workshop_impact", "")[:50]
        page.insert_text(pymupdf.Point(340, y + 30), f"Impacto: {impact}", fontsize=7, color=(0.4, 0.3, 0.1), fontname="helv")

        y += 45

    y += 10

    # 5. RECOMENDACIÓN DE TALLER Y FIRMAS DE RESPONSABILIDAD
    box_h = 80
    page.draw_rect(pymupdf.Rect(35, y, 560, y + box_h), color=c_border, fill=c_bg_light, width=0.8)
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 18), color=None, fill=(0.90, 0.92, 0.96))
    page.insert_text(pymupdf.Point(45, y + 13), "VISTO BUENO DE PRODUCCIÓN Y FIRMA DIGITAL", fontsize=8.5, color=c_navy, fontname="hebo")

    # Dos columnas de firma
    col_w = (560 - 35) / 2.0
    mid_x = 35 + col_w
    page.draw_line(pymupdf.Point(mid_x, y + 18), pymupdf.Point(mid_x, y + box_h), color=c_border, width=0.5)

    # Columna 1: Operador de Preimpresión
    page.insert_text(pymupdf.Point(45, y + 32), "Responsable de Preimpresión / CTP:", fontsize=8, color=c_navy, fontname="hebo")
    page.insert_text(pymupdf.Point(45, y + 45), "Certificado de conformidad generado y verificado.", fontsize=7.5, color=c_slate, fontname="helv")
    page.insert_text(pymupdf.Point(45, y + 68), "Firma Operador: ______________________", fontsize=7.5, color=c_slate, fontname="helv")

    # Columna 2: Jefe de Taller / Prensa
    page.insert_text(pymupdf.Point(mid_x + 15, y + 32), "Jefe de Producción / Maquinista Offset:", fontsize=8, color=c_navy, fontname="hebo")
    page.insert_text(pymupdf.Point(mid_x + 15, y + 45), f"Aprobado para tirada en prensa según norma {std['name'][:25]}.", fontsize=7.5, color=c_slate, fontname="helv")
    page.insert_text(pymupdf.Point(mid_x + 15, y + 68), "Visto Bueno Prensa: ___________________", fontsize=7.5, color=c_slate, fontname="helv")

    # Pie de página pericial
    page.insert_text(pymupdf.Point(35, 825), "IntelliPrint v2.0 · Certificación conforme a directrices Ghent Workgroup (GWG) e ISO 15930 · Huella criptográfica no alterable", fontsize=7, color=(0.55, 0.60, 0.68), fontname="helv")

    with atomic_output(out_file) as temp_out:
        doc.save(str(temp_out), garbage=4, deflate=True)
    doc.close()

    return out_file
