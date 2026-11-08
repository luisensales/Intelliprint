"""
didactic_engine.py
==================
Motor Didáctico y Simulador de Taller Gráfico para Formación Profesional (FP).
Desarrollado para CPIFP Salesianos Urnieta LHIPI y CIFP Mendizabala LHII
en el marco del proyecto de innovación aplicada de Artes Gráficas (Gobierno Vasco).

Proporciona:
1. Catálogo y generador dinámico de "Retos de Taller FP" (Casos reales con errores controlados).
2. Simulador visual interactivo de consecuencias físicas en taller:
   - Descalce de Registro CMYK en texto fino (Rich Black).
   - Efecto Repintado / Maculado en pila por exceso de TAC (> 300%).
   - Desvío de Guillotina y Filete Blanco por falta de sangre (Bleed 0 mm).
   - Pérdida de Líneas Finas en insolación CTP (< 0.25 pt).
   - Fallo de Escaneo de Códigos de Barras en cuatricromía.
3. Motor de Autoevaluación / Quiz Técnico con Rúbrica FP e ISO 12647-2 / PDF/X.
4. Generador de Hoja de Práctica y Evaluación del Alumno en PDF A4.
"""

from __future__ import annotations

import io
import math
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pymupdf
from PIL import Image, ImageDraw, ImageFont, ImageFilter

PAGE_W = 595.3
PAGE_H = 841.9
MARGIN_X = 35.0
CONTENT_W = PAGE_W - 2 * MARGIN_X
HEADER_H = 70.0
FOOTER_Y = 808.0

# ---------------------------------------------------------------------------
# CATÁLOGO DE RETOS DE TALLER FP
# ---------------------------------------------------------------------------

SCENARIOS_CATALOG = [
    {
        "id": "reto_tarjeta_richblack",
        "title": "Reto 1: Tarjeta Corporativa con Rich Black y Sin Sangrado",
        "level": "Iniciación FP (Grado Medio / 1º GS)",
        "module": "Tratamiento de Imagen y Preimpresión Digital",
        "doc_type": "Tarjeta de Visita (85 x 55 mm)",
        "description": "El cliente aporta una tarjeta de visita corporativa con los textos de 6 pt compuestos en 4 tintas (Rich Black 300%) y el fondo colocado al corte exacto (0 mm de sangre).",
        "target_errors": [
            "Texto de 6 pt en 4 tintas (CMYK) con grave riesgo de descalce de registro en máquina.",
            "Falta total de sangre perimetral (0 mm de sangrado exterior).",
            "Resolución deficiente en isotipo gráfico (72 DPI)."
        ],
        "learning_goals": [
            "Comprender la diferencia entre 100% K puro y Negro Enriquecido en tipografía menuda.",
            "Aplicar los 3 mm de sangrado exterior exigidos por la norma de producción.",
            "Verificar la resolución nativa mínima de 300 DPI."
        ],
        "iso_norm": "ISO 12647-2 / ISO 15930 (PDF/X-1a)"
    },
    {
        "id": "reto_folleto_tac_hairlines",
        "title": "Reto 2: Folleto Promocional con TAC 360% y Líneas Pelo (CTP)",
        "level": "Intermedio (Taller de Impresión Offset / Digital)",
        "module": "Impresión Offset y Control de Producción",
        "doc_type": "Folleto A5 (148 x 210 mm)",
        "description": "Folleto publicitario con un fondo fotográfico nocturno cuya cobertura total de tinta (TAC) alcanza el 365% y filetes dorados decorativos de 0.06 pt.",
        "target_errors": [
            "Exceso extremo de cobertura de tinta (TAC 365% vs límite de 300%-320%).",
            "Líneas ultrafinas (0.06 pt) no reproducibles en plancha CTP térmica.",
            "Riesgo crítico de repintado y maculado en la pila de salida de máquina."
        ],
        "learning_goals": [
            "Comprender los límites de absorción del papel estucado según ISO 12647-2.",
            "Controlar la curva de transferencia en CTP y umbral mínimo de trazo (0.25 pt).",
            "Aplicar conversión con perfil DeviceLink o reducción de TAC sin alterar el contraste."
        ],
        "iso_norm": "ISO 12647-2: Cobertura máxima de tinta ≤ 300% (Offset hojas)"
    },
    {
        "id": "reto_packaging_barcode_cmyk",
        "title": "Reto 3: Estuche Packaging con Código de Barras en 4 Tintas",
        "level": "Avanzado (Packaging y Troquelado)",
        "module": "Troquelado, Packaging y Trazabilidad",
        "doc_type": "Estuche Cosmético (120 x 180 mm)",
        "description": "Estuche desplegado con código de barras EAN-13 impreso en 4 tintas sin reserva blanca, y textos de ingredientes a 1.2 mm del trazo de hendido/troquel.",
        "target_errors": [
            "Código de barras EAN-13 tramado en cuatricromía (provoca rechazo en escáneres ópticos).",
            "Falta de zona de silencio lateral (Quiet Zone) en el código de barras.",
            "Invasión de la zona de seguridad y línea de troquelado (menos de 3 mm)."
        ],
        "learning_goals": [
            "Conocer las especificaciones GS1 para códigos de barras comerciales (100% K y quiet zone).",
            "Dominar las tolerancias de troquelado y hendido en cartoncillo.",
            "Evitar devoluciones comerciales por código ilegible en lineales de venta."
        ],
        "iso_norm": "ISO/IEC 15420 (GS1 EAN-13) & ISO 12647-2"
    },
    {
        "id": "reto_revista_seguridad_lomo",
        "title": "Reto 4: Portada de Revista con Textos en el Medianil/Lomo",
        "level": "Avanzado (Imposición y Encuadernación)",
        "module": "Gestión de la Producción Gráfica y Acabados",
        "doc_type": "Revista A4 (210 x 297 mm, 16 págs)",
        "description": "Publicación editorial grapada en la que los folios explicativos y pies de foto tocan el pliegue del lomo (medianil) y la imagen de portada está en RGB sRGB.",
        "target_errors": [
            "Textos e información crítica ubicados dentro de la zona de hendido del lomo (8 mm).",
            "Imágenes no separadas a CMYK (perfil de cámara sRGB).",
            "Falta de consideración del desplazamiento o trepa en cuadernillos grapados."
        ],
        "learning_goals": [
            "Calcular la reserva de medianil y lomo según el tipo de encuadernación (grapa vs rústica).",
            "Separación cromática según el soporte (FOGRA39 / FOGRA51).",
            "Comprender el efecto físico de la guillotina trilateral en publicaciones plegadas."
        ],
        "iso_norm": "ISO 12647-2 / Especificaciones ECI para Edición Gráfica"
    }
]

