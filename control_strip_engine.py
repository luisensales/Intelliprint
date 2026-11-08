"""
control_strip_engine.py
=======================
Generador de Tira de Control Normalizada FOGRA / ISO 12647-2 y Balance de Grises.
Desarrollado para CPIFP Salesianos Urnieta LHIPI y CIFP Mendizabala LHII.

Incluye:
1. Parches de Sólidos Primarios CMYK al 100% (Dmax).
2. Sobreimpresiones de Trampas de Tinta (Trapping: Rojo, Verde, Azul, 3-Color).
3. Escalas Tonales CMYK: Medios tonos (75%, 50%, 25%), Altas luces (3%, 5%) y Sombras (95%, 98%).
4. Parches de Balance de Grises ISO 12647-2:
   - Medio tono: Parche CMY (C50% M40% Y40%) frente a K50%.
   - Altas luces: Parche CMY (C25% M19% Y19%) frente a K25%.
   - Sombras: Parche CMY (C75% M64% Y64%) frente a K75%.
5. Micro-miras y vernier de control de arrastre y doblado (Slur and Doubling).
"""

from __future__ import annotations

from typing import List, Tuple, Dict, Any, Optional
import pymupdf

# Definición de parches normalizados ISO 12647-2 (Valores CMYK 0.0 a 1.0)
FOGRA_SWATCHES: List[Dict[str, Any]] = [
    # --- PRIMARIOS 100% ---
    {"label": "C", "cmyk": (1.0, 0.0, 0.0, 0.0), "group": "solids"},
    {"label": "M", "cmyk": (0.0, 1.0, 0.0, 0.0), "group": "solids"},
    {"label": "Y", "cmyk": (0.0, 0.0, 1.0, 0.0), "group": "solids"},
    {"label": "K", "cmyk": (0.0, 0.0, 0.0, 1.0), "group": "solids"},

    # --- SOBREIMPRESIONES / TRAPPING (2 y 3 Tintas) ---
    {"label": "R", "cmyk": (0.0, 1.0, 1.0, 0.0), "group": "trapping"},       # M + Y
    {"label": "G", "cmyk": (1.0, 0.0, 1.0, 0.0), "group": "trapping"},       # C + Y
    {"label": "B", "cmyk": (1.0, 1.0, 0.0, 0.0), "group": "trapping"},       # C + M
    {"label": "3C", "cmyk": (1.0, 1.0, 1.0, 0.0), "group": "trapping"},      # C + M + Y

    # --- MEDIOS TONOS 50% ---
    {"label": "C50", "cmyk": (0.50, 0.0, 0.0, 0.0), "group": "halftones"},
    {"label": "M50", "cmyk": (0.0, 0.50, 0.0, 0.0), "group": "halftones"},
    {"label": "Y50", "cmyk": (0.0, 0.0, 0.50, 0.0), "group": "halftones"},
    {"label": "K50", "cmyk": (0.0, 0.0, 0.0, 0.50), "group": "halftones"},

    # --- BALANCE DE GRISES ISO 12647-2 (PARCHE CRÍTICO DE CALIBRACIÓN) ---
    # En una máquina calibrada, CMY 50/40/40 es visualmente neutro e idéntico a K50
    {"label": "CMY50", "cmyk": (0.50, 0.40, 0.40, 0.0), "group": "grey_balance"},
    {"label": "REF50", "cmyk": (0.0, 0.0, 0.0, 0.50), "group": "grey_balance"},

    # --- BALANCE DE GRISES ALTAS LUCES (25%) ---
    {"label": "CMY25", "cmyk": (0.25, 0.19, 0.19, 0.0), "group": "grey_balance"},
    {"label": "REF25", "cmyk": (0.0, 0.0, 0.0, 0.25), "group": "grey_balance"},

    # --- BALANCE DE GRISES SOMBRAS (75%) ---
    {"label": "CMY75", "cmyk": (0.75, 0.64, 0.64, 0.0), "group": "grey_balance"},
    {"label": "REF75", "cmyk": (0.0, 0.0, 0.0, 0.75), "group": "grey_balance"},

    # --- CONTROL DE RESOLUCIÓN CTP (ALTAS LUCES 3% Y SOMBRAS 95%) ---
    {"label": "K3%", "cmyk": (0.0, 0.0, 0.0, 0.03), "group": "ctp_resolution"},
    {"label": "K5%", "cmyk": (0.0, 0.0, 0.0, 0.05), "group": "ctp_resolution"},
    {"label": "K95%", "cmyk": (0.0, 0.0, 0.0, 0.95), "group": "ctp_resolution"},
    {"label": "K98%", "cmyk": (0.0, 0.0, 0.0, 0.98), "group": "ctp_resolution"},
]


