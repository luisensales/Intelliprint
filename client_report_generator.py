"""
client_report_generator.py
==========================
Generador de Informe Pedagógico para el Cliente y Diseñador (1 página A4).

Produce una guía visual, comprensible y sin tecnicismos hostiles que el
taller de imprenta puede remitir al diseñador/cliente explicando exactamente
qué incidencias se detectaron en su PDF y cómo solucionarlas en InDesign / Illustrator.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

import pymupdf

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

    page.insert_text(pymupdf.Point(text_x, 32), "Intelli", fontsize=12.5, color=(1, 1, 1), fontname="helv")
    w_intelli = pymupdf.get_text_length("Intelli", fontname="helv", fontsize=12.5)
    page.insert_text(pymupdf.Point(text_x + w_intelli, 32), "Print", fontsize=12.5, color=(0.0, 0.64, 1.0), fontname="hebo")
    w_print = pymupdf.get_text_length("Print", fontname="hebo", fontsize=12.5)
    page.insert_text(pymupdf.Point(text_x + w_intelli + w_print + 5, 32), "· GUÍA DE ARTE FINAL", fontsize=9.5, color=(0.85, 0.90, 0.95), fontname="helv")
    page.insert_text(
        pymupdf.Point(text_x, 48),
        "Informe pedagógico para el diseñador y cliente · Control de calidad para imprenta",
        fontsize=7.8,
        color=(0.75, 0.82, 0.90),
        fontname="helv",
    )

    p_sales = assets_dir / "logo-salesianos.png"
    p_mendi = assets_dir / "logo-mendizabala.png"
    p_edu = assets_dir / "logo-dept-educacion-1.png"

    if p_sales.exists() and p_mendi.exists() and p_edu.exists():
        capsule = pymupdf.Rect(325, 12, 567, 58)
        page.draw_rect(capsule, fill=(1, 1, 1), radius=0.08)
        r_sales = pymupdf.Rect(332, 16, 400, 54)
        page.insert_image(r_sales, filename=str(p_sales), keep_proportion=True)
        page.draw_line(pymupdf.Point(404, 18), pymupdf.Point(404, 52), color=(0.88, 0.88, 0.88), width=0.6)
        r_mendi = pymupdf.Rect(408, 16, 478, 54)
        page.insert_image(r_mendi, filename=str(p_mendi), keep_proportion=True)
        page.draw_line(pymupdf.Point(482, 18), pymupdf.Point(482, 52), color=(0.88, 0.88, 0.88), width=0.6)
        r_edu = pymupdf.Rect(486, 16, 560, 54)
        page.insert_image(r_edu, filename=str(p_edu), keep_proportion=True)

        # Enlaces interactivos en los logotipos de la cabecera PDF
        page.insert_link({"kind": pymupdf.LINK_URI, "from": r_sales, "uri": "https://salesianosurnieta.com/"})
        page.insert_link({"kind": pymupdf.LINK_URI, "from": r_mendi, "uri": "https://www.mendizabala.eus/"})
        page.insert_link({"kind": pymupdf.LINK_URI, "from": r_edu, "uri": "https://www.euskadi.eus/gobierno-vasco/departamento-de-educacion/"})


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
    meta = job_data.get("job_meta", {})

    items = []

    # 1. Sangrado (Bleed)
    has_bleed_err = any(f.get("rule_id") == "BLEED_GEOMETRY_3MM" for f in findings)
    bleed_mm = summary.get("bleed_detected_mm", 0.0)
    if has_bleed_err or (bleed_mm < 2.5 and not meta.get("has_mirror_bleed")):
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
    if (has_rgb_err or non_cmyk_imgs > 0) and not meta.get("has_cmyk_converted"):
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
    if has_font_err and not meta.get("has_fonts_outlined"):
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
    if has_black_err and not meta.get("has_overprint_fixed"):
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
    if has_hairline_err and not meta.get("has_hairline_fixed"):
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
    has_spots = any(f.get("rule_id") == "SPOT_COLOR_FOUND" for f in findings)
    if has_spots and not meta.get("has_spot_converted"):
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
    if has_tac_err and not meta.get("has_tac_limited"):
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

    return items


def generate_client_educational_report_pdf(job_data: Dict[str, Any], output_path: str | Path):
    """
    Genera el PDF del Informe Pedagógico para el Cliente (exactamente 1 página A4).
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
        badge_sub = "Cumple especificaciones de taller"
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

    page.insert_text(
        pymupdf.Point(MARGIN_X, y_sec + 12),
        "GUÍA DE AJUSTES EN INDESIGN / ILLUSTRATOR" if has_issues else "VERIFICACIÓN DE CALIDAD EN EL DOCUMENTO",
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

    if not has_issues:
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
        # Limitar a máximo 4 ítems prioritarios para garantizar que quepa en 1 página con aire
        display_items = items[:4]
        available_h = max_issues_y - y_content
        item_h = min(105.0, (available_h - (len(display_items) - 1) * 8.0) / len(display_items))
        gap = 8.0
        cur_y = y_content

        for it in display_items:
            is_crit = it["severity"] == "CRÍTICO"
            bg_col = p["red_bg"] if is_crit else p["amber_bg"]
            bord_col = p["red_border"] if is_crit else p["amber_border"]
            badge_col = p["red"] if is_crit else p["amber"]

            page.draw_rect(
                pymupdf.Rect(MARGIN_X, cur_y, PAGE_W - MARGIN_X, cur_y + item_h),
                fill=bg_col,
                color=bord_col,
                width=0.8,
                radius=0.04,
            )

            # Píldora de severidad
            pill_w = 48.0
            page.draw_rect(
                pymupdf.Rect(MARGIN_X + 8, cur_y + 6, MARGIN_X + 8 + pill_w, cur_y + 19),
                fill=badge_col,
                radius=0.08,
            )
            page.insert_text(
                pymupdf.Point(MARGIN_X + 12, cur_y + 15),
                it["severity"],
                fontsize=6.5,
                fontname="helv",
                color=(1, 1, 1),
            )

            # Título del problema
            page.insert_text(
                pymupdf.Point(MARGIN_X + 62, cur_y + 15),
                it["title"][:58],
                fontsize=8.5,
                fontname="helv",
                color=p["navy"],
            )

            # Explicación del porqué (¿Qué ocurre?)
            page.insert_text(
                pymupdf.Point(MARGIN_X + 10, cur_y + 30),
                f"Por qué afecta a la tirada: {it['problem'][:135]}",
                fontsize=7.0,
                fontname="helv",
                color=p["slate_dark"],
            )

            # Solución paso a paso en InDesign/Illustrator
            sol_y = cur_y + 44
            page.insert_text(
                pymupdf.Point(MARGIN_X + 10, sol_y),
                "Cómo corregirlo en tu programa de maquetación (InDesign / Illustrator):",
                fontsize=7.0,
                fontname="helv",
                color=p["blue"],
            )

            step_y = sol_y + 12
            for step in it["solution"][:2]:  # 2 pasos clave
                page.insert_text(
                    pymupdf.Point(MARGIN_X + 18, step_y),
                    f"> {step[:118]}",
                    fontsize=6.8,
                    fontname="helv",
                    color=p["slate_dark"],
                )
                step_y += 11

            cur_y += item_h + gap

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

    doc.save(str(output_path))
    doc.close()