# ---------------------------------------------------------------------------
# GENERADOR DINÁMICO DE ARCHIVOS SINTÉTICOS DE RETO (PDF REALES)
# ---------------------------------------------------------------------------

def generate_scenario_pdf(scenario_id: str, output_path: Path) -> Path:
    """
    Genera un PDF sintético con los errores intencionados del reto seleccionado
    para que el alumno pueda inspeccionarlo directamente con el motor de preflight.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()

    if scenario_id == "reto_tarjeta_richblack":
        # Tarjeta 85 x 55 mm = 240.94 x 155.91 pt
        w, h = 240.94, 155.91
        page = doc.new_page(width=w, height=h)
        # TrimBox y MediaBox exactos (sin BleedBox = 0 mm sangre)
        page.set_trimbox(pymupdf.Rect(0, 0, w, h))
        page.set_mediabox(pymupdf.Rect(0, 0, w, h))

        # Fondo oscuro al corte exacto (Rich black C=60, M=50, Y=40, K=100)
        # En PyMuPDF representamos el Rich Black con color RGB equivalente oscuro
        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.04, 0.03, 0.03))

        # Cuadro decorativo claro
        page.draw_rect(pymupdf.Rect(10, 10, w - 10, h - 10), color=(0.85, 0.70, 0.20), width=0.8)

        # Texto corporativo
        page.insert_text(pymupdf.Point(20, 40), "SERVICIOS GRÁFICOS NORTE", fontsize=11, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(20, 56), "Consultoría Gráfica & Packaging", fontsize=7.5, fontname="helv", color=(0.85, 0.70, 0.20))

        # Texto muy fino en 4 tintas (Simulado en RGB oscuro para detonar Rich Black)
        page.insert_text(pymupdf.Point(20, 85), "Director Técnico: Martin Otegui", fontsize=6.0, fontname="helv", color=(0.05, 0.05, 0.06))
        page.insert_text(pymupdf.Point(20, 97), "Tel: +34 943 00 11 22 · info@graficasnorte.eus", fontsize=5.5, fontname="helv", color=(0.05, 0.05, 0.06))
        page.insert_text(pymupdf.Point(20, 108), "Parque Tecnológico Miramon, Donostia", fontsize=5.5, fontname="helv", color=(0.05, 0.05, 0.06))

        # Insignia baja resolución simulada
        img = Image.new("RGB", (40, 40), color=(220, 180, 50))
        d = ImageDraw.Draw(img)
        d.rectangle([5, 5, 35, 35], outline=(30, 30, 30), width=2)
        d.text((12, 12), "GN", fill=(20, 20, 20))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        page.insert_image(pymupdf.Rect(w - 60, 30, w - 20, 70), stream=buf.getvalue())

    elif scenario_id == "reto_folleto_tac_hairlines":
        # Folleto A5: 148 x 210 mm = 419.5 x 595.3 pt
        w, h = 419.5, 595.3
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(pymupdf.Rect(0, 0, w, h))

        # Fondo con gran densidad de tinta (simula TAC 360%)
        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.02, 0.01, 0.01))

        # Líneas pelo (hairlines < 0.25 pt)
        page.draw_line(pymupdf.Point(30, 80), pymupdf.Point(w - 30, 80), color=(0.95, 0.85, 0.40), width=0.06)
        page.draw_line(pymupdf.Point(30, 84), pymupdf.Point(w - 30, 84), color=(0.95, 0.85, 0.40), width=0.08)
        page.draw_line(pymupdf.Point(30, 520), pymupdf.Point(w - 30, 520), color=(0.95, 0.85, 0.40), width=0.05)

        page.insert_text(pymupdf.Point(40, 120), "CONCIERTO SINFÓNICO NOCTURNO", fontsize=18, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(40, 145), "Gran Gala de Apertura · Temporada 2026/2027", fontsize=11, fontname="helv", color=(0.9, 0.8, 0.4))
        page.insert_text(pymupdf.Point(40, 180), "Auditorio Kursaal · Donostia-San Sebastián", fontsize=10, fontname="helv", color=(0.8, 0.8, 0.8))

        # Recuadro informativo con texto
        page.draw_rect(pymupdf.Rect(35, 220, w - 35, 480), fill=(0.08, 0.06, 0.07), color=(0.9, 0.8, 0.4), width=0.1)
        page.insert_text(pymupdf.Point(50, 260), "Programa de Obras:", fontsize=12, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(50, 290), "1. Obertura Festiva - D. Shostakovich", fontsize=9, fontname="helv", color=(0.85, 0.85, 0.85))
        page.insert_text(pymupdf.Point(50, 315), "2. Sinfonía Nº 9 en Mi menor - A. Dvorak", fontsize=9, fontname="helv", color=(0.85, 0.85, 0.85))
        page.insert_text(pymupdf.Point(50, 340), "3. Danzas Polovtsianas - A. Borodin", fontsize=9, fontname="helv", color=(0.85, 0.85, 0.85))

    elif scenario_id == "reto_packaging_barcode_cmyk":
        # Estuche Packaging: 120 x 180 mm = 340.16 x 510.24 pt
        w, h = 340.16, 510.24
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(pymupdf.Rect(0, 0, w, h))

        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.95, 0.94, 0.92))

        # Título producto
        page.insert_text(pymupdf.Point(30, 60), "CREMA DERMO-REPARADORA BIO", fontsize=14, fontname="helv", color=(0.2, 0.4, 0.3))
        page.insert_text(pymupdf.Point(30, 80), "Con Extracto Puro de Caléndula y Karité", fontsize=8.5, fontname="helv", color=(0.4, 0.5, 0.4))

        # Texto legal que invade zona de seguridad (a 1.2 mm = 3.4 pt del borde)
        page.insert_text(pymupdf.Point(3.4, 150), "Lote: 2026-X9 / Caducidad: 12/2028 / Fabricado en la UE para Laboratorios DermoLab S.L.", fontsize=5.0, fontname="helv", color=(0.1, 0.1, 0.1))

        # Simular código de barras EAN-13 en 4 tintas (color RGB no puro sin quiet zone)
        # Dibuja barras con colores compuestos
        bx, by = 60.0, 360.0
        bw, bh = 140.0, 60.0
        # Fondo sin reserva (directo sobre fondo gris)
        page.insert_text(pymupdf.Point(bx, by - 10), "Código de Barras Comercial (EAN-13):", fontsize=7.5, fontname="helv", color=(0.2, 0.2, 0.2))

        # Dibuja barras tramadas
        random.seed(42)
        cur_x = bx
        while cur_x < bx + bw:
            bar_w = random.choice([1.2, 2.4, 3.6])
            # Color marrón oscuro/morado (simulando 4 tintas)
            page.draw_rect(pymupdf.Rect(cur_x, by, cur_x + bar_w, by + bh), fill=(0.15, 0.10, 0.08))
            cur_x += bar_w + random.choice([1.2, 2.4])

        page.insert_text(pymupdf.Point(bx + 15, by + bh + 12), "8 412345 678905", fontsize=9, fontname="helv", color=(0.15, 0.10, 0.08))

    else: # reto_revista_seguridad_lomo u otro
        w, h = 595.3, 841.9 # A4
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(pymupdf.Rect(0, 0, w, h))

        # Cabecera
        page.draw_rect(pymupdf.Rect(0, 0, w, 120), fill=(0.10, 0.25, 0.45))
        page.insert_text(pymupdf.Point(40, 70), "REVISTA TÉCNICA DE FP INDUSTRIAL", fontsize=20, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(40, 95), "Edición Euskadi 2026 · Nuevas Tecnologías en Artes Gráficas", fontsize=10, fontname="helv", color=(0.8, 0.9, 1))

        # Texto que invade el medianil (a 3 mm del lomo izquierdo)
        page.insert_text(pymupdf.Point(8.5, 200), "NOTA EDITORIAL AL BORDE DEL PLIEGUE (PELIGRO DE PÉRDIDA EN ENCUADERNACIÓN)", fontsize=6.5, fontname="helv", color=(0.8, 0.1, 0.1))

        # Columnas de texto
        page.insert_text(pymupdf.Point(40, 240), "La digitalización de los procesos de preimpresión...", fontsize=10, fontname="helv", color=(0.2, 0.2, 0.2))

    doc.save(str(output_path))
    doc.close()
    return output_path

# ---------------------------------------------------------------------------
# SIMULADOR VISUAL DE CONSECUENCIAS FÍSICAS EN TALLER
# ---------------------------------------------------------------------------

def simulate_register_misalignment(shift_px: int = 4) -> io.BytesIO:
    """
    Simula visualmente el descalce de registro en planchas CMYK.
    Cuando un texto tipográfico fino (6-8 pt) o un logotipo se diseña en 4 tintas
    (Rich Black) en vez de 100% K puro, cualquier vibración o dilatación del papel
    en la máquina offset provoca halos visibles de cian, magenta y amarillo.
    """
    w, h = 560, 200
    base = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(base)

    # Dibuja fondo cuadriculado suave de referencia
    for x in range(0, w, 20):
        draw.line([(x, 0), (x, h)], fill=(245, 245, 248))
    for y in range(0, h, 20):
        draw.line([(0, y), (w, y)], fill=(245, 245, 248))

    # Creamos capas separadas para C, M, Y, K
    def render_text_layer(color, offset):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # Línea de prueba fina
        d.line([(40 + offset[0], 50 + offset[1]), (520 + offset[0], 50 + offset[1])], fill=color, width=2)
        # Texto de muestra de simulación
        try:
            # Usar default font o básico
            font_title = ImageFont.load_default()
        except Exception:
            font_title = None

        d.text((40 + offset[0], 70 + offset[1]), "TEXTO EN 4 TINTAS (RICH BLACK) - VIBRACIÓN DE REGISTRO OFFSET", fill=color)
        d.text((40 + offset[0], 100 + offset[1]), "C=75%  M=68%  Y=67%  K=90%  --> Descalce de planchas CTP en tirada", fill=color)
        d.text((40 + offset[0], 130 + offset[1]), "Resultado en papel: Texto borroso con halo multicolor no apto para lectura", fill=color)
        return img

    s = max(1, min(shift_px, 12))
    # Capa Cyan (desfasada a la izquierda)
    layer_c = render_text_layer((0, 160, 230, 210), (-s, 0))
    # Capa Magenta (desfasada hacia arriba-derecha)
    layer_m = render_text_layer((230, 0, 125, 210), (s, -int(s * 0.7)))
    # Capa Yellow (desfasada hacia abajo)
    layer_y = render_text_layer((255, 220, 0, 190), (0, s))
    # Capa Black (eje central)
    layer_k = render_text_layer((30, 30, 30, 240), (0, 0))

    # Fusionar capas
    base.alpha_composite(layer_c)
    base.alpha_composite(layer_m)
    base.alpha_composite(layer_y)
    base.alpha_composite(layer_k)

    # Anotación explicativa en la imagen
    draw_final = ImageDraw.Draw(base)
    draw_final.rectangle([(0, h - 28), (w, h)], fill=(20, 25, 35))
    draw_final.text((15, h - 20), f"SIMULACIÓN DIDÁCTICA FP: Desfase de planchas a +{s * 0.05:.2f} mm | Solución: Usar 100% K Puro", fill=(255, 220, 100))

    buf = io.BytesIO()
    base.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf


def simulate_setoff_stain(tac_percent: int = 360) -> io.BytesIO:
    """
    Simula visualmente el efecto físico de "Repintado / Maculado en Pila" (Set-off).
    Si la cobertura total de tinta (TAC) excede el 300%-320%, el papel estucado no puede
    absorber el vehículo oleoso ni fijar los pigmentos a tiempo. En la pila de salida,
    la presión de las hojas superiores transfiere tinta fresca al dorso de la siguiente hoja.
    """
    w, h = 560, 220
    base = Image.new("RGB", (w, h), (250, 248, 245))
    draw = ImageDraw.Draw(base)

    # Lado Izquierdo: Hoja impresa original (anverso)
    draw.rectangle([(20, 20), (260, 180)], fill=(15, 12, 10), outline=(180, 180, 180), width=1)
    draw.text((35, 35), "ANVERSO (CARA)", fill=(240, 240, 240))
    draw.text((35, 60), f"Masa de color oscuro con TAC={tac_percent}%", fill=(200, 200, 200))
    draw.text((35, 80), "(Capa de tinta excesivamente gruesa)", fill=(180, 180, 180))

    # Lado Derecho: Reverso de la siguiente hoja en la pila (manchada por repintado)
    draw.rectangle([(300, 20), (540, 180)], fill=(255, 255, 255), outline=(180, 180, 180), width=1)
    draw.text((315, 35), "REVERSO (DORSO)", fill=(40, 40, 40))
    draw.text((315, 60), "Página posterior en blanco afectada", fill=(100, 100, 100))

    # Mancha de repintado en el dorso (proporcional al exceso de TAC)
    excess = max(0, tac_percent - 300)
    alpha = min(220, int(excess * 3.5))

    stain_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(stain_layer)

    if excess > 0:
        # Dibujar manchas irregulares simulando contacto de presión en pila
        for i in range(12):
            cx = random.randint(340, 500)
            cy = random.randint(80, 160)
            r = random.randint(15, 45)
            sdraw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(30, 25, 20, int(alpha * 0.7)))

    # Aplicar desenfoque para dar aspecto oleoso de transferencia de tinta
    stain_layer = stain_layer.filter(ImageFilter.GaussianBlur(radius=6))

    base_rgba = base.convert("RGBA")
    base_rgba.alpha_composite(stain_layer)

    final_img = base_rgba.convert("RGB")
    fdraw = ImageDraw.Draw(final_img)

    # Pie explicativo
    fdraw.rectangle([(0, h - 28), (w, h)], fill=(140, 30, 30) if excess > 0 else (20, 120, 50))
    msg = f"EFECTO EN TALLER: Repintado Severo en Pila (TAC={tac_percent}% > 300%) | Rechazo de Tirada" if excess > 0 else f"TAC CORRECTO: {tac_percent}% dentro de norma ISO 12647-2 (Secado óptimo)"
    fdraw.text((15, h - 20), msg, fill=(255, 255, 255))

    buf = io.BytesIO()
    final_img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def simulate_guillotine_shift(has_bleed: bool = False, cut_error_mm: float = 1.5) -> io.BytesIO:
    """
    Simula visualmente el desvío de la guillotina de corte.
    Si un archivo tiene fondo al corte pero NO dispone de 3 mm de sangrado (Bleed),
    cualquier variación física en el pisón o la cuchilla de la guillotina dejará
    un antiestético "filete blanco" en el contorno del impreso final.
    """
    w, h = 560, 220
    base = Image.new("RGB", (w, h), (240, 242, 245))
    draw = ImageDraw.Draw(base)

    # Área nominal del trabajo
    trim_x1, trim_y1 = 120, 40
    trim_x2, trim_y2 = 440, 160

    # Si tiene sangre, el fondo se extiende 30px (equiv 3mm)
    bleed_px = 25 if has_bleed else 0
    bg_x1, bg_y1 = trim_x1 - bleed_px, trim_y1 - bleed_px
    bg_x2, bg_y2 = trim_x2 + bleed_px, trim_y2 + bleed_px

    # Dibujar fondo impreso (azul intenso)
    draw.rectangle([(bg_x1, bg_y1), (bg_x2, bg_y2)], fill=(20, 60, 140))
    draw.text((bg_x1 + 15, bg_y1 + 15), "FONDO IMPRESO", fill=(180, 200, 255))

    # Línea nominal de TrimBox (Corte teórico)
    draw.rectangle([(trim_x1, trim_y1), (trim_x2, trim_y2)], outline=(0, 255, 120), width=2)
    draw.text((trim_x1 + 10, trim_y1 + 35), "Línea Teórica de Corte (TrimBox)", fill=(0, 255, 120))

    # Cuchilla de guillotina desfasada (error de corte)
    shift_px = int(cut_error_mm * 12)
    blade_x1 = trim_x1 + shift_px
    blade_y1 = trim_y1
    blade_x2 = trim_x2 + shift_px
    blade_y2 = trim_y2

    # Línea de la cuchilla real
    draw.rectangle([(blade_x1, blade_y1), (blade_x2, blade_y2)], outline=(255, 50, 50), width=2)

    # Si no tiene sangre, entre el borde del fondo (bg_x1) y la cuchilla (blade_x1) aparece papel blanco
    if not has_bleed and shift_px > 0:
        # Filete blanco visible
        draw.rectangle([(bg_x1, blade_y1), (blade_x1, blade_y2)], fill=(255, 255, 255), outline=(255, 0, 0), width=1)
        draw.text((blade_x1 - 100, blade_y1 + 55), "FILETE BLANCO!", fill=(220, 20, 20))

    # Pie informativo
    draw.rectangle([(0, h - 28), (w, h)], fill=(160, 30, 30) if not has_bleed else (20, 120, 50))
    status_text = f"SIN SANGRE: Filete blanco visible de {cut_error_mm} mm | Solución: Añadir +3 mm de sangrado" if not has_bleed else f"CON SANGRE (+3 mm): Corte limpio y perfecto incluso con oscilación de cuchilla de {cut_error_mm} mm"
    draw.text((15, h - 20), status_text, fill=(255, 255, 255))

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf


def simulate_ctp_hairline(stroke_pt: float = 0.08) -> io.BytesIO:
    """
    Simula visualmente la pérdida o debilitamiento de líneas finas (Hairlines)
    en el láser del insolador térmico CTP (Computer to Plate) a 2400 DPI.
    Las líneas < 0.25 pt no reciben suficiente energía de exposición o se lavan
    en la procesadora química, desapareciendo en la plancha de aluminio.
    """
    w, h = 560, 200
    base = Image.new("RGB", (w, h), (245, 246, 248))
    draw = ImageDraw.Draw(base)

    # Panel izquierdo: Diseño en pantalla (Vectorial)
    draw.rectangle([(20, 20), (260, 160)], fill=(255, 255, 255), outline=(200, 200, 200), width=1)
    draw.text((30, 30), "EN PANTALLA (InDesign / Illustrator)", fill=(40, 40, 40))
    draw.text((30, 50), f"Línea vectorial de {stroke_pt} pt", fill=(100, 100, 100))
    # En pantalla se ve una línea delgada nítida
    draw.line([(40, 90), (240, 90)], fill=(0, 0, 0), width=1)
    draw.line([(40, 110), (240, 110)], fill=(0, 0, 0), width=1)
    draw.text((30, 130), "En monitor siempre parece visible", fill=(120, 120, 120))

    # Panel derecho: Plancha CTP / Papel impreso
    draw.rectangle([(300, 20), (540, 160)], fill=(230, 235, 240), outline=(200, 200, 200), width=1)
    draw.text((310, 30), "EN PLANCHA CTP / PAPEL IMPRESO", fill=(40, 40, 40))

    if stroke_pt < 0.25:
        draw.text((310, 50), f"Láser CTP 2400 DPI (Pérdida de emulsión)", fill=(180, 40, 40))
        # Línea quebrada o ausente
        # Dibuja puntos dispersos simulando rotura
        for x in range(320, 520, 8):
            if random.random() > 0.65:
                draw.point((x, 90), fill=(100, 100, 100))
                draw.point((x + 1, 90), fill=(140, 140, 140))
        draw.text((310, 130), "¡TRAZO ROTO O INEXISTENTE EN TIRADA!", fill=(180, 20, 20))
    else:
        draw.text((310, 50), f"Láser CTP 2400 DPI (Fijación correcta)", fill=(20, 120, 50))
        draw.line([(320, 90), (520, 90)], fill=(20, 20, 20), width=2)
        draw.text((310, 130), "Trazo sólido y continuo asegurado", fill=(20, 120, 50))

    # Pie informativo
    draw.rectangle([(0, h - 28), (w, h)], fill=(160, 30, 30) if stroke_pt < 0.25 else (20, 120, 50))
    msg = f"PELIGRO CTP: Grosor {stroke_pt} pt < 0.25 pt mínimo de norma | Solución automática: Corregir a 0.30 pt" if stroke_pt < 0.25 else f"TRAZO CORRECTO: {stroke_pt} pt ≥ 0.25 pt (Fijación garantizada en plancha)"
    draw.text((15, h - 20), msg, fill=(255, 255, 255))

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ---------------------------------------------------------------------------
# MOTOR DE AUTOEVALUACIÓN / QUIZ TÉCNICO FP
# ---------------------------------------------------------------------------

QUESTIONS_FP = [
    {
        "id": "q_rich_black",
        "question": "¿Por qué motivo NO se debe utilizar Negro Enriquecido (Rich Black / 4 tintas) en tipografías menudas (≤ 8 pt)?",
        "options": [
            "Porque consume más memoria RAM al rasterizar en el RIP.",
            "Porque cualquier desfase microscópico de registro entre planchas provocará halos de color y texto borroso e ilegible.",
            "Porque la tinta negra no se mezcla bien químicamente con el amarillo.",
            "Porque la norma ISO prohíbe imprimir textos de menos de 10 pt."
        ],
        "correct_index": 1,
        "explanation": "En máquina offset o digital de hojas, un texto fino en 4 tintas requiere que las 4 planchas coincidan con precisión de micrómetros. Una variación mínima genera desenfoque y halos cromáticos. Los textos menudos deben ir siempre en 100% K puro con sobreimpresión.",
        "iso_ref": "ISO 12647-2 / Buenas Prácticas Ghent Workgroup"
    },
    {
        "id": "q_bleed_margin",
        "question": "¿Cuál es la función principal del Sangrado exterior de 3 mm en un documento gráfico destinado a corte?",
        "options": [
            "Dejar espacio suficiente para colocar la firma del diseñador gráfico.",
            "Asegurar que los colores y fotos de fondo se extiendan más allá de la línea de corte para evitar filetes blancos si la guillotina oscila.",
            "Permitir que la encuadernadora aplique la cola caliente en el lomo.",
            "Servir como margen para que el maquinista apoye las pinzas de arrastre."
        ],
        "correct_index": 1,
        "explanation": "La guillotina de taller corta cientos o miles de hojas apiladas con una tolerancia mecánica habitual de ±0.5 a 1 mm. Si los fondos terminan en la línea exacta de corte (TrimBox), cualquier desviación deja visible el blanco del papel.",
        "iso_ref": "ISO 12647-2 / Especificaciones ECI"
    },
    {
        "id": "q_tac_limit",
        "question": "¿Qué consecuencia física grave provoca en taller superar el límite de Cobertura Total de Tinta (TAC > 300%-320%)?",
        "options": [
            "La plancha CTP se quema debido al exceso de calor del láser térmico.",
            "El papel estucado no puede absorber tanta tinta, provocando repintado (maculado) en la pila de salida y bloqueando el secado.",
            "Las letras en tipografía palo seco cambian automáticamente a tipografía con serifa.",
            "El archivo PDF aumenta 10 veces su tamaño en disco."
        ],
        "correct_index": 1,
        "explanation": "El exceso de tinta satura la superficie del papel, impidiendo el anclaje y secado por oxidación/absorción. Al caer las hojas en la pila de salida, la cara entintada mancha el dorso de la hoja superior (repintado), inutilizando la tirada completa.",
        "iso_ref": "ISO 12647-2 (Límite TAC 300% para estucado FOGRA39/51)"
    },
    {
        "id": "q_hairline_ctp",
        "question": "¿Por qué las líneas de espesor inferior a 0.25 pt (Hairlines) son un problema crítico en preimpresión?",
        "options": [
            "Porque la tinta offset se expande tanto que se convierten en líneas de 5 mm de ancho.",
            "Porque el láser del CTP no llega a polimerizar la capa fotosensible de la plancha, perdiéndose el trazo durante el tiraje.",
            "Porque consumen demasiada tinta en los rodillos dadores de la batería.",
            "Porque están reservadas exclusivamente a los billetes de curso legal."
        ],
        "correct_index": 1,
        "explanation": "A resoluciones de insolación estándar (2400 DPI), un trazo de 0.05 pt equivale a menos de un píxel de láser. Durante el revelado y tirada, la fricción del agua de mojado y la mantilla de caucho arranca la emulsión débil, rompiendo la línea.",
        "iso_ref": "Especificaciones Técnicas CTP & Ghent Output Suite"
    },
    {
        "id": "q_barcode_k",
        "question": "¿Por qué los códigos de barras comerciales (EAN-13, QR) deben imprimirse en 100% K y no en cuatricromía?",
        "options": [
            "Porque los lectores ópticos e industriales usan láseres rojos que exigen máximo contraste fotométrico y nitidez sin sangrado de registro.",
            "Porque el consorcio GS1 cobra un canon extra si se imprime en colores.",
            "Porque los supermercados no disponen de pantallas a color en caja.",
            "Porque las 4 tintas pesan demasiado en el embalaje del producto."
        ],
        "correct_index": 0,
        "explanation": "El lector láser comercial emite luz roja y detecta la absorción del negro. Si el código está compuesto en 4 tintas, cualquier descalce de registro o ganancia de punto borronea las barras y los huecos (zona muda / quiet zone), provocando fallos de lectura en caja.",
        "iso_ref": "ISO/IEC 15420 / Estándar Internacional GS1"
    }
]

def evaluate_student_quiz(answers: Dict[str, int]) -> Dict[str, Any]:
    """
    Evalúa las respuestas del alumno, calcula la calificación de 0 a 10,
    y genera el diagnóstico pedagógico con referencias a normas de Artes Gráficas.
    """
    total = len(QUESTIONS_FP)
    correct_count = 0
    feedback_items = []

    for q in QUESTIONS_FP:
        qid = q["id"]
        chosen = answers.get(qid, -1)
        is_ok = (chosen == q["correct_index"])
        if is_ok:
            correct_count += 1

        feedback_items.append({
            "question_id": qid,
            "question": q["question"],
            "chosen_index": chosen,
            "correct_index": q["correct_index"],
            "is_correct": is_ok,
            "explanation": q["explanation"],
            "iso_ref": q["iso_ref"]
        })

    score = round((correct_count / total) * 10, 1)

    if score >= 9.0:
        level = "Sobresaliente (Competencia Técnica Avanzada en Preimpresión)"
    elif score >= 7.0:
        level = "Notable (Sólido Criterio de Taller y Control de Calidad)"
    elif score >= 5.0:
        level = "Aprobado (Conocimientos Básicos de Taller Adquiridos)"
    else:
        level = "Insuficiente (Requiere Repaso de Incidencias Físicas y Normas ISO)"

    return {
        "score": score,
        "total_questions": total,
        "correct_answers": correct_count,
        "level": level,
        "evaluated_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "feedback": feedback_items
    }

# ---------------------------------------------------------------------------
# GENERADOR DE HOJA DE PRÁCTICA Y EVALUACIÓN DEL ALUMNO (PDF A4)
# ---------------------------------------------------------------------------

def generate_student_worksheet_pdf(
    student_name: str,
    school_name: str,
    scenario_info: Dict[str, Any],
    quiz_results: Optional[Dict[str, Any]],
    output_pdf_path: Path,
    assets_dir: Path
) -> Path:
    """
    Genera la Hoja de Práctica Oficial de Taller en PDF A4 con sellos de
    Salesianos Urnieta, CIFP Mendizabala LHII y Gobierno Vasco (Hezkuntza Saila).
    """
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    # 1. Cabecera Corporativa Institucional
    navy = (31 / 255, 38 / 255, 44 / 255)
    page.draw_rect(pymupdf.Rect(0, 0, PAGE_W, HEADER_H), fill=navy)

    imago_path = assets_dir / "Logo-intelliprint-imago.jpg"
    if imago_path.exists():
        page.insert_image(pymupdf.Rect(26, 12, 74, 58), filename=str(imago_path), keep_proportion=True)
        text_x = 84
    else:
        text_x = 35

    page.insert_text(
        pymupdf.Point(text_x, 32),
        "INTELLIPRINT · FICHA DE PRÁCTICA Y EVALUACIÓN FP",
        fontsize=11.0,
        color=(1, 1, 1),
        fontname="helv",
    )
    page.insert_text(
        pymupdf.Point(text_x, 48),
        "Simulador Didáctico de Preimpresión y Consecuencias en Taller Gráfico",
        fontsize=7.8,
        color=(0.75, 0.82, 0.90),
        fontname="helv",
    )

    # Sellos institucionales de los centros
    p_sales = assets_dir / "logo-salesianos.png"
    p_mendi = assets_dir / "logo-mendizabala.png"
    p_edu = assets_dir / "logo-dept-educacion-1.png"

    if p_sales.exists() and p_mendi.exists() and p_edu.exists():
        capsule = pymupdf.Rect(325, 12, 567, 58)
        page.draw_rect(capsule, fill=(1, 1, 1), radius=0.08)
        page.insert_image(pymupdf.Rect(332, 16, 400, 54), filename=str(p_sales), keep_proportion=True)
        page.draw_line(pymupdf.Point(404, 18), pymupdf.Point(404, 52), color=(0.88, 0.88, 0.88), width=0.6)
        page.insert_image(pymupdf.Rect(408, 16, 478, 54), filename=str(p_mendi), keep_proportion=True)
        page.draw_line(pymupdf.Point(482, 18), pymupdf.Point(482, 52), color=(0.88, 0.88, 0.88), width=0.6)
        page.insert_image(pymupdf.Rect(486, 16, 560, 54), filename=str(p_edu), keep_proportion=True)

    # 2. Bloque de Datos del Alumno y Práctica
    y = 86.0
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + 54), fill=(0.96, 0.97, 0.99), color=(0.82, 0.86, 0.90), width=0.6)

    alumno = student_name if student_name.strip() else "Alumno/a de Artes Gráficas"
    centro = school_name if school_name.strip() else "CPIFP Salesianos Urnieta / CIFP Mendizabala LHII"

    page.insert_text(pymupdf.Point(MARGIN_X + 12, y + 18), f"Estudiante: {alumno}", fontsize=9.0, fontname="helv", color=(0.15, 0.20, 0.25))
    page.insert_text(pymupdf.Point(MARGIN_X + 12, y + 33), f"Centro Educativo: {centro}", fontsize=8.2, fontname="helv", color=(0.35, 0.40, 0.48))
    page.insert_text(pymupdf.Point(MARGIN_X + 12, y + 46), f"Módulo / Nivel: {scenario_info.get('module', 'Preimpresión Digital')} · {scenario_info.get('level', 'FP')}", fontsize=8.0, fontname="helv", color=(0.35, 0.40, 0.48))

    score_val = quiz_results.get("score", 0.0) if quiz_results else None
    if score_val is not None:
        score_box = pymupdf.Rect(PAGE_W - MARGIN_X - 110, y + 8, PAGE_W - MARGIN_X - 12, y + 46)
        color_score = (0.10, 0.60, 0.35) if score_val >= 5.0 else (0.85, 0.20, 0.20)
        page.draw_rect(score_box, fill=(1, 1, 1), color=color_score, width=1.0)
        page.insert_text(pymupdf.Point(score_box.x0 + 10, score_box.y0 + 18), f"CALIFICACIÓN FP", fontsize=7.0, fontname="helv", color=color_score)
        page.insert_text(pymupdf.Point(score_box.x0 + 18, score_box.y0 + 34), f"{score_val:.1f} / 10", fontsize=13.0, fontname="helv", color=color_score)

    # 3. Reto de Taller Analizado
    y += 66.0
    page.insert_text(pymupdf.Point(MARGIN_X, y), "1. CASO PRÁCTICO ASIGNADO", fontsize=10.0, fontname="helv", color=navy)
    page.draw_line(pymupdf.Point(MARGIN_X, y + 3), pymupdf.Point(PAGE_W - MARGIN_X, y + 3), color=(0.28, 0.25, 0.75), width=1.2)

    y += 16.0
    page.insert_text(pymupdf.Point(MARGIN_X, y), f"Título del Reto: {scenario_info.get('title', 'Caso de Taller')}", fontsize=9.0, fontname="helv", color=(0.15, 0.2, 0.3))
    page.insert_text(pymupdf.Point(MARGIN_X, y + 13), f"Tipo de Trabajo: {scenario_info.get('doc_type', 'Documento Comercial')} · Norma de Referencia: {scenario_info.get('iso_norm', 'ISO 12647-2')}", fontsize=8.0, fontname="helv", color=(0.4, 0.45, 0.5))

    y += 26.0
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + 38), fill=(0.98, 0.98, 0.99), color=(0.88, 0.90, 0.92), width=0.5)
    page.insert_text(pymupdf.Point(MARGIN_X + 10, y + 14), "Descripción del trabajo entregado por el cliente:", fontsize=7.5, fontname="helv", color=(0.3, 0.35, 0.4))
    desc = scenario_info.get("description", "")
    page.insert_textbox(pymupdf.Rect(MARGIN_X + 10, y + 16, PAGE_W - MARGIN_X - 10, y + 36), desc, fontsize=7.8, fontname="helv", color=(0.15, 0.2, 0.25))

    # 4. Errores Críticos que el Alumno Debe Diagnosticar
    y += 50.0
    page.insert_text(pymupdf.Point(MARGIN_X, y), "2. DIAGNÓSTICO TÉCNICO Y CONSECUENCIAS FÍSICAS EN MÁQUINA", fontsize=10.0, fontname="helv", color=navy)
    page.draw_line(pymupdf.Point(MARGIN_X, y + 3), pymupdf.Point(PAGE_W - MARGIN_X, y + 3), color=(0.28, 0.25, 0.75), width=1.2)

    y += 14.0
    errors = scenario_info.get("target_errors", [])
    for idx, err in enumerate(errors, 1):
        page.draw_circle(pymupdf.Point(MARGIN_X + 6, y + 5), 2.5, fill=(0.85, 0.20, 0.20))
        page.insert_text(pymupdf.Point(MARGIN_X + 16, y + 8), f"Incidencia {idx}: {err}", fontsize=8.2, fontname="helv", color=(0.2, 0.2, 0.2))
        y += 16.0

    # 5. Aprendizajes Clave y Procedimiento de Corrección
    y += 8.0
    page.insert_text(pymupdf.Point(MARGIN_X, y), "3. PROCEDIMIENTO DE CORRECCIÓN EN PREIMPRESIÓN (InDesign / Acrobat / IntelliPrint)", fontsize=10.0, fontname="helv", color=navy)
    page.draw_line(pymupdf.Point(MARGIN_X, y + 3), pymupdf.Point(PAGE_W - MARGIN_X, y + 3), color=(0.28, 0.25, 0.75), width=1.2)

    y += 14.0
    goals = scenario_info.get("learning_goals", [])
    for idx, goal in enumerate(goals, 1):
        page.draw_circle(pymupdf.Point(MARGIN_X + 6, y + 5), 2.5, fill=(0.10, 0.60, 0.35))
        page.insert_text(pymupdf.Point(MARGIN_X + 16, y + 8), f"Paso {idx}: {goal}", fontsize=8.2, fontname="helv", color=(0.2, 0.2, 0.2))
        y += 16.0

    # 6. Rúbrica y Resultados del Cuestionario
    if quiz_results:
        y += 10.0
        page.insert_text(pymupdf.Point(MARGIN_X, y), "4. RESULTADOS DE LA EVALUACIÓN TEÓRICO-PRÁCTICA", fontsize=10.0, fontname="helv", color=navy)
        page.draw_line(pymupdf.Point(MARGIN_X, y + 3), pymupdf.Point(PAGE_W - MARGIN_X, y + 3), color=(0.28, 0.25, 0.75), width=1.2)

        y += 16.0
        page.insert_text(
            pymupdf.Point(MARGIN_X, y),
            f"Nivel alcanzado: {quiz_results.get('level', '')} ({quiz_results.get('correct_answers', 0)} / {quiz_results.get('total_questions', 0)} respuestas acertadas)",
            fontsize=8.5,
            fontname="helv",
            color=(0.15, 0.2, 0.3)
        )
        y += 14.0

        for fb in quiz_results.get("feedback", [])[:4]: # Mostrar hasta 4 ítems
            icon_color = (0.10, 0.60, 0.35) if fb["is_correct"] else (0.85, 0.20, 0.20)
            mark = "[ACIERTO]" if fb["is_correct"] else "[REVISAR]"
            page.insert_text(pymupdf.Point(MARGIN_X + 8, y), f"{mark} {fb['question'][:75]}...", fontsize=7.2, fontname="helv", color=icon_color)
            y += 10.0
            page.insert_text(pymupdf.Point(MARGIN_X + 24, y), f"Fundamento técnico: {fb['explanation'][:100]}...", fontsize=6.8, fontname="helv", color=(0.4, 0.45, 0.5))
            y += 13.0

    # 7. Firma Docente y Validación
    y = 740.0
    box_firma_w = (CONTENT_W - 30) / 2
    # Caja Profesor
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, MARGIN_X + box_firma_w, y + 55), color=(0.82, 0.86, 0.90), width=0.6)
    page.insert_text(pymupdf.Point(MARGIN_X + 10, y + 15), "Vº Bº PROFESOR / EVALUADOR:", fontsize=7.2, fontname="helv", color=(0.3, 0.35, 0.4))
    page.insert_text(pymupdf.Point(MARGIN_X + 10, y + 46), "Firma y Sello del Departamento", fontsize=6.8, fontname="helv", color=(0.6, 0.65, 0.7))

    # Caja Alumno
    page.draw_rect(pymupdf.Rect(MARGIN_X + box_firma_w + 30, y, PAGE_W - MARGIN_X, y + 55), color=(0.82, 0.86, 0.90), width=0.6)
    page.insert_text(pymupdf.Point(MARGIN_X + box_firma_w + 40, y + 15), "CONFORMIDAD DEL ALUMNO/A:", fontsize=7.2, fontname="helv", color=(0.3, 0.35, 0.4))
    page.insert_text(pymupdf.Point(MARGIN_X + box_firma_w + 40, y + 46), "Fecha y Firma del Estudiante", fontsize=6.8, fontname="helv", color=(0.6, 0.65, 0.7))

    # Pie institucional
    page.draw_line(pymupdf.Point(MARGIN_X, FOOTER_Y), pymupdf.Point(PAGE_W - MARGIN_X, FOOTER_Y), color=(0.82, 0.86, 0.90), width=0.5)
    page.insert_text(
        pymupdf.Point(MARGIN_X, FOOTER_Y + 12),
        "IntelliPrint Didactic Engine · CPIFP Salesianos Urnieta LHIPI / CIFP Mendizabala LHII · Hezkuntza Saila (Gobierno Vasco)",
        fontsize=7.0,
        fontname="helv",
        color=(0.35, 0.40, 0.48),
    )

    doc.save(str(output_pdf_path))
    doc.close()
    return output_pdf_path
