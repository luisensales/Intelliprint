"""
generate_fogra_sample.py
========================
Genera una lámina técnica en PDF A4 y su renderizado en PNG de alta resolución
demostrando la Tira de Control Normalizada FOGRA / ISO 12647-2 implementada en IntelliPrint.

Instituciones:
- CPIFP Salesianos Urnieta LHIPI
- CIFP Mendizabala LHII
- Eusko Jaurlaritza - Hezkuntza Saila
"""

import os
import pymupdf
from control_strip_engine import draw_fogra_control_strip, FOGRA_SWATCHES

def create_fogra_spec_sheet(output_pdf="Muestra_Tira_FOGRA_ISO12647.pdf", output_png="static/img/muestra_tira_fogra_iso12647.png"):
    os.makedirs("static/img", exist_ok=True)
    
    # Dimensiones A4 horizontal (Landscape para visualizar la tira a lo ancho con holgura)
    # 841.89 x 595.28 pt (A4 apaisado)
    w_pt = 841.89
    h_pt = 595.28
    
    doc = pymupdf.open()
    page = doc.new_page(width=w_pt, height=h_pt)
    
    # 1. Fondo técnico y cuadrícula suave
    navy_dark = (0.05, 0.09, 0.16)
    teal_brand = (0.05, 0.58, 0.53)
    gray_bg = (0.97, 0.98, 0.99)
    gray_border = (0.85, 0.88, 0.92)
    black_ink = (0.0, 0.0, 0.0, 1.0) # CMYK
    
    # Rectángulo cabecera
    page.draw_rect(pymupdf.Rect(0, 0, w_pt, 75), fill=(0.06, 0.10, 0.18), width=0)
    page.draw_line(pymupdf.Point(0, 75), pymupdf.Point(w_pt, 75), color=teal_brand, width=2.5)
    
    # Título institucional
    page.insert_text(
        pymupdf.Point(36, 32),
        "INTELLIPRINT PREPRESS SUITE  |  HOJA TÉCNICA DE CONTROL DE CALIDAD",
        fontsize=13,
        fontname="helv",
        color=(1, 1, 1)
    )
    page.insert_text(
        pymupdf.Point(36, 52),
        "Tira de Control Normalizada FOGRA / ISO 12647-2 y Balance de Grises Espectrofotométrico",
        fontsize=10.5,
        fontname="helv",
        color=(0.3, 0.78, 0.72)
    )
    page.insert_text(
        pymupdf.Point(36, 66),
        "Centros de Referencia: CPIFP Salesianos Urnieta LHIPI  •  CIFP Mendizabala LHII  •  Eusko Jaurlaritza (Educación)",
        fontsize=8,
        fontname="helv",
        color=(0.7, 0.75, 0.82)
    )
    
    # 2. Caja 1: La Tira en Tamaño Real de Taller (Escala 1:1)
    page.draw_rect(pymupdf.Rect(36, 95, w_pt - 36, 175), fill=gray_bg, color=gray_border, width=0.8)
    page.insert_text(pymupdf.Point(50, 115), "1. TIRA NORMALIZADA EN TAMAÑO DE PRODUCCIÓN (ESCALA 1:1 - slug / cabecera de pliego)", fontsize=9.5, fontname="helv", color=(0.1, 0.15, 0.25))
    page.insert_text(pymupdf.Point(50, 128), "Diseñada en espacio nativo /DeviceCMYK sin compresión ni conversiones RGB intermedias.", fontsize=8, fontname="helv", color=(0.4, 0.45, 0.5))
    
    # Dibujar la tira en escala normal
    draw_fogra_control_strip(page, x=50, y=142, swatch_w=7.5, swatch_h=7.5, show_labels=True)
    
    # 3. Caja 2: La Tira Ampliada Didáctica para Inspección y Medición con Densitómetro/Espectrofotómetro
    page.draw_rect(pymupdf.Rect(36, 190, w_pt - 36, 315), fill=gray_bg, color=gray_border, width=0.8)
    page.insert_text(pymupdf.Point(50, 210), "2. VISTA MACRO DIDÁCTICA Y PARCHES CRÍTICOS (Ampliación para lectura en mesa de control)", fontsize=9.5, fontname="helv", color=(0.1, 0.15, 0.25))
    
    # Dibujar parches ampliados con sus valores CMYK exactos
    start_x = 50.0
    start_y = 225.0
    macro_w = 27.0
    macro_h = 24.0
    macro_gap = 5.0
    
    cur_x = start_x
    for i, sw in enumerate(FOGRA_SWATCHES):
        rect = pymupdf.Rect(cur_x, start_y, cur_x + macro_w, start_y + macro_h)
        
        # Relleno CMYK nativo
        page.draw_rect(rect, fill=sw["cmyk"], color=(0.1, 0.1, 0.1, 1.0), width=0.4)
        
        # Si es balance de grises, recuadro de seguridad
        if sw["group"] == "grey_balance":
            page.draw_rect(pymupdf.Rect(cur_x - 1.5, start_y - 1.5, cur_x + macro_w + 1.5, start_y + macro_h + 1.5), color=(0.85, 0.4, 0.0), width=1.0)
            
        # Label arriba
        page.insert_text(pymupdf.Point(cur_x + 2, start_y + macro_h + 9), sw["label"], fontsize=6.5, fontname="helv", color=(0.0, 0.0, 0.0, 1.0))
        
        # Porcentajes abajo
        c, m, y, k = sw["cmyk"]
        c_str = f"C{int(round(c*100))}" if c > 0 else ""
        m_str = f"M{int(round(m*100))}" if m > 0 else ""
        y_str = f"Y{int(round(y*100))}" if y > 0 else ""
        k_str = f"K{int(round(k*100))}" if k > 0 else ""
        parts = [p for p in [c_str, m_str, y_str, k_str] if p]
        val_str = "/".join(parts) if parts else "0%"
        page.insert_text(pymupdf.Point(cur_x + 1, start_y + macro_h + 18), val_str, fontsize=4.8, fontname="helv", color=(0.3, 0.35, 0.45))
        
        cur_x += macro_w + macro_gap
        
        # Salto de línea si excede ancho
        if (i + 1) % 11 == 0:
            cur_x = start_x
            start_y += macro_h + 28
            
    # 4. Caja 3: Guía de Medición Espectrofotométrica y Densitométrica de Taller (ISO 12647-2)
    page.draw_rect(pymupdf.Rect(36, 330, w_pt - 36, 555), fill=(1, 1, 1), color=gray_border, width=0.8)
    
    # Columnas explicativas
    col_w = (w_pt - 72 - 30) / 3
    
    # Columna 1: Balance de Grises
    c1_x = 50
    page.insert_text(pymupdf.Point(c1_x, 350), "A. BALANCE DE GRISES (ISO 12647-2)", fontsize=9, fontname="helv", color=(0.8, 0.2, 0.1))
    c1_lines = [
        "• Objetivo: Detectar desviaciones cromáticas (color cast) en máquina.",
        "• Parche Crítico Medios Tonos: CMY50 (C50% M40% Y40%) frente a REF50 (K50%).",
        "• En condiciones ideales de equilibrio químico agua-tinta, ambos parches",
        "  deben verse con idéntica neutralidad y densidad visual.",
        "• Si CMY50 vira a magenta o cian, el maquinista debe corregir el caudal",
        "  del tintero del color desviado antes de alterar el negro acromático.",
        "• Tolerancia ISO: Desviación cromática Delta Ch <= 3.5 en medios tonos."
    ]
    for idx, l in enumerate(c1_lines):
        page.insert_text(pymupdf.Point(c1_x, 368 + idx * 13), l, fontsize=7.2, fontname="helv", color=(0.15, 0.2, 0.25))
        
    # Columna 2: Sólidos y Ganancia de Punto (TVI)
    c2_x = 50 + col_w + 15
    page.insert_text(pymupdf.Point(c2_x, 350), "B. SÓLIDOS (Dmax) Y GANANCIA DE PUNTO", fontsize=9, fontname="helv", color=(0.05, 0.5, 0.45))
    c2_lines = [
        "• Sólidos 100% (C, M, Y, K): Verifican la densidad máxima óptica (Dmax).",
        "  - Valores estándar papel estucado tipo 1/2: C: 1.55, M: 1.50, Y: 1.40, K: 1.85.",
        "• Medios tonos 50% (C50, M50, Y50, K50): Miden la ganancia de punto (TVI).",
        "  - Curvas de calibración ISO 12647-2 (Curva A/B): TVI nominal = 14% a 16%.",
        "• Altas luces (3%, 5%): Controlan que el punto mínimo de trama no se queme",
        "  ni se pierda en el procesado de plancha CTP.",
        "• Sombras (95%, 98%): Aseguran que los fondos densos no empasten."
    ]
    for idx, l in enumerate(c2_lines):
        page.insert_text(pymupdf.Point(c2_x, 368 + idx * 13), l, fontsize=7.2, fontname="helv", color=(0.15, 0.2, 0.25))
        
    # Columna 3: Trapping y Mecánica de Prensa
    c3_x = 50 + (col_w + 15) * 2
    page.insert_text(pymupdf.Point(c3_x, 350), "C. TRAPPING Y DIAGNÓSTICO MECÁNICO", fontsize=9, fontname="helv", color=(0.1, 0.3, 0.7))
    c3_lines = [
        "• Sobreimpresiones (Rojo = M+Y, Verde = C+Y, Azul = C+M, 3C = C+M+Y):",
        "  - Evalúan la aceptación de tinta sobre tinta húmeda (Fórmula Preucil/Brunner).",
        "  - Trapping óptimo offset: > 75% en bicolores para evitar colores lavados.",
        "• Vernier Slur & Doubling (Arrastre y Doblado):",
        "  - Líneas verticales (0.25 pt): Detectan vibraciones y holguras axiales de engranaje.",
        "  - Líneas horizontales: Revelan patinado de papel por exceso de presión cilindro-mantilla.",
        "  - Si la trama se engruesa en una dirección, existe desajuste mecánico de prensa."
    ]
    for idx, l in enumerate(c3_lines):
        page.insert_text(pymupdf.Point(c3_x, 368 + idx * 13), l, fontsize=7.2, fontname="helv", color=(0.15, 0.2, 0.25))

    # Pie institucional
    page.draw_line(pymupdf.Point(36, 568), pymupdf.Point(w_pt - 36, 568), color=(0.8, 0.85, 0.9), width=0.5)
    page.insert_text(
        pymupdf.Point(36, 582),
        "Generado automáticamente por IntelliPrint Engine • Módulo control_strip_engine.py • Destinado a talleres y aulas de Artes Gráficas de Euskadi",
        fontsize=7,
        fontname="helv",
        color=(0.5, 0.55, 0.6)
    )
    page.insert_text(
        pymupdf.Point(w_pt - 180, 582),
        "Norma de referencia: ISO 12647-2:2013",
        fontsize=7,
        fontname="helv",
        color=(0.1, 0.4, 0.35)
    )

    doc.save(output_pdf)
    print(f"Lámina técnica guardada en {output_pdf}")
    
    # Renderizar a imagen PNG de alta resolución (200 DPI) para inspección inmediata
    pix = page.get_pixmap(dpi=200)
    pix.save(output_png)
    print(f"Render PNG guardado en {output_png}")
    doc.close()

if __name__ == "__main__":
    create_fogra_spec_sheet()
