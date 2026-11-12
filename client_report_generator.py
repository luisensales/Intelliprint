"""
client_report_generator.py
==========================
Generador de Informe Pedagógico para el Cliente y Diseñador (páginas A4).

Produce una guía visual, comprensible y sin tecnicismos hostiles que el
taller de imprenta puede remitir al diseñador/cliente explicando exactamente
qué incidencias se detectaron en su PDF y cómo solucionarlas en InDesign / Illustrator.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

import pymupdf

from report_images import collect_report_image_issues

PAGE_W = 595.3
PAGE_H = 841.9
MARGIN_X = 35.0
CONTENT_W = PAGE_W - 2 * MARGIN_X  # 525.3 pt
HEADER_H = 70.0
FOOTER_Y = 808.0


def _palette():
    return {
        "navy": (31 / 255, 38 / 255, 44 / 255),
        "blue": (0.13, 0.40, 0.85),
        "indigo": (0.28, 0.25, 0.75),
        "slate": (0.35, 0.40, 0.48),
        "slate_dark": (0.12, 0.16, 0.22),
        "light": (0.96, 0.97, 0.99),
        "green": (0.10, 0.60, 0.35),
        "green_bg": (0.93, 0.98, 0.94),
        "green_border": (0.60, 0.85, 0.68),
        "amber": (0.85, 0.50, 0.05),
        "amber_bg": (0.99, 0.96, 0.90),
        "amber_border": (0.92, 0.78, 0.55),
        "red": (0.85, 0.20, 0.20),
        "red_bg": (0.99, 0.93, 0.93),
        "red_border": (0.92, 0.68, 0.68),
        "border": (0.82, 0.86, 0.90),
    }


def _draw_header(page: pymupdf.Page, assets_dir: Path, p: dict):
    """Dibuja la cabecera corporativa con logos institucionales."""
    page.draw_rect(pymupdf.Rect(0, 0, PAGE_W, HEADER_H), fill=p["navy"])

    imago_path = assets_dir / "Logo-intelliprint-imago.png"
    if not imago_path.exists():
        imago_path = assets_dir / "Logo-intelliprint-imago.jpg"
    full_logo_path = assets_dir / "Logo-intelliprint.png"
    if not full_logo_path.exists():
        full_logo_path = assets_dir / "Logo-intelliprint.jpg"

    if imago_path.exists():
        page.insert_image(pymupdf.Rect(26, 12, 74, 58), filename=str(imago_path), keep_proportion=True)
        text_x = 82
    elif full_logo_path.exists():
        page.insert_image(pymupdf.Rect(26, 14, 146, 54), filename=str(full_logo_path), keep_proportion=True)
        text_x = 154
    else:
        text_x = 35

    page.insert_text(pymupdf.Point(text_x, 28), "Intelli", fontsize=12.5, color=(1, 1, 1), fontname="helv")
    w_intelli = pymupdf.get_text_length("Intelli", fontname="helv", fontsize=12.5)
    page.insert_text(pymupdf.Point(text_x + w_intelli, 28), "Print", fontsize=12.5, color=(0.0, 0.64, 1.0), fontname="hebo")
    w_print = pymupdf.get_text_length("Print", fontname="hebo", fontsize=12.5)
    page.insert_text(pymupdf.Point(text_x + w_intelli + w_print + 5, 28), "· GUÍA DE ARTE FINAL", fontsize=9.5, color=(0.85, 0.90, 0.95), fontname="helv")
    page.insert_text(
        pymupdf.Point(text_x, 41),
        "Informe pedagógico para el diseñador y cliente",
        fontsize=7.6,
        color=(0.78, 0.85, 0.92),
        fontname="helv",
    )
    page.insert_text(
        pymupdf.Point(text_x, 52),
        "Control de calidad y preflight de arte final para imprenta",
        fontsize=7.2,
        color=(0.65, 0.74, 0.84),
        fontname="helv",
    )

    p_sales = assets_dir / "logo-salesianos.png"
    p_mendi = assets_dir / "logo-mendizabala.png"
    p_edu = assets_dir / "logo-dept-educacion-1.png"

    if p_sales.exists() and p_mendi.exists() and p_edu.exists():
        capsule = pymupdf.Rect(340, 12, 567, 58)
        page.draw_rect(capsule, fill=(1, 1, 1), radius=0.08)
        x0 = 346
        slot_w = 68.0
        r_sales = pymupdf.Rect(x0, 16, x0 + slot_w, 54)
        page.insert_image(r_sales, filename=str(p_sales), keep_proportion=True)
        div1_x = x0 + slot_w + 3.0
        page.draw_line(pymupdf.Point(div1_x, 18), pymupdf.Point(div1_x, 52), color=(0.88, 0.88, 0.88), width=0.6)
        
        x1 = div1_x + 4.0
        r_mendi = pymupdf.Rect(x1, 16, x1 + slot_w, 54)
        page.insert_image(r_mendi, filename=str(p_mendi), keep_proportion=True)
        div2_x = x1 + slot_w + 3.0
        page.draw_line(pymupdf.Point(div2_x, 18), pymupdf.Point(div2_x, 52), color=(0.88, 0.88, 0.88), width=0.6)
        
        x2 = div2_x + 4.0
        r_edu = pymupdf.Rect(x2, 16, 561, 54)
        page.insert_image(r_edu, filename=str(p_edu), keep_proportion=True)

        # Enlaces interactivos en los logotipos de la cabecera PDF
        page.insert_link({"kind": pymupdf.LINK_URI, "from": r_sales, "uri": "https://salesianosurnieta.com/"})
        page.insert_link({"kind": pymupdf.LINK_URI, "from": r_mendi, "uri": "https://www.mendizabala.eus/"})
        page.insert_link({"kind": pymupdf.LINK_URI, "from": r_edu, "uri": "https://www.euskadi.eus/gobierno-vasco/departamento-educacion/"})


def _draw_footer(page: pymupdf.Page, p: dict, job_id: str):
    """Dibuja el pie de página institucional del informe."""
    page.draw_line(
        pymupdf.Point(MARGIN_X, FOOTER_Y),
        pymupdf.Point(PAGE_W - MARGIN_X, FOOTER_Y),
        color=p["border"],
        width=0.5,
    )
    page.insert_text(
        pymupdf.Point(MARGIN_X, FOOTER_Y + 12),
        "IntelliPrint Preflight · Proyecto de Innovación Aplicada en FP · Salesianos Urnieta / CIFP Mendizabala LHII",
        fontsize=7.2,
        fontname="helv",
        color=p["slate"],
    )
    page.insert_text(
        pymupdf.Point(PAGE_W - MARGIN_X - 100, FOOTER_Y + 12),
        f"Ref. Trabajo: {job_id[:16]}",
        fontsize=7.2,
        fontname="helv",
        color=p["slate"],
    )
    page.insert_text(
        pymupdf.Point(MARGIN_X, FOOTER_Y + 22),
        "Este informe ha sido generado para facilitar una comunicación clara y constructiva entre el diseñador y la imprenta.",
        fontsize=6.8,
        fontname="helv",
        color=(0.55, 0.60, 0.68),
    )


def _extract_pedagogical_items(job_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Analiza las incidencias técnicas y las traduce a explicaciones pedagógicas
    orientadas a diseñadores (con instrucciones para InDesign / Illustrator / Photoshop).
    """
    findings = job_data.get("findings", [])
    summary = job_data.get("job_summary", {})
    items = []

    # Resolución: conservar la gravedad del preflight, también si no fue medible.
    resolution_findings = [
        f for f in findings
        if f.get("rule_id") == "PRINT_IMAGE_EFFECTIVE_PPI"
        and f.get("severity") in ("ERROR", "WARNING")
    ]
    low_res_images = summary.get("low_res_images", 0)
    if resolution_findings or low_res_images > 0:
        errors = sum(f.get("severity") == "ERROR" for f in resolution_findings)
        warnings = sum(f.get("severity") == "WARNING" for f in resolution_findings)
        pages = sorted({
            f["page"] for f in resolution_findings
            if isinstance(f.get("page"), int) and f["page"] > 0
        })
        pages_text = ", ".join(str(page) for page in pages[:4]) or "sin indicar"
        if len(pages) > 4:
            pages_text += f" y {len(pages) - 4} más"
        target_dpi = summary.get("target_dpi", 300)
        counts = f"{errors} {'error' if errors == 1 else 'errores'} y {warnings} {'aviso' if warnings == 1 else 'avisos'}"
        if not resolution_findings:
            counts = f"{low_res_images} imágenes por debajo de {target_dpi} ppp"
        items.append({
            "category": "resolution",
            "icon": "RESOLUCIÓN",
            "severity": "CRÍTICO" if errors else "AVISO",
            "title": "Resolución de Imágenes Insuficiente o No Verificable",
            "problem": f"{counts}. Págs.: {pages_text}. Riesgo de pixelado o nitidez sin verificar.",
            "solution": [
                f"En InDesign / Illustrator: revisa los vínculos y usa originales con al menos {target_dpi} ppp al tamaño final.",
                "Reduce el tamaño colocado o sustituye la imagen; aumentar los ppp por remuestreo no recupera detalle."
            ]
        })

    # 1. Sangrado (Bleed)
    has_bleed_err = any(f.get("rule_id") == "BLEED_GEOMETRY_3MM" for f in findings)
    if has_bleed_err or summary.get("bleed_status") == "FAIL":
        items.append({
            "category": "bleed",
            "icon": "SANGRADO",
            "severity": "CRÍTICO",
            "title": "Falta Sangrado Perimetral (+3 mm en los 4 bordes)",
            "problem": "El diseño termina en el borde exacto de corte. Al cortar en la guillotina de imprenta, cualquier oscilación mínima del papel provocará filetes o líneas blancas no deseadas en los extremos.",
            "solution": [
                "En InDesign: Archivo > Ajustar documento > Sangrado: escribe 3 mm en los 4 lados.",
                "Estira todos los fondos, imágenes y colores que toquen el borde hasta la GUÍA ROJA exterior.",
                "Al exportar el PDF: en la pestaña 'Marcas y sangrados', activa 'Utilizar configuración de sangrado del documento'."
            ]
        })

    # 2. Modo de color RGB
    has_rgb_err = any(f.get("rule_id") == "SOURCE_COLOR_DIAGNOSTIC" for f in findings)
    non_cmyk_imgs = summary.get("non_cmyk_images", 0)
    if has_rgb_err or (non_cmyk_imgs > 0 and summary.get("required_color_family", "CMYK") == "CMYK"):
        items.append({
            "category": "rgb",
            "icon": "COLOR",
            "severity": "CRÍTICO",
            "title": f"Imágenes en Modo de Color RGB ({non_cmyk_imgs} detectadas)",
            "problem": "Las imágenes están en RGB (espacio de luz para pantallas). En imprenta se imprime con 4 tintas CMYK (Cian, Magenta, Amarillo y Negro). Una conversión imprevista puede apagar colores vivos.",
            "solution": [
                "En Photoshop: Imagen > Modo > Color CMYK (con perfil estándar ISO Coated v2 o FOGRA39).",
                "O en InDesign al exportar PDF: Salida > Conversión de color: 'Convertir a destino (mantener valores)' indicando perfil de destino Documento CMYK - ISO Coated v2."
            ]
        })

    # 3. Tipografías no incrustadas
    has_font_err = any(f.get("rule_id") == "USED_FONTS_EMBEDDED" for f in findings)
    if has_font_err:
        items.append({
            "category": "fonts",
            "icon": "FUENTES",
            "severity": "AVISO",
            "title": "Tipografías No Incrustadas en el PDF",
            "problem": "El archivo PDF no contiene las fuentes tipográficas. Si el procesador (RIP) de la imprenta no dispone de la misma fuente instalada, se sustituirá por otra deformando el diseño.",
            "solution": [
                "En InDesign / Illustrator: selecciona los textos y pulsa Texto > Crear contornos (Ctrl+Shift+O).",
                "O exporta como PDF/X-4 o PDF/X-1a, estándares de la industria que garantizan la incrustación íntegra de las fuentes."
            ]
        })

    # 4. Textos negros en cuatricromía / calado
    has_black_err = any(
        f.get("rule_id") in ("BLACK_TEXT_KNOCKOUT", "BLACK_TEXT_KNOCKOUT_100", "RICH_BLACK_SMALL_TEXT", "WHITE_OVERPRINT")
        for f in findings
    )
    if has_black_err:
        items.append({
            "category": "black",
            "icon": "NEGRO",
            "severity": "AVISO",
            "title": "Textos Pequeños en Negro Compuesto (C+M+Y+K) o en Calado",
            "problem": "Hay texto de lectura menor de 12 pt compuesto por las cuatro tintas. En máquina offset, cualquier microdesajuste de registro entre planchas creará halos de color o texto borroso.",
            "solution": [
                "Aplica a todos los textos de lectura la muestra pura [Negro] 100% K (0 C / 0 M / 0 Y / 100 K).",
                "En InDesign: Preferencias > Apariencia de negro > comprueba que esté marcada la opción 'Sobreimprimir negro al 100%'."
            ]
        })

    # 5. Filetes ultrafinos (Hairlines < 0.25 pt)
    has_hairline_err = any(
        f.get("rule_id") in ("HAIRLINE_WIDTH", "HAIRLINE_STROKE", "HAIRLINE_DETECTED")
        for f in findings
    )
    if has_hairline_err:
        items.append({
            "category": "hairlines",
            "icon": "TRAZOS",
            "severity": "AVISO",
            "title": "Filetes o Líneas Demasiado Finas (< 0.25 pt)",
            "problem": "Hay trazos con un grosor menor de 0.25 pt. En el grabado CTP de planchas offset, estas líneas son tan débiles que desaparecen y no imprimen en el papel.",
            "solution": [
                "En la ventana Trazo de InDesign / Illustrator: aumenta el grosor de todas las líneas a un mínimo de 0.30 pt o 0.50 pt."
            ]
        })

    # 6. Tintas planas / Pantone sin descomponer
    has_spots = any(f.get("rule_id") in ("SPOT_COLOR_FOUND", "SPOT_COLOR_NOT_ALLOWED") for f in findings)
    if has_spots:
        items.append({
            "category": "spots",
            "icon": "TINTAS",
            "severity": "INFO",
            "title": "Tintas Planas (Pantone) en Trabajo de Cuatricromía",
            "problem": "El archivo incluye tintas directas especiales. Si tu tirada está contratada a 4 tintas CMYK, las tintas planas deben descomponerse para no requerir planchas adicionales.",
            "solution": [
                "En InDesign: Ventana > Muestras > doble clic en la muestra Pantone > Tipo de color: cambiar a 'Proceso'."
            ]
        })

    # 7. Cobertura de tinta excesiva (TAC > 300%)
    has_tac_err = any(f.get("rule_id") == "MAX_INK_COVERAGE" for f in findings)
    if has_tac_err:
        items.append({
            "category": "tac",
            "icon": "TINTA",
            "severity": "AVISO",
            "title": "Cobertura Total de Tinta Excesiva (> 300%)",
            "problem": "Zonas oscuras del documento acumulan más del 300% de suma de tintas (C+M+Y+K). Esto satura el papel y provoca repintado (manchas) al apilar los pliegos en máquina.",
            "solution": [
                "Al exportar tu PDF en InDesign: Salida > Destino: selecciona el perfil estándar 'ISO Coated v2 300% (ECI)' que limita la tinta automáticamente."
            ]
        })

    # 8. Margen de seguridad de corte (TrimBox < 3 mm)
    has_safety_margin_err = any(f.get("rule_id") == "SAFETY_MARGIN_TRIMBOX" for f in findings)
    if has_safety_margin_err:
        items.append({
            "category": "safety_margin",
            "icon": "CORTE",
            "severity": "AVISO",
            "title": "Textos Próximos a la Línea de Corte (< 3 mm)",
            "problem": "Se han detectado textos o elementos vivos a menos de 3 mm de la línea de corte (TrimBox). La guillotina de corte tiene una tolerancia mecánica de ±1 mm; si los elementos están muy pegados al borde, corren riesgo de quedar amputados o visualmente descompensados.",
            "solution": [
                "En InDesign / Illustrator: activa las guías de márgenes (Márgenes y columnas) y sitúa los textos al menos a 3 mm hacia el interior del borde de página.",
                "Mantén una distancia prudencial en titulares y pies de página para garantizar un margen visual limpio tras el guillotinado."
            ]
        })

    if summary.get("required_color_family") == "RGB":
        for item in items:
            if item["category"] == "rgb":
                item["title"] = "Imágenes CMYK en un documento para pantalla (RGB)"
                item["problem"] = "El destino exige RGB. Las imágenes CMYK pueden mostrar colores apagados en pantallas y navegadores."
                item["solution"] = [
                    "En Photoshop: convierte las imágenes al perfil sRGB y actualiza los vínculos en el documento.",
                    "Exporta el PDF con el perfil RGB acordado para pantalla y vuelve a verificarlo."
                ]

    rules_by_category = {
        "resolution": {"PRINT_IMAGE_EFFECTIVE_PPI"},
        "bleed": {"BLEED_GEOMETRY_3MM"},
        "rgb": {"SOURCE_COLOR_DIAGNOSTIC"},
        "fonts": {"USED_FONTS_EMBEDDED"},
        "black": {"BLACK_TEXT_KNOCKOUT", "BLACK_TEXT_KNOCKOUT_100", "RICH_BLACK_SMALL_TEXT", "WHITE_OVERPRINT"},
        "hairlines": {"HAIRLINE_WIDTH", "HAIRLINE_STROKE", "HAIRLINE_DETECTED"},
        "spots": {"SPOT_COLOR_FOUND", "SPOT_COLOR_NOT_ALLOWED"},
        "tac": {"MAX_INK_COVERAGE"},
        "safety_margin": {"SAFETY_MARGIN_TRIMBOX"},
    }
    handled = set().union(*rules_by_category.values())
    for item in items:
        current = [f for f in findings if f.get("rule_id") in rules_by_category[item["category"]]]
        if current:
            item["severity"] = ("CRÍTICO" if any(f.get("severity") == "ERROR" for f in current)
                                else "AVISO" if any(f.get("severity") == "WARNING" for f in current) else "INFO")
            pages = sorted({f["page"] for f in current if isinstance(f.get("page"), int) and f["page"] > 0})
            item["detail"] = f"Incidencias: {len(current)}. Páginas: {', '.join(map(str, pages)) or 'sin indicar'}."
    # Las reglas sin guía específica también deben aparecer en la ficha.
    other_rules = {}
    for finding in findings:
        if finding.get("rule_id") not in handled and finding.get("severity") in ("ERROR", "WARNING"):
            other_rules.setdefault(finding.get("rule_id"), []).append(finding)
    for rule_id, current in other_rules.items():
        messages = list(dict.fromkeys(f.get("message") or f.get("title") or "Revisión técnica pendiente." for f in current))
        items.append({
            "category": rule_id or "other",
            "icon": "REVISIÓN",
            "severity": "CRÍTICO" if any(f.get("severity") == "ERROR" for f in current) else "AVISO",
            "title": current[0].get("title") or "Incidencia técnica pendiente",
            "problem": "\n".join(messages),
            "solution": ["Revisa esta incidencia en el documento de origen y vuelve a exportar el PDF con el perfil acordado con el taller."],
        })

    severity_order = {"CRÍTICO": 0, "AVISO": 1, "INFO": 2}
    items.sort(key=lambda it: (severity_order[it["severity"]], it["category"] != "resolution"))
    return items


