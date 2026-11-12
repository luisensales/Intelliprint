"""Production order (Job Ticket) and recipe engine connecting Preflight, Imposition, CIP3 and Workshop Deliverables.

Allows configuring a graphical job by specifying real-world workshop parameters:
Product, Printing Machine, Substrate/Paper, Quantity, and Finishings.
Automatically recommends and configures:
- Recommended Preflight Profile and TAC limits
- Imposition Scheme (Step & Repeat vs Saddle-Stitch Booklet) and sheet size
- Paper sheet requirements (net sheets + estimated workshop setup waste)
- Consistency checks between the uploaded PDF and the production order
- Generation of the official Workshop Job Ticket (Hoja de Ruta de Taller) PDF
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

from pdf_utils import atomic_output
from security_limits import contained_job_path, validate_job_id


# ---------------------------------------------------------------------------
# CATÁLOGOS TÉCNICOS DE PRODUCCIÓN
# ---------------------------------------------------------------------------

PRODUCT_RECIPES = {
    "catalogo_grapado": {
        "id": "catalogo_grapado",
        "name": "Catálogo o Revista Grapada (Cuadernillo)",
        "description": "Folleto o revista encuadernada con grapa en caballete (Saddle-Stitch). Requiere páginas múltiplo de 4.",
        "default_imposition_mode": "booklet",
        "allowed_imposition_modes": ["booklet"],
        "pages_multiple_of": 4,
        "min_pages": 4,
        "standard_trim_mm": (210.0, 297.0),  # A4
        "recommended_gutter_x_mm": 0.0,      # Compartido en medianil
        "recommended_gutter_y_mm": 4.0,
        "default_finishings": ["grapado"],
    },
    "folleto_plegado": {
        "id": "folleto_plegado",
        "name": "Folleto Plegado (Díptico / Tríptico)",
        "description": "Folleto plegado en 2 o 3 cuerpos (envolvente o acordeón).",
        "default_imposition_mode": "step_and_repeat",
        "allowed_imposition_modes": ["step_and_repeat", "2up"],
        "pages_multiple_of": 2,
        "min_pages": 2,
        "standard_trim_mm": (100.0, 210.0),
        "recommended_gutter_x_mm": 4.0,
        "recommended_gutter_y_mm": 4.0,
        "default_finishings": ["plegado"],
    },
    "flyer_volante": {
        "id": "flyer_volante",
        "name": "Flyer Publicitario / Hoja Suelta",
        "description": "Hoja suelta impresa a 1 o 2 caras cortada a sangre.",
        "default_imposition_mode": "step_and_repeat",
        "allowed_imposition_modes": ["step_and_repeat"],
        "pages_multiple_of": 1,
        "min_pages": 1,
        "standard_trim_mm": (148.0, 210.0),  # A5
        "recommended_gutter_x_mm": 4.0,      # Doble corte
        "recommended_gutter_y_mm": 4.0,
        "default_finishings": [],
    },
    "tarjetas_visita": {
        "id": "tarjetas_visita",
        "name": "Tarjetas de Visita Comerciales",
        "description": "Tarjetas de 85 × 55 mm montadas en multipose para guillotina.",
        "default_imposition_mode": "step_and_repeat",
        "allowed_imposition_modes": ["step_and_repeat"],
        "pages_multiple_of": 1,
        "min_pages": 1,
        "standard_trim_mm": (85.0, 55.0),
        "recommended_gutter_x_mm": 4.0,
        "recommended_gutter_y_mm": 4.0,
        "default_finishings": [],
    },
    "cartel_poster": {
        "id": "cartel_poster",
        "name": "Cartel / Póster / Display",
        "description": "Cartelería en gran o medio formato (A3, A2, 50×70 o 70×100).",
        "default_imposition_mode": "step_and_repeat",
        "allowed_imposition_modes": ["step_and_repeat"],
        "pages_multiple_of": 1,
        "min_pages": 1,
        "standard_trim_mm": (420.0, 594.0),  # A2
        "recommended_gutter_x_mm": 0.0,
        "recommended_gutter_y_mm": 0.0,
        "default_finishings": [],
    },
    "packaging_estuche": {
        "id": "packaging_estuche",
        "name": "Packaging / Estuche con Troquel",
        "description": "Caja plegable o estuche en cartoncillo con línea de troquel y hendido.",
        "default_imposition_mode": "step_and_repeat",
        "allowed_imposition_modes": ["step_and_repeat"],
        "pages_multiple_of": 1,
        "min_pages": 1,
        "standard_trim_mm": (200.0, 280.0),
        "recommended_gutter_x_mm": 5.0,
        "recommended_gutter_y_mm": 5.0,
        "default_finishings": ["troquelado"],
        "requires_technical_spot": True,
    },
}

MACHINE_PROFILES = {
    "digital_sra3": {
        "id": "digital_sra3",
        "name": "Prensa Digital SRA3 (Tóner / Inkjet Producción)",
        "type": "digital",
        "standard_sheet": "SRA3",
        "sheet_dimensions_mm": (320.0, 450.0),
        "min_gripper_margin_mm": 8.0,
        "recommended_profile": "DIGITAL_200",
        "waste_setup_sheets": 15,    # Puesta a punto digital mínima
        "waste_percentage": 0.03,    # 3% de merma
        "cip3_zones": 16,
    },
    "offset_b3": {
        "id": "offset_b3",
        "name": "Prensa Offset B3 / Pequeño Formato (50 × 35 cm)",
        "type": "offset",
        "standard_sheet": "B3",
        "sheet_dimensions_mm": (350.0, 500.0),
        "min_gripper_margin_mm": 10.0,
        "recommended_profile": "OFFSET_300",
        "waste_setup_sheets": 70,    # Puesta a punto de tinteros y registro offset medio formato
        "waste_percentage": 0.04,    # 4% de merma de tirada
        "cip3_zones": 16,            # 16 zonas estándar para ancho 50 cm
    },
    "offset_b2": {
        "id": "offset_b2",
        "name": "Prensa Offset Pliego B2 (50 × 70 cm)",
        "type": "offset",
        "standard_sheet": "500X700",
        "sheet_dimensions_mm": (500.0, 700.0),
        "min_gripper_margin_mm": 12.0,
        "recommended_profile": "OFFSET_300",
        "waste_setup_sheets": 120,   # Puesta a punto de tinteros y registro offset
        "waste_percentage": 0.05,    # 5% de merma de tirada
        "cip3_zones": 24,            # 24 zonas para ancho 70 cm
    },
    "offset_b1": {
        "id": "offset_b1",
        "name": "Prensa Offset Gran Formato B1 (70 × 100 cm)",
        "type": "offset",
        "standard_sheet": "500X700",  # Compatible con catálogo estándar
        "sheet_dimensions_mm": (700.0, 1000.0),
        "min_gripper_margin_mm": 15.0,
        "recommended_profile": "OFFSET_300",
        "waste_setup_sheets": 200,
        "waste_percentage": 0.05,
        "cip3_zones": 32,            # 32 zonas para ancho 100 cm
    },
    "plotter_roll": {
        "id": "plotter_roll",
        "name": "Plotter Gran Formato (Rollo / Bobina)",
        "type": "plotter",
        "standard_sheet": "500X700",
        "sheet_dimensions_mm": (500.0, 700.0),
        "min_gripper_margin_mm": 10.0,
        "recommended_profile": "GRAN_FORMATO",
        "waste_setup_sheets": 2,
        "waste_percentage": 0.02,
        "cip3_zones": 16,
    },
}

PAPER_SUBSTRATES = {
    "estucado_brillo": {
        "id": "estucado_brillo",
        "name": "Estucado Brillo (Coated Gloss)",
        "finish_type": "coated",
        "tac_limit": 300,
        "icc_standard": "FOGRA51 / PSO Coated v3",
        "recommended_profile_override": "OFFSET_300",
        "absorption": "Baja (superficie lisa)",
    },
    "estucado_mate": {
        "id": "estucado_mate",
        "name": "Estucado Mate / Semimate (Coated Matte)",
        "finish_type": "coated",
        "tac_limit": 300,
        "icc_standard": "FOGRA51 / PSO Coated v3",
        "recommended_profile_override": "OFFSET_300",
        "absorption": "Baja",
    },
    "offset_uncoated": {
        "id": "offset_uncoated",
        "name": "Offset / No Estucado (Woodfree Uncoated)",
        "finish_type": "uncoated",
        "tac_limit": 280,
        "icc_standard": "FOGRA52 / PSO Uncoated v3",
        "recommended_profile_override": "OFFSET_300",
        "absorption": "Alta (requiere control de ganancia de punto)",
    },
    "periodico_prensa": {
        "id": "periodico_prensa",
        "name": "Papel Prensa Estándar (Newsprint)",
        "finish_type": "newsprint",
        "tac_limit": 240,
        "icc_standard": "WAN-IFRA / ISOnewspaper26v4",
        "recommended_profile_override": "PERIODICO_TAC240",
        "absorption": "Muy Alta (papel absorbente)",
    },
    "cartoncillo_folding": {
        "id": "cartoncillo_folding",
        "name": "Cartoncillo Folding GC1/GC2 (Packaging)",
        "finish_type": "board",
        "tac_limit": 300,
        "icc_standard": "FOGRA51 / Packaging",
        "recommended_profile_override": "PACKAGING_CARTONCILLO",
        "absorption": "Media",
    },
}

FINISHING_OPTIONS = {
    "grapado": {
        "id": "grapado",
        "name": "Grapado en Caballete (2 grapas omega o estándar)",
        "waste_sheets": 25,
        "requires_creep_compensation": True,
    },
    "plegado": {
        "id": "plegado",
        "name": "Plegado Mecánico (Díptico / Tríptico / Cruz)",
        "waste_sheets": 30,
        "requires_creep_compensation": False,
    },
    "plastificado_mate": {
        "id": "plastificado_mate",
        "name": "Plastificado / Peliculado Mate",
        "waste_sheets": 20,
        "requires_creep_compensation": False,
    },
    "plastificado_brillo": {
        "id": "plastificado_brillo",
        "name": "Plastificado / Peliculado Brillo",
        "waste_sheets": 20,
        "requires_creep_compensation": False,
    },
    "barniz_uvi": {
        "id": "barniz_uvi",
        "name": "Barniz Reserva Serigráfico UVI",
        "waste_sheets": 40,
        "requires_spot_ink": "Barniz_UVI",
    },
    "troquelado": {
        "id": "troquelado",
        "name": "Troquelado con Molde y Hendidos",
        "waste_sheets": 50,
        "requires_spot_ink": "Troquel",
    },
}


# ---------------------------------------------------------------------------
# MOTOR DE PROPUESTA DE RECETA Y PLANIFICACIÓN
# ---------------------------------------------------------------------------

def get_production_catalogs() -> Dict[str, Any]:
    """Devuelve los catálogos públicos para los selectores de la interfaz."""
    return {
        "products": list(PRODUCT_RECIPES.values()),
        "machines": list(MACHINE_PROFILES.values()),
        "papers": list(PAPER_SUBSTRATES.values()),
        "finishings": list(FINISHING_OPTIONS.values()),
    }


def propose_production_recipe(
    product_id: str,
    machine_id: str,
    paper_id: str,
    quantity: int = 500,
    finishings: Optional[List[str]] = None,
    page_count: Optional[int] = None,
    trim_width_mm: Optional[float] = None,
    trim_height_mm: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calcula y propone la receta completa de producción conectando Preflight, Imposición y Taller.
    """
    product = PRODUCT_RECIPES.get(product_id) or PRODUCT_RECIPES["catalogo_grapado"]
    if machine_id in ("offset_b3", "offset_50x35", "offset_35x50", "b3", "offset_500x350"):
        machine = MACHINE_PROFILES["offset_b3"]
    else:
        machine = MACHINE_PROFILES.get(machine_id) or MACHINE_PROFILES["digital_sra3"]
    paper = PAPER_SUBSTRATES.get(paper_id) or PAPER_SUBSTRATES["estucado_mate"]
    finishings = finishings or []

    quantity = max(1, int(quantity))

    # 1. Determinación del Perfil Técnico Óptimo
    # Si el papel o la máquina tienen perfiles específicos, priorizarlos
    profile_id = paper.get("recommended_profile_override") or machine.get("recommended_profile")
    if machine["type"] == "plotter":
        profile_id = "GRAN_FORMATO"
    elif product["id"] == "packaging_estuche":
        profile_id = "PACKAGING_CARTONCILLO"

    tac_limit = paper.get("tac_limit", 300)

    # 2. Esquema de Imposición
    imposition_mode = product["default_imposition_mode"]
    sheet_size = machine["standard_sheet"]

    # Orientación óptima según formato de pose
    pose_w, pose_h = (trim_width_mm, trim_height_mm) if (trim_width_mm and trim_height_mm) else product["standard_trim_mm"]
    sheet_w, sheet_h = machine["sheet_dimensions_mm"]

    if imposition_mode == "booklet":
        # En cuadernillo A4 sobre SRA3, el pliego debe ser apaisado
        orientation = "landscape"
    else:
        # En step & repeat, optimizar orientación según dimensiones
        orientation = "landscape" if sheet_h > sheet_w else "portrait"

    gutter_x = product["recommended_gutter_x_mm"]
    gutter_y = product["recommended_gutter_y_mm"]

    # 3. Cálculo de Pliegos y Mermas de Taller
    pages = page_count or product["min_pages"]

    if imposition_mode == "booklet":
        # Un pliego (cara y dorso) alberga 4 páginas del cuadernillo
        sheets_per_book = math.ceil(pages / 4)
        net_sheets = sheets_per_book * quantity
    else:
        # Estimación aproximada de poses por pliego
        # Margen perimetral de 10mm a cada lado
        avail_w = max(50.0, sheet_w - 20.0)
        avail_h = max(50.0, sheet_h - 20.0)
        cols = max(1, int(avail_w // (pose_w + gutter_x)))
        rows = max(1, int(avail_h // (pose_h + gutter_y)))
        poses_per_sheet = max(1, cols * rows)
        sheets_per_copy = 1  # 1 hoja para flyer/tarjeta
        net_sheets = math.ceil(quantity / poses_per_sheet)

    # Merma de puesta a punto de máquina
    setup_waste = machine.get("waste_setup_sheets", 20)
    # Merma por acabados
    finishing_waste = sum(FINISHING_OPTIONS.get(f, {}).get("waste_sheets", 0) for f in finishings)
    # Merma porcentual por tirada
    run_waste = math.ceil(net_sheets * machine.get("waste_percentage", 0.04))

    total_waste = setup_waste + finishing_waste + run_waste
    gross_sheets = net_sheets + total_waste

    # 4. Verificaciones y Advertencias
    warnings = []
    if imposition_mode == "booklet" and pages % 4 != 0:
        missing = 4 - (pages % 4)
        warnings.append(
            f"El catálogo tiene {pages} páginas (no es múltiplo de 4). Se requieren {missing} páginas en blanco o de respeto para el encamizado."
        )

    for f_id in finishings:
        f_info = FINISHING_OPTIONS.get(f_id)
        if f_info and "requires_spot_ink" in f_info:
            warnings.append(
                f"El acabado '{f_info['name']}' exige incluir la tinta técnica directa '{f_info['requires_spot_ink']}' configurada con sobreimpresión."
            )

    return {
        "product": product,
        "machine": machine,
        "paper": paper,
        "quantity": quantity,
        "finishings": [FINISHING_OPTIONS[f] for f in finishings if f in FINISHING_OPTIONS],
        "recommended_profile_id": profile_id,
        "recommended_tac": tac_limit,
        "imposition": {
            "mode": imposition_mode,
            "sheet_size": sheet_size,
            "orientation": orientation,
            "gutter_x_mm": gutter_x,
            "gutter_y_mm": gutter_y,
            "bleed_mm": 3.0,
            "sheet_margin_mm": machine.get("min_gripper_margin_mm", 10.0),
            "marks": {
                "cut_marks": True,
                "reg_marks": True,
                "densitometer": True,
                "slug": True,
            },
        },
        "cip3_recommendation": {
            "zones": machine.get("cip3_zones", 16),
            "description": f"{machine.get('cip3_zones', 16)} zonas clave de tinta (ancho {sheet_w:.0f} mm)",
        },
        "material_calculation": {
            "page_count": pages,
            "quantity_ordered": quantity,
            "net_sheets": net_sheets,
            "setup_waste_sheets": setup_waste,
            "finishing_waste_sheets": finishing_waste,
            "run_waste_sheets": run_waste,
            "total_waste_sheets": total_waste,
            "gross_sheets": gross_sheets,
            "waste_ratio_percent": round((total_waste / gross_sheets) * 100, 1) if gross_sheets > 0 else 0,
        },
        "warnings": warnings,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def validate_pdf_against_order(
    job_data: Dict[str, Any],
    order_recipe: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Valida si el PDF cargado en el trabajo cumple las restricciones de la Orden de Producción.
    Devuelve lista de no conformidades detectadas.
    """
    findings = []
    meta = job_data.get("job_meta") or {}
    pages = (job_data.get("paginas") or {}).get("total_paginas") or meta.get("page_count") or 1

    prod_id = order_recipe.get("product", {}).get("id")

    # 1. Regla de páginas para cuadernillo grapado
    if prod_id == "catalogo_grapado":
        if pages % 4 != 0:
            findings.append({
                "type": "error",
                "code": "PO_BOOKLET_PAGES_NOT_MULTIPLE_OF_4",
                "message": f"El PDF contiene {pages} páginas. Un catálogo grapado exige obligatoriamente páginas múltiplos de 4.",
                "solution": f"Añade {4 - (pages % 4)} página(s) de respeto, índice o cortesía al final de la publicación.",
            })

    # 2. Tintas técnicas exigidas por acabados
    finishings = order_recipe.get("finishings") or []
    separations = job_data.get("separaciones") or {}
    spot_names = [s.get("nombre", "").lower() for s in separations.get("tintas_directas", [])]

    for fin in finishings:
        req_ink = fin.get("requires_spot_ink")
        if req_ink:
            found = any(req_ink.lower() in name for name in spot_names)
            if not found:
                findings.append({
                    "type": "warning",
                    "code": "PO_MISSING_TECHNICAL_SPOT",
                    "message": f"El acabado '{fin.get('name')}' requiere la separación de tinta directa técnica '{req_ink}', pero no se detectó en el PDF.",
                    "solution": f"Define la capa o trazo con tinta plana llamada '{req_ink}' y activa la sobreimpresión de trazo en InDesign/Illustrator.",
                })

    # 3. Límite TAC de papel
    measured_tac = (job_data.get("analisis_tac") or {}).get("tac_maximo") or (job_data.get("job_summary") or {}).get("tac_measurement", {}).get("peak_percent", 0)
    allowed_tac = order_recipe.get("recommended_tac", 300)
    if measured_tac > allowed_tac:
        findings.append({
            "type": "warning",
            "code": "PO_TAC_EXCEEDS_PAPER_LIMIT",
            "message": f"El papel seleccionado ({order_recipe.get('paper', {}).get('name')}) admite un TAC máximo de {allowed_tac} %, pero el PDF alcanza {measured_tac} %.",
            "solution": f"Aplica la corrección automática 'Limitar TAC a {allowed_tac} %' en el panel de herramientas.",
        })

    return findings


# ---------------------------------------------------------------------------
# GENERADOR DE HOJA DE RUTA / JOB TICKET PDF (A4 TALLER)
# ---------------------------------------------------------------------------

def generate_job_ticket_pdf(
    order_recipe: Dict[str, Any],
    job_data: Dict[str, Any],
    output_path: Path | str,
) -> Path:
    """
    Genera la Hoja de Ruta de Taller (Job Ticket) oficial en formato A4 para imprimir y acompañar la tirada.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open()
    # A4 vertical: 595.3 x 841.9 pt
    page = doc.new_page(width=595.3, height=841.9)

    meta = job_data.get("job_meta") or {}
    job_id = meta.get("job_id") or "TRABAJO_SIN_ID"
    filename = meta.get("filename") or "documento.pdf"

    prod = order_recipe.get("product") or {}
    mach = order_recipe.get("machine") or {}
    pap = order_recipe.get("paper") or {}
    mat = order_recipe.get("material_calculation") or {}
    imp = order_recipe.get("imposition") or {}

    c_navy = (0.08, 0.12, 0.22)
    c_blue = (0.13, 0.40, 0.85)
    c_slate = (0.40, 0.45, 0.52)
    c_bg_light = (0.95, 0.96, 0.98)
    c_border = (0.82, 0.86, 0.90)
    c_amber = (0.85, 0.55, 0.10)
    c_white = (1.0, 1.0, 1.0)

    # 1. ENCABEZADO
    page.draw_rect(pymupdf.Rect(0, 0, 595.3, 75), color=None, fill=c_navy)
    page.insert_text(pymupdf.Point(35, 32), "INTELLIPRINT · PREPRESS & WORKSHOP SUITE", fontsize=9, color=(0.4, 0.7, 1.0), fontname="helv")
    page.insert_text(pymupdf.Point(35, 54), "ORDEN DE PRODUCCIÓN & HOJA DE RUTA DE TALLER", fontsize=15, color=c_white, fontname="hebo")

    page.insert_text(pymupdf.Point(400, 32), f"JOB ID: {job_id}", fontsize=11, color=c_white, fontname="hebo")
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    page.insert_text(pymupdf.Point(400, 48), f"Fecha: {date_str}", fontsize=8.5, color=(0.7, 0.75, 0.85), fontname="helv")

    y = 95.0

    # 2. BLOQUE 1: DATOS DEL PEDIDO Y PRODUCTO
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 90), color=c_border, fill=c_bg_light, width=0.8)
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 22), color=None, fill=(0.90, 0.92, 0.96))
    page.insert_text(pymupdf.Point(45, y + 15), "1. ESPECIFICACIÓN DEL PRODUCTO Y TIRADA", fontsize=9.5, color=c_navy, fontname="hebo")

    y_t = y + 38
    page.insert_text(pymupdf.Point(45, y_t), "Producto:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(115, y_t), str(prod.get("name", "N/A")), fontsize=8.5, color=c_navy, fontname="hebo")

    page.insert_text(pymupdf.Point(340, y_t), "Tirada Requerida:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(435, y_t), f"{mat.get('quantity_ordered', 500)} ejemplares", fontsize=8.5, color=c_navy, fontname="hebo")

    y_t += 18
    page.insert_text(pymupdf.Point(45, y_t), "Archivo PDF:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(115, y_t), str(filename)[:45], fontsize=8.5, color=c_navy, fontname="helv")

    page.insert_text(pymupdf.Point(340, y_t), "Páginas del PDF:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(435, y_t), f"{mat.get('page_count', 1)} páginas", fontsize=8.5, color=c_navy, fontname="helv")

    y_t += 18
    finishings_names = ", ".join(f.get("name", "") for f in order_recipe.get("finishings", [])) or "Sin acabados especiales"
    page.insert_text(pymupdf.Point(45, y_t), "Acabados:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(115, y_t), finishings_names[:65], fontsize=8.5, color=c_navy, fontname="helv")

    y += 105

    # 3. BLOQUE 2: MÁQUINA, SOPORTE Y CRITERIOS TÉCNICOS
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 90), color=c_border, fill=c_bg_light, width=0.8)
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 22), color=None, fill=(0.90, 0.92, 0.96))
    page.insert_text(pymupdf.Point(45, y + 15), "2. MAQUINARIA, PAPEL Y PERFIL DE COLOR", fontsize=9.5, color=c_navy, fontname="hebo")

    y_t = y + 38
    page.insert_text(pymupdf.Point(45, y_t), "Máquina Impresión:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(145, y_t), str(mach.get("name", "N/A")), fontsize=8.5, color=c_navy, fontname="hebo")

    page.insert_text(pymupdf.Point(340, y_t), "Pliego Máquina:", fontsize=8.5, color=c_slate, fontname="hebo")
    dims = mach.get("sheet_dimensions_mm", (0, 0))
    page.insert_text(pymupdf.Point(435, y_t), f"{mach.get('standard_sheet')} ({dims[0]:.0f} × {dims[1]:.0f} mm)", fontsize=8.5, color=c_navy, fontname="helv")

    y_t += 18
    page.insert_text(pymupdf.Point(45, y_t), "Soporte / Papel:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(145, y_t), str(pap.get("name", "N/A")), fontsize=8.5, color=c_navy, fontname="helv")

    page.insert_text(pymupdf.Point(340, y_t), "Límite TAC Papel:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(435, y_t), f"{pap.get('tac_limit', 300)} % máximo", fontsize=8.5, color=c_navy, fontname="hebo")

    y_t += 18
    page.insert_text(pymupdf.Point(45, y_t), "Perfil Preflight:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(145, y_t), f"{order_recipe.get('recommended_profile_id')} ({pap.get('icc_standard', 'ISO 12647')})", fontsize=8.5, color=c_navy, fontname="helv")

    page.insert_text(pymupdf.Point(340, y_t), "Pinza / CIP3:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(435, y_t), f"Pinza {mach.get('min_gripper_margin_mm', 10.0):.0f} mm · {mach.get('cip3_zones', 16)} zonas CIP3", fontsize=8.5, color=c_navy, fontname="helv")

    y += 105

    # 4. BLOQUE 3: IMPOSICIÓN Y CÁLCULO DE CONSUMO DE PLIEGOS (MATERIALES)
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 105), color=c_border, fill=c_bg_light, width=0.8)
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 22), color=None, fill=(0.90, 0.92, 0.96))
    page.insert_text(pymupdf.Point(45, y + 15), "3. PLAN DE MONTAJE E IMPOSICIÓN Y CONSUMO DE PLIEGOS", fontsize=9.5, color=c_navy, fontname="hebo")

    y_t = y + 38
    im_mode_lbl = "Cuadernillo (Saddle-Stitch Grapado 2-Up)" if imp.get("mode") == "booklet" else "Paso y Repetición (N-Up Multipose)"
    page.insert_text(pymupdf.Point(45, y_t), "Modo de Montaje:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(145, y_t), im_mode_lbl, fontsize=8.5, color=c_navy, fontname="hebo")

    page.insert_text(pymupdf.Point(340, y_t), "Orientación:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(435, y_t), str(imp.get("orientation", "landscape")).capitalize(), fontsize=8.5, color=c_navy, fontname="helv")

    y_t += 18
    page.insert_text(pymupdf.Point(45, y_t), "Calles de Corte:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(145, y_t), f"X: {imp.get('gutter_x_mm', 0)} mm · Y: {imp.get('gutter_y_mm', 0)} mm", fontsize=8.5, color=c_navy, fontname="helv")

    page.insert_text(pymupdf.Point(340, y_t), "Sangrado Pose:", fontsize=8.5, color=c_slate, fontname="hebo")
    page.insert_text(pymupdf.Point(435, y_t), f"{imp.get('bleed_mm', 3.0)} mm estándar", fontsize=8.5, color=c_navy, fontname="helv")

    # Tabla resumen de pliegos y mermas
    y_t += 18
    page.draw_rect(pymupdf.Rect(45, y_t, 550, y_t + 22), color=(0.7, 0.8, 0.9), fill=(0.88, 0.92, 0.98), width=0.5)
    page.insert_text(pymupdf.Point(52, y_t + 15), f"Pliegos Netos: {mat.get('net_sheets', 0)}", fontsize=8.5, color=c_navy, fontname="hebo")
    page.insert_text(pymupdf.Point(175, y_t + 15), f"+ Merma Puesta Punto: {mat.get('setup_waste_sheets', 0)}", fontsize=8, color=c_slate, fontname="helv")
    page.insert_text(pymupdf.Point(310, y_t + 15), f"+ Merma Acabados: {mat.get('finishing_waste_sheets', 0)}", fontsize=8, color=c_slate, fontname="helv")
    page.insert_text(pymupdf.Point(420, y_t + 15), f"TOTAL BRUTO: {mat.get('gross_sheets', 0)} pliegos", fontsize=9, color=(0.1, 0.5, 0.2), fontname="hebo")

    y += 120

    # 5. BLOQUE 4: VALIDACIÓN DE COHERENCIA Y ADVERTENCIAS
    warnings = order_recipe.get("warnings") or []
    box_h = 70 if warnings else 50
    page.draw_rect(pymupdf.Rect(35, y, 560, y + box_h), color=c_border, fill=c_bg_light, width=0.8)
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 20), color=None, fill=(0.95, 0.90, 0.85) if warnings else (0.90, 0.94, 0.90))
    title_text = "4. ADVERTENCIAS TÉCNICAS Y REQUISITOS DE CONTROL" if warnings else "4. VERIFICACIÓN DE COMPATIBILIDAD CON LA ORDEN"
    page.insert_text(pymupdf.Point(45, y + 14), title_text, fontsize=9, color=c_amber if warnings else (0.1, 0.5, 0.2), fontname="hebo")

    if warnings:
        w_y = y + 33
        for w in warnings[:3]:
            page.insert_text(pymupdf.Point(45, w_y), f"• {w[:95]}", fontsize=8, color=(0.7, 0.2, 0.1), fontname="helv")
            w_y += 13
    else:
        page.insert_text(pymupdf.Point(45, y + 35), "✓ El archivo PDF y los parámetros seleccionados son coherentes con las exigencias de taller.", fontsize=8.5, color=(0.1, 0.5, 0.2), fontname="hebo")

    y += box_h + 15

    # 6. BLOQUE 5: SEGUIMIENTO DE FASES Y FIRMAS DE TALLER (HOJA DE RUTA)
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 120), color=c_border, fill=c_white, width=1.0)
    page.draw_rect(pymupdf.Rect(35, y, 560, y + 20), color=None, fill=c_navy)
    page.insert_text(pymupdf.Point(45, y + 14), "5. SEGUIMIENTO DE FASES Y VISTO BUENO DE TALLER (FIRMAS)", fontsize=9, color=c_white, fontname="hebo")

    col_w = (560 - 35) / 3.0  # 175 pt
    col1_x = 35
    col2_x = 35 + col_w
    col3_x = 35 + 2 * col_w

    # Líneas separadoras
    page.draw_line(pymupdf.Point(col2_x, y + 20), pymupdf.Point(col2_x, y + 120), color=c_border, width=0.8)
    page.draw_line(pymupdf.Point(col3_x, y + 20), pymupdf.Point(col3_x, y + 120), color=c_border, width=0.8)

    # Fase 1: Preimpresión
    page.insert_text(pymupdf.Point(col1_x + 10, y + 34), "FASE 1: PREIMPRESIÓN", fontsize=8, color=c_navy, fontname="hebo")
    page.insert_text(pymupdf.Point(col1_x + 10, y + 46), "Preflight OK · Imposición y CIP3", fontsize=7.5, color=c_slate, fontname="helv")
    page.insert_text(pymupdf.Point(col1_x + 10, y + 70), "Firma Operador:", fontsize=7, color=c_slate, fontname="helv")
    page.draw_line(pymupdf.Point(col1_x + 10, y + 95), pymupdf.Point(col1_x + col_w - 15, y + 95), color=c_border, width=0.5)
    page.insert_text(pymupdf.Point(col1_x + 10, y + 108), "Fecha/Hora: ____/____/____", fontsize=7, color=c_slate, fontname="helv")

    # Fase 2: Impresión
    page.insert_text(pymupdf.Point(col2_x + 10, y + 34), "FASE 2: IMPRESIÓN (PRENSA)", fontsize=8, color=c_navy, fontname="hebo")
    page.insert_text(pymupdf.Point(col2_x + 10, y + 46), "Puesta a punto · Tinteros CIP3", fontsize=7.5, color=c_slate, fontname="helv")
    page.insert_text(pymupdf.Point(col2_x + 10, y + 60), "Pliegos impresos reales: ________", fontsize=7.5, color=c_slate, fontname="helv")
    page.insert_text(pymupdf.Point(col2_x + 10, y + 75), "Firma Maquinista:", fontsize=7, color=c_slate, fontname="helv")
    page.draw_line(pymupdf.Point(col2_x + 10, y + 95), pymupdf.Point(col2_x + col_w - 15, y + 95), color=c_border, width=0.5)
    page.insert_text(pymupdf.Point(col2_x + 10, y + 108), "Fecha/Hora: ____/____/____", fontsize=7, color=c_slate, fontname="helv")

    # Fase 3: Postimpresión y Acabados
    page.insert_text(pymupdf.Point(col3_x + 10, y + 34), "FASE 3: ACABADOS Y ENTREGA", fontsize=8, color=c_navy, fontname="hebo")
    page.insert_text(pymupdf.Point(col3_x + 10, y + 46), "Corte · Plegado · Grapado", fontsize=7.5, color=c_slate, fontname="helv")
    page.insert_text(pymupdf.Point(col3_x + 10, y + 60), "Ejemplares entregados: ________", fontsize=7.5, color=c_slate, fontname="helv")
    page.insert_text(pymupdf.Point(col3_x + 10, y + 75), "Firma Responsable:", fontsize=7, color=c_slate, fontname="helv")
    page.draw_line(pymupdf.Point(col3_x + 10, y + 95), pymupdf.Point(col3_x + col_w - 15, y + 95), color=c_border, width=0.5)
    page.insert_text(pymupdf.Point(col3_x + 10, y + 108), "Fecha/Hora: ____/____/____", fontsize=7, color=c_slate, fontname="helv")

    # PIE DE PÁGINA
    page.draw_rect(pymupdf.Rect(35, 805, 560, 806), color=c_border, fill=None)
    page.insert_text(pymupdf.Point(35, 820), "CPIFP Salesianos Urnieta LHIPI · CIFP Mendizabala LHII · Departamento de Educación del Gobierno Vasco", fontsize=7.5, color=c_slate, fontname="helv")
    page.insert_text(pymupdf.Point(475, 820), "IntelliPrint 2026", fontsize=7.5, color=c_navy, fontname="hebo")

    with atomic_output(output_path) as tmp:
        doc.save(str(tmp))
    doc.close()
    return output_path