def draw_fogra_control_strip(
    page: pymupdf.Page,
    x: float,
    y: float,
    swatch_w: float = 6.0,
    swatch_h: float = 6.0,
    show_labels: bool = True
) -> float:
    """
    Dibuja la tira de control FOGRA / ISO 12647-2 completa sobre una página PDF.
    
    Parámetros:
      page: Objeto pymupdf.Page donde se estampará la tira.
      x: Coordenada X inicial (origen izquierdo).
      y: Coordenada Y inicial (origen superior).
      swatch_w: Anchura de cada parche en puntos (aprox. 5.5 a 7 pt).
      swatch_h: Altura de cada parche en puntos.
      show_labels: Si es True, dibuja leyendas identificativas debajo de cada parche.

    Retorna:
      La anchura total consumida por la tira (en puntos).
    """
    black_stroke = (0.0, 0.0, 0.0, 1.0)
    gap = 1.0
    cur_x = x

    # 1. Rótulo identificativo de inicio
    page.insert_text(
        pymupdf.Point(cur_x, y + swatch_h * 0.8),
        "FOGRA Media Wedge ISO 12647-2",
        fontsize=4.0,
        fontname="helv",
        color=(0.0, 0.0, 0.0, 1.0)
    )
    cur_x += 70.0

    # 2. Dibujar parches normalizados
    for sw in FOGRA_SWATCHES:
        sw_rect = pymupdf.Rect(cur_x, y, cur_x + swatch_w, y + swatch_h)

        # Rellenar con color CMYK nativo en espacio DeviceCMYK
        page.draw_rect(
            sw_rect,
            fill=sw["cmyk"],
            color=black_stroke,
            width=0.20
        )

        # Destacar visualmente los pares de balance de grises con un recuadro doble
        if sw["group"] == "grey_balance":
            page.draw_rect(
                pymupdf.Rect(cur_x - 0.5, y - 0.5, cur_x + swatch_w + 0.5, y + swatch_h + 0.5),
                color=black_stroke,
                width=0.30
            )

        # Rótulo de parche
        if show_labels:
            lbl = sw["label"]
            font_sz = 3.0 if len(lbl) <= 3 else 2.4
            page.insert_text(
                pymupdf.Point(cur_x, y + swatch_h + 4.5),
                lbl,
                fontsize=font_sz,
                fontname="helv",
                color=(0.0, 0.0, 0.0, 1.0)
            )

        cur_x += swatch_w + gap

    # 3. Vernier / Mira de Slur and Doubling (Arrastre y Doblado de Mantilla)
    cur_x += 4.0
    vernier_w = 12.0
    v_box = pymupdf.Rect(cur_x, y, cur_x + vernier_w, y + swatch_h)
    page.draw_rect(v_box, color=black_stroke, width=0.25)

    # Filetes verticales finos (0.2 pt) para detectar vibración horizontal
    for vx in [cur_x + 2.5, cur_x + 5.0, cur_x + 7.5, cur_x + 10.0]:
        page.draw_line(pymupdf.Point(vx, y), pymupdf.Point(vx, y + swatch_h), color=black_stroke, width=0.25)

    cur_x += vernier_w + 2.0
    h_box = pymupdf.Rect(cur_x, y, cur_x + vernier_w, y + swatch_h)
    page.draw_rect(h_box, color=black_stroke, width=0.25)

    # Filetes horizontales finos para detectar patinado en cilindro impresor
    for vy in [y + 1.5, y + 3.0, y + 4.5]:
        page.draw_line(pymupdf.Point(cur_x, vy), pymupdf.Point(cur_x + vernier_w, vy), color=black_stroke, width=0.25)

    cur_x += vernier_w + 4.0

    return cur_x - x