def _resolved_pedagogical_items(job_data):
    """Keep the initial diagnosis separate from issues still found in the PDF."""
    original = job_data.get("original_analysis")
    if not isinstance(original, dict):
        return []
    # A color conversion can change an image's title (RGB -> CMYK) without
    # repairing its resolution. Compare rule/page counts rather than titles.
    remaining = Counter((f.get("rule_id"), f.get("page"))
                        for f in job_data.get("findings", [])
                        if f.get("severity") in ("ERROR", "WARNING"))
    no_longer_found = []
    for finding in original.get("findings", []):
        if finding.get("severity") not in ("ERROR", "WARNING"):
            continue
        key = (finding.get("rule_id"), finding.get("page"))
        if remaining[key]:
            remaining[key] -= 1
        else:
            no_longer_found.append(finding)
    history = {"findings": no_longer_found, "job_summary": {
        "target_dpi": original.get("job_summary", {}).get("target_dpi", 300),
        "required_color_family": original.get("job_summary", {}).get("required_color_family", "CMYK"),
        "non_cmyk_images": sum(f.get("rule_id") == "SOURCE_COLOR_DIAGNOSTIC" for f in no_longer_found),
    }}
    items = _extract_pedagogical_items(history)
    for item in items:
        item["status"] = "resolved"
        item["solution"] = [
            "Presente en el análisis inicial y ausente en la última verificación del PDF corregido.",
            "Comprueba visualmente el resultado antes de autorizar la impresión."
        ]
        if item["category"] == "black":
            item["solution"].append(
                "Si el texto se ha trazado, revisa su color en las separaciones: pasar a curvas no corrige por sí solo el negro compuesto."
            )
    return items


def _wrap_lines(text, width, fontsize, fontname="helv"):
    lines = []
    for paragraph in str(text).splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if pymupdf.get_text_length(candidate, fontname=fontname, fontsize=fontsize) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            for char in word:
                if line and pymupdf.get_text_length(line + char, fontname=fontname, fontsize=fontsize) > width:
                    lines.append(line)
                    line = ""
                line += char
        lines.append(line)
    return lines


def _item_layout(item):
    lines = []
    title_lines = _wrap_lines(item["title"], CONTENT_W - 74, 8.5)
    y = 15.0
    for title in title_lines:
        lines.append((62, y, title, 8.5, "navy"))
        y += 11
    y += 3
    if item.get("detail"):
        for line in _wrap_lines(item["detail"], CONTENT_W - 20, 7):
            lines.append((10, y, line, 7, "slate"))
            y += 9.5
    prefix = "Diagnóstico inicial: " if item.get("status") == "resolved" else "Por qué afecta a la tirada: "
    for line in _wrap_lines(prefix + item["problem"], CONTENT_W - 20, 7):
        lines.append((10, y, line, 7, "slate_dark"))
        y += 9.5
    y += 3
    label = ("Resultado de la corrección y comprobación:" if item.get("status") == "resolved"
             else "Cómo corregirlo en tu programa de maquetación (InDesign / Illustrator):")
    lines.append((10, y, label, 7, "blue"))
    y += 12
    for step in item["solution"]:
        for line in _wrap_lines(f"> {step}", CONTENT_W - 36, 6.8):
            lines.append((18, y, line, 6.8, "slate_dark"))
            y += 9.5
        y += 1.5
    return max(105, y + 1), lines


def _draw_item(page, item, y, height, lines, p):
    resolved = item.get("status") == "resolved"
    tone = "green" if resolved else "red" if item["severity"] == "CRÍTICO" else "amber"
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + height),
                   fill=p[f"{tone}_bg"], color=p[f"{tone}_border"], width=0.8, radius=0.04)
    page.draw_rect(pymupdf.Rect(MARGIN_X + 8, y + 6, MARGIN_X + 56, y + 19),
                   fill=p[tone], radius=0.08)
    page.insert_text(pymupdf.Point(MARGIN_X + 12, y + 15), "REVISADO" if resolved else item["severity"],
                     fontsize=6.5, fontname="helv", color=(1, 1, 1))
    for x, offset, text, size, color in lines:
        page.insert_text(pymupdf.Point(MARGIN_X + x, y + offset), text,
                         fontsize=size, fontname="helv", color=p[color])


def _draw_section_heading(page, title, y, p):
    page.insert_text(pymupdf.Point(MARGIN_X, y + 12), title, fontsize=9.2, fontname="helv", color=p["navy"])
    page.draw_line(pymupdf.Point(MARGIN_X, y + 16), pymupdf.Point(PAGE_W - MARGIN_X, y + 16),
                   color=p["navy"], width=0.8)


def _item_parts(item, max_height):
    """Continue exceptionally long findings instead of clipping their text."""
    height, lines = _item_layout(item)
    if height <= max_height:
        return [(item, height, lines)]
    body = [line for line in lines if line[0] != 62]
    parts = []
    while body:
        part = dict(item)
        if parts:
            part["title"] += " (continuación)"
        title_lines = _wrap_lines(part["title"], CONTENT_W - 74, 8.5)
        chunk = [(62, 15 + i * 11, text, 8.5, "navy") for i, text in enumerate(title_lines)]
        start_y = chunk[-1][1] + 14
        original_y = body[0][1]
        taken = 0
        for x, offset, text, size, color in body:
            relative_y = start_y + offset - original_y
            if relative_y + 10 > max_height and taken:
                break
            chunk.append((x, relative_y, text, size, color))
            taken += 1
        parts.append((part, max(105, chunk[-1][1] + 10), chunk))
        body = body[taken:]
    return parts


def _draw_image_issue(page, entry, y, p, source):
    """Identify each painted image, including multiple placements of one XObject."""
    dpi = entry.get("effective_dpi")
    dpi_text = f"{dpi:g}" if isinstance(dpi, (int, float)) and dpi > 0 else "N/D"
    target = entry.get("target_dpi", 300)
    target_text = f"{target:g}" if isinstance(target, (int, float)) else str(target or "N/D")
    index = entry.get("index")
    page_label = entry.get("page") or "sin indicar"
    label = f"Pág. {page_label} · Imagen {index if index is not None else 'sin identificar'}"
    issue_lines = _wrap_lines(" · ".join(entry.get("issues", [])), CONTENT_W - 124, 7.2)
    height = max(78, 58 + len(issue_lines) * 9.5 + 8)
    tone = "red" if entry.get("severity") == "ERROR" else "amber"
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + height),
                   fill=p[f"{tone}_bg"], color=p[f"{tone}_border"], width=0.7, radius=0.04)
    preview = pymupdf.Rect(MARGIN_X + 8, y + 8, MARGIN_X + 96, y + height - 8)
    page.draw_rect(preview, fill=(1, 1, 1), color=p["border"], width=0.5)
    thumbnail = False
    if source is not None and entry.get("bbox"):
        try:
            source_page = source[int(entry["page"]) - 1]
            clip = (pymupdf.Rect(entry["bbox"]) * source_page.rotation_matrix) & source_page.rect
            if not clip.is_empty and not clip.is_infinite:
                scale = min(2, 176 / clip.width, 124 / clip.height)
                pixmap = source_page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
                page.insert_image(preview, stream=pixmap.tobytes("png"), keep_proportion=True)
                thumbnail = True
        except (ValueError, IndexError, TypeError, RuntimeError):
            pass
    if not thumbnail:
        page.insert_text(pymupdf.Point(preview.x0 + 5, preview.y0 + 24),
                         "Ver imagen en", fontsize=7, fontname="helv", color=p["slate"])
        page.insert_text(pymupdf.Point(preview.x0 + 5, preview.y0 + 35),
                         f"la página {page_label}", fontsize=7, fontname="helv", color=p["slate"])
    x = MARGIN_X + 108
    page.insert_text(pymupdf.Point(x, y + 16), label, fontsize=9, fontname="hebo", color=p["navy"])
    page.insert_text(pymupdf.Point(x, y + 30),
                     f"Resolución: {dpi_text} ppp   |   Mínimo del perfil: {target_text} ppp",
                     fontsize=7.5, fontname="helv", color=p["slate_dark"])
    color = entry.get("colorspace") or "sin identificar"
    dimensions = (f"{entry['width_px']} x {entry['height_px']} px"
                  if entry.get("width_px") and entry.get("height_px") else "tamaño no disponible")
    page.insert_text(pymupdf.Point(x, y + 43), f"Color: {color}   |   {dimensions}",
                     fontsize=7.2, fontname="helv", color=p["slate"])
    for line_index, line in enumerate(issue_lines):
        page.insert_text(pymupdf.Point(x, y + 58 + line_index * 9.5), line,
                         fontsize=7.2, fontname="helv", color=p[tone])
    return height


def generate_client_educational_report_pdf(job_data: Dict[str, Any], output_path: str | Path, pdf_path=None):
    """
    Genera la guía A4 completa, con incidencias actuales e historial separados.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(exist_ok=True, parents=True)

    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    assets_dir = Path(__file__).parent / "assets"
    p = _palette()

    meta = job_data.get("job_meta", {})
    summary = job_data.get("job_summary", {})
    job_id = meta.get("job_id", "N/A")
    filename = meta.get("filename", "documento.pdf")

    # 1. Cabecera corporativa
    _draw_header(page, assets_dir, p)

    # 2. Tarjeta resumen del archivo y estado general
    y_card = HEADER_H + 12.0
    card_h = 58.0
    page.draw_rect(
        pymupdf.Rect(MARGIN_X, y_card, PAGE_W - MARGIN_X, y_card + card_h),
        fill=p["light"],
        color=p["border"],
        width=0.8,
        radius=0.04,
    )

    page.insert_text(
        pymupdf.Point(MARGIN_X + 12, y_card + 18),
        f"Archivo revisado: {filename[:45]}",
        fontsize=9.5,
        fontname="helv",
        color=p["navy"],
    )

    now_str = datetime.now().strftime("%d/%m/%Y · %H:%M")
    page.insert_text(
        pymupdf.Point(MARGIN_X + 12, y_card + 34),
        f"Fecha: {now_str}   |   Páginas: {summary.get('pages', 1)}   |   Estándar: Imprenta Offset / Digital (ISO 12647-2)",
        fontsize=7.5,
        fontname="helv",
        color=p["slate"],
    )

    items = _extract_pedagogical_items(job_data)
    resolved_items = _resolved_pedagogical_items(job_data)
    has_critical = any(it["severity"] == "CRÍTICO" for it in items)
    has_issues = len(items) > 0

    # Badge de estado en la esquina derecha de la tarjeta
    badge_w = 175.0
    badge_x = PAGE_W - MARGIN_X - badge_w - 10.0
    badge_y = y_card + 10.0
    badge_h = 38.0

    if not has_issues:
        badge_bg = p["green_bg"]
        badge_border = p["green_border"]
        badge_text_col = p["green"]
        badge_title = "LISTO PARA IMPRESIÓN"
        badge_sub = "Sin incidencias pendientes en la verificación"
    elif has_critical:
        badge_bg = p["red_bg"]
        badge_border = p["red_border"]
        badge_text_col = p["red"]
        badge_title = "REQUIERE AJUSTES PREVIOS"
        badge_sub = "Puntos críticos antes de máquina"
    else:
        badge_bg = p["amber_bg"]
        badge_border = p["amber_border"]
        badge_text_col = p["amber"]
        badge_title = "RECOMENDACIONES DE MEJORA"
        badge_sub = "Avisos para optimizar la tirada"

    page.draw_rect(
        pymupdf.Rect(badge_x, badge_y, badge_x + badge_w, badge_y + badge_h),
        fill=badge_bg,
        color=badge_border,
        width=1.0,
        radius=0.08,
    )
    page.insert_text(
        pymupdf.Point(badge_x + 10, badge_y + 16),
        badge_title,
        fontsize=8.0,
        fontname="helv",
        color=badge_text_col,
    )
    page.insert_text(
        pymupdf.Point(badge_x + 10, badge_y + 30),
        badge_sub,
        fontsize=6.8,
        fontname="helv",
        color=p["slate_dark"],
    )

    # 3. Sección pedagógica: "¿Qué hemos detectado y cómo solucionarlo?"
    y_sec = y_card + card_h + 10.0
    if job_data.get("original_analysis_unavailable"):
        notice = "Historial inicial no disponible: se muestra únicamente la verificación del PDF actual."
        page.insert_text(pymupdf.Point(MARGIN_X + 4, y_sec + 10), notice,
                         fontsize=7, fontname="helv", color=p["amber"])
        y_sec += 20

    page.insert_text(
        pymupdf.Point(MARGIN_X, y_sec + 12),
        ("INCIDENCIAS PENDIENTES EN EL PDF ACTUAL" if has_issues else
         "CORREGIDOS / YA NO DETECTADOS EN EL PDF ACTUAL" if resolved_items else
         "VERIFICACIÓN DE CALIDAD EN EL DOCUMENTO"),
        fontsize=9.2,
        fontname="helv",
        color=p["navy"],
    )
    page.draw_line(
        pymupdf.Point(MARGIN_X, y_sec + 16),
        pymupdf.Point(PAGE_W - MARGIN_X, y_sec + 16),
        color=p["navy"],
        width=0.8,
    )

    y_content = y_sec + 22.0
    max_issues_y = 630.0  # Límite vertical antes del bloque de opciones

    if not has_issues and not resolved_items:
        # Estado perfecto: mostrar 4 tarjetas verdes de conformidad
        checks = [
            ("Sangrado y Geometría ISO", "El documento dispone de cajas de página y sangrado correcto (+3 mm) para un corte limpio en guillotina."),
            ("Espacio de Color CMYK", "Imágenes y gráficos vectoriales preparados para 4 tintas sin dependencias de color RGB."),
            ("Tipografías y Textos", "Todas las fuentes están debidamente incrustadas o trazadas; no habrá sustitución de tipos."),
            ("Sobreimpresión y Cobertura", "Los textos negros sobreimprimen al 100% K y la cobertura total de tinta respeta el límite de 300%.")
        ]
        box_h = 42.0
        gap = 8.0
        cur_y = y_content + 5.0
        for title, desc in checks:
            page.draw_rect(
                pymupdf.Rect(MARGIN_X, cur_y, PAGE_W - MARGIN_X, cur_y + box_h),
                fill=p["green_bg"],
                color=p["green_border"],
                width=0.7,
                radius=0.04,
            )
            page.insert_text(
                pymupdf.Point(MARGIN_X + 12, cur_y + 15),
                f"[OK]  {title}",
                fontsize=8.5,
                fontname="helv",
                color=p["green"],
            )
            page.insert_textbox(
                pymupdf.Rect(MARGIN_X + 12, cur_y + 19, PAGE_W - MARGIN_X - 12, cur_y + box_h - 2),
                desc,
                fontsize=7.4,
                fontname="helv",
                color=p["slate_dark"],
            )
            cur_y += box_h + gap

    else:
        sections = []
        if items:
            sections.append(("INCIDENCIAS PENDIENTES EN EL PDF ACTUAL", items))
        if resolved_items:
            sections.append(("CORREGIDOS / YA NO DETECTADOS EN EL PDF ACTUAL", resolved_items))
        cur_y = y_content
        for section_index, (heading, section_items) in enumerate(sections):
            cards_on_page = 0
            if section_index:
                _draw_footer(page, p, job_id)
                page = doc.new_page(width=PAGE_W, height=PAGE_H)
                _draw_header(page, assets_dir, p)
                _draw_section_heading(page, heading, HEADER_H + 12, p)
                cur_y = HEADER_H + 34
            for item in section_items:
                for part, height, lines in _item_parts(item, max_issues_y - y_content):
                    if cards_on_page >= 4 or cur_y + height > max_issues_y:
                        _draw_footer(page, p, job_id)
                        page = doc.new_page(width=PAGE_W, height=PAGE_H)
                        _draw_header(page, assets_dir, p)
                        _draw_section_heading(page, heading + " (continuación)", HEADER_H + 12, p)
                        cur_y = HEADER_H + 34
                        cards_on_page = 0
                    _draw_item(page, part, cur_y, height, lines, p)
                    cur_y += height + 8
                    cards_on_page += 1

    image_issues = collect_report_image_issues(job_data)
    if image_issues:
        source = None
        source_path = pdf_path or meta.get("last_fixed_pdf_path") or meta.get("batch_fixed_pdf_path") or meta.get("pdf_path")
        if source_path:
            try:
                source = pymupdf.open(source_path)
            except (OSError, ValueError, RuntimeError):
                pass
        try:
            _draw_footer(page, p, job_id)
            page = doc.new_page(width=PAGE_W, height=PAGE_H)
            _draw_header(page, assets_dir, p)
            _draw_section_heading(page, "IMÁGENES QUE REQUIEREN AJUSTES", HEADER_H + 12, p)
            image_y = HEADER_H + 34
            for entry in image_issues:
                line_count = len(_wrap_lines(" · ".join(entry.get("issues", [])), CONTENT_W - 124, 7.2))
                height = max(78, 58 + line_count * 9.5 + 8)
                if image_y + height > max_issues_y:
                    _draw_footer(page, p, job_id)
                    page = doc.new_page(width=PAGE_W, height=PAGE_H)
                    _draw_header(page, assets_dir, p)
                    _draw_section_heading(page, "IMÁGENES QUE REQUIEREN AJUSTES (continuación)", HEADER_H + 12, p)
                    image_y = HEADER_H + 34
                _draw_image_issue(page, entry, image_y, p, source)
                image_y += height + 8
        finally:
            if source is not None:
                source.close()

    # 4. Bloque inferior: "¿Cómo proceder? Dos opciones sencillas" (Y: 642 a 792 pt)
    y_opt = 642.0
    opt_h = 145.0
    page.draw_rect(
        pymupdf.Rect(MARGIN_X, y_opt, PAGE_W - MARGIN_X, y_opt + opt_h),
        fill=(1, 1, 1),
        color=p["border"],
        width=0.8,
        radius=0.04,
    )

    # Cabecera del bloque de opciones
    page.draw_rect(
        pymupdf.Rect(MARGIN_X, y_opt, PAGE_W - MARGIN_X, y_opt + 24),
        fill=p["indigo"],
    )
    page.insert_text(
        pymupdf.Point(MARGIN_X + 12, y_opt + 16),
        "¿CÓMO PROCEDER AHORA? ELIGE LA OPCIÓN MÁS CÓMODA PARA TI",
        fontsize=8.5,
        fontname="helv",
        color=(1, 1, 1),
    )

    # Dos columnas: Opción A y Opción B
    col_w = (CONTENT_W - 16.0) / 2.0
    col1_x = MARGIN_X + 8.0
    col2_x = col1_x + col_w + 8.0
    inner_y = y_opt + 32.0
    inner_h = opt_h - 40.0

    # Opción A: Estudio del cliente
    page.draw_rect(
        pymupdf.Rect(col1_x, inner_y, col1_x + col_w, inner_y + inner_h),
        fill=p["light"],
        color=p["border"],
        width=0.6,
        radius=0.04,
    )
    page.insert_text(
        pymupdf.Point(col1_x + 10, inner_y + 16),
        "Opción A: Corregir en tu programa de diseño",
        fontsize=8.2,
        fontname="helv",
        color=p["navy"],
    )
    optA_text = (
        "Si prefieres mantener el control absoluto de tu archivo original, abre tu documento en InDesign o Illustrator, "
        "aplica los ajustes recomendados arriba y vuelve a exportar un nuevo PDF (recomendado: estándar PDF/X-4 con sangrado).\n\n"
        "Envíanos el nuevo archivo y lo verificaremos de inmediato sin coste adicional."
    )
    page.insert_textbox(
        pymupdf.Rect(col1_x + 10, inner_y + 24, col1_x + col_w - 10, inner_y + inner_h - 6),
        optA_text,
        fontsize=7.0,
        fontname="helv",
        color=p["slate_dark"],
    )

    # Opción B: Taller IntelliPrint
    page.draw_rect(
        pymupdf.Rect(col2_x, inner_y, col2_x + col_w, inner_y + inner_h),
        fill=(0.94, 0.98, 0.96),
        color=p["green_border"],
        width=0.6,
        radius=0.04,
    )
    page.insert_text(
        pymupdf.Point(col2_x + 10, inner_y + 16),
        "Opción B: Corrección automática en taller",
        fontsize=8.2,
        fontname="helv",
        color=p["green"],
    )
    optB_text = (
        "¿Tienes urgencia o no dispones del archivo editable? Nuestro taller cuenta con el sistema profesional IntelliPrint, "
        "capaz de corregir en 1 clic: sangrado sintético por reflejo, conversión a CMYK, trazado de fuentes y sobreimpresión de negro.\n\n"
        "Indícanoslo por email o teléfono y prepararemos el documento listo para máquina."
    )
    page.insert_textbox(
        pymupdf.Rect(col2_x + 10, inner_y + 24, col2_x + col_w - 10, inner_y + inner_h - 6),
        optB_text,
        fontsize=7.0,
        fontname="helv",
        color=p["slate_dark"],
    )

    # 5. Pie de página
    _draw_footer(page, p, job_id)
    for number, report_page in enumerate(doc, 1):
        report_page.insert_text(pymupdf.Point(PAGE_W - MARGIN_X - 54, HEADER_H - 4),
                                f"Guía {number} / {len(doc)}", fontsize=6.5, fontname="helv",
                                color=(0.78, 0.85, 0.92))

    doc.save(str(output_path), deflate=True, garbage=4)
    doc.close()

