"""
mirror_bleed_generator.py - Generador de Sangrado Sintético Profesional para Preimpresión
Genera sangrado perimetral de 3.0 mm mediante extensión inteligente de bordes:
1. Detecta automáticamente el espacio de color nativo del documento (CMYK o RGB).
2. Muestrea y genera la capa de sangrado en DeviceCMYK / DeviceRGB nativo sin conversiones destructivas.
3. Inserta la imagen con compresión sin pérdidas (Pixmap / Flate) eliminando artefactos y virajes de color.
4. Búsqueda inteligente hacia el interior (hasta 2.0 mm): si un elemento de diseño (cabecera, faldón, caja)
   se detuvo a décimas de milímetro del borde neto de corte dejando un filete blanco, detecta el color exacto
   del arte, cierra el filete blanco y extiende el sangrado 3.0 mm hacia el exterior.
5. Inset anti-aliasing (0.25 mm): evita muestrear los píxeles perimetrales de subpíxel que MuPDF o el renderizador
   mezclan con el fondo blanco de la página, extrayendo la tinta sólida pura e impidiendo filetes desvaídos.
6. Preserva la nitidez vectorial del centro mediante superposición exacta y normaliza TrimBox y BleedBox.
"""

from pathlib import Path
from typing import Dict, Any, Optional
import pymupdf
import numpy as np
import pikepdf


def get_page_print_colorspace(page: pymupdf.Page) -> pymupdf.Colorspace:
    """Detecta si la página utiliza CMYK o RGB en sus objetos vectoriales e imágenes."""
    has_rgb = False
    for d in page.get_drawings():
        for col in (d.get("fill"), d.get("stroke")):
            if col and isinstance(col, (list, tuple)):
                if len(col) == 4:
                    return pymupdf.csCMYK
                elif len(col) == 3:
                    has_rgb = True
    for img in page.get_images(full=True):
        cs_name = img[5] if len(img) > 5 else ""
        if cs_name in ("DeviceCMYK", "Separation", "DeviceN"):
            return pymupdf.csCMYK
        if cs_name == "DeviceRGB":
            has_rgb = True
    if has_rgb:
        return pymupdf.csRGB
    return pymupdf.csCMYK


def generate_mirror_bleed(
    pdf_path: str,
    output_path: str,
    bleed_mm: float = 3.0,
    dpi: int = 300
) -> Dict[str, Any]:
    """
    Genera sangrado sintético profesional de 3.0 mm en documentos que carecen de sangre.

    :param pdf_path: Ruta al archivo PDF de entrada.
    :param output_path: Ruta de salida para el PDF con sangrado por reflejo.
    :param bleed_mm: Milímetros de sangrado a generar (por defecto 3.0 mm).
    :param dpi: Resolución de muestreo para la franja de reflejo (por defecto 300 DPI).
    :return: Diccionario con estadísticas de la operación.
    """
    bleed_pt = bleed_mm * 72.0 / 25.4
    px_per_mm = dpi / 25.4
    bleed_px = max(1, int(round(bleed_mm * px_per_mm)))
    search_depth_px = max(1, int(round(2.0 * px_per_mm)))  # 2.0 mm de búsqueda interior
    edge_inset = max(2, int(round(0.25 * px_per_mm)))     # 0.25 mm inward para evitar antialiasing del borde

    src_doc = pymupdf.open(pdf_path)
    dst_doc = pymupdf.open()

    total_pages = len(src_doc)
    pages_processed = 0

    for idx, page in enumerate(src_doc):
        # TrimBox original o límites de la página
        if page.trimbox.width > 0 and page.trimbox.height > 0 and page.trimbox != page.mediabox:
            trim = page.trimbox
        else:
            trim = page.rect

        w_pt = trim.width
        h_pt = trim.height

        cs = get_page_print_colorspace(page)
        is_cmyk = (cs == pymupdf.csCMYK)
        num_channels = 4 if is_cmyk else 3

        # Renderizar la página original a alta resolución en su espacio de color nativo
        pix = page.get_pixmap(dpi=dpi, clip=trim, colorspace=cs)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, num_channels)).copy()
        H, W, _ = arr.shape

        search_d = min(search_depth_px, max(1, H // 2 - edge_inset), max(1, W // 2 - edge_inset))

        # -------------------------------------------------------------
        # 1. BORDE SUPERIOR (TOP)
        # -------------------------------------------------------------
        top_strip = arr[edge_inset:edge_inset + search_d, :, :]
        is_w_top = np.all(top_strip < 15, axis=2) if is_cmyk else np.all(top_strip > 240, axis=2)
        has_art_top = ~is_w_top
        any_art_top = np.any(has_art_top, axis=0)
        first_art_row = np.argmax(has_art_top, axis=0) + edge_inset
        top_colors = arr[edge_inset, :, :].copy()
        cols_art_top = np.where(any_art_top)[0]
        top_colors[cols_art_top] = arr[first_art_row[cols_art_top], cols_art_top, :]

        # Cerrar filetes blancos y corregir antialiasing en el borde superior
        cols_art_set = set(cols_art_top)
        for c in range(W):
            if c in cols_art_set:
                r_idx = first_art_row[c]
                arr[0:r_idx, c, :] = top_colors[c]
            else:
                arr[0:edge_inset, c, :] = top_colors[c]

        # -------------------------------------------------------------
        # 2. BORDE INFERIOR (BOTTOM)
        # -------------------------------------------------------------
        bot_anchor = H - 1 - edge_inset
        bot_strip = arr[bot_anchor - search_d:bot_anchor + 1, :, :]
        is_w_bot = np.all(bot_strip < 15, axis=2) if is_cmyk else np.all(bot_strip > 240, axis=2)
        has_art_bot = ~is_w_bot
        any_art_bot = np.any(has_art_bot, axis=0)
        has_art_bot_rev = has_art_bot[::-1, :]
        dist_from_bot = np.argmax(has_art_bot_rev, axis=0)
        bot_colors = arr[bot_anchor, :, :].copy()
        cols_art_bot = np.where(any_art_bot)[0]
        bot_row_indices = bot_anchor - dist_from_bot[cols_art_bot]
        bot_colors[cols_art_bot] = arr[bot_row_indices, cols_art_bot, :]

        # Cerrar filetes blancos y corregir antialiasing en el borde inferior
        cols_bot_map = {c: bot_row_indices[i] for i, c in enumerate(cols_art_bot)}
        for c in range(W):
            if c in cols_bot_map:
                r_idx = cols_bot_map[c]
                arr[r_idx + 1:H, c, :] = bot_colors[c]
            else:
                arr[bot_anchor + 1:H, c, :] = bot_colors[c]

        # -------------------------------------------------------------
        # 3. BORDE IZQUIERDO (LEFT)
        # -------------------------------------------------------------
        left_strip = arr[:, edge_inset:edge_inset + search_d, :]
        is_w_left = np.all(left_strip < 15, axis=2) if is_cmyk else np.all(left_strip > 240, axis=2)
        has_art_left = ~is_w_left
        any_art_left = np.any(has_art_left, axis=1)
        first_art_col = np.argmax(has_art_left, axis=1) + edge_inset
        left_colors = arr[:, edge_inset, :].copy()
        rows_art_left = np.where(any_art_left)[0]
        left_colors[rows_art_left] = arr[rows_art_left, first_art_col[rows_art_left], :]

        # Cerrar filetes blancos y corregir antialiasing en el borde izquierdo
        rows_left_set = set(rows_art_left)
        for r in range(H):
            if r in rows_left_set:
                c_idx = first_art_col[r]
                arr[r, 0:c_idx, :] = left_colors[r]
            else:
                arr[r, 0:edge_inset, :] = left_colors[r]

        # -------------------------------------------------------------
        # 4. BORDE DERECHO (RIGHT)
        # -------------------------------------------------------------
        right_anchor = W - 1 - edge_inset
        right_strip = arr[:, right_anchor - search_d:right_anchor + 1, :]
        is_w_right = np.all(right_strip < 15, axis=2) if is_cmyk else np.all(right_strip > 240, axis=2)
        has_art_right = ~is_w_right
        any_art_right = np.any(has_art_right, axis=1)
        has_art_right_rev = has_art_right[:, ::-1]
        dist_from_right = np.argmax(has_art_right_rev, axis=1)
        right_colors = arr[:, right_anchor, :].copy()
        rows_art_right = np.where(any_art_right)[0]
        right_col_indices = right_anchor - dist_from_right[rows_art_right]
        right_colors[rows_art_right] = arr[rows_art_right, right_col_indices, :]

        # Cerrar filetes blancos y corregir antialiasing en el borde derecho
        rows_right_map = {r: right_col_indices[i] for i, r in enumerate(rows_art_right)}
        for r in range(H):
            if r in rows_right_map:
                c_idx = rows_right_map[r]
                arr[r, c_idx + 1:W, :] = right_colors[r]
            else:
                arr[r, right_anchor + 1:W, :] = right_colors[r]

        # -------------------------------------------------------------
        # 5. CONSTRUCCIÓN DEL LIENZO CON SANGRADO (CANVAS)
        # -------------------------------------------------------------
        canvas_h = H + 2 * bleed_px
        canvas_w = W + 2 * bleed_px
        canvas = np.zeros((canvas_h, canvas_w, num_channels), dtype=np.uint8)

        # Centro (arte original con filetes y antialiasing perimetral corregidos)
        canvas[bleed_px:bleed_px + H, bleed_px:bleed_px + W, :] = arr

        # Sangrados perimetrales (3.0 mm)
        canvas[0:bleed_px, bleed_px:bleed_px + W, :] = top_colors[None, :, :]
        canvas[bleed_px + H:, bleed_px:bleed_px + W, :] = bot_colors[None, :, :]
        canvas[bleed_px:bleed_px + H, 0:bleed_px, :] = left_colors[:, None, :]
        canvas[bleed_px:bleed_px + H, bleed_px + W:, :] = right_colors[:, None, :]

        # Esquinas: utilizar los colores de los extremos de los sangrados adyacentes
        canvas[0:bleed_px, 0:bleed_px, :] = top_colors[0][None, None, :]
        canvas[0:bleed_px, bleed_px + W:, :] = top_colors[W - 1][None, None, :]
        canvas[bleed_px + H:, 0:bleed_px, :] = bot_colors[0][None, None, :]
        canvas[bleed_px + H:, bleed_px + W:, :] = bot_colors[W - 1][None, None, :]

        tot_w_pt = w_pt + 2 * bleed_pt
        tot_h_pt = h_pt + 2 * bleed_pt

        new_page = dst_doc.new_page(width=tot_w_pt, height=tot_h_pt)
        new_page.set_mediabox(new_page.mediabox)
        new_page.set_bleedbox(new_page.mediabox)
        new_page.set_trimbox(pymupdf.Rect(bleed_pt, bleed_pt, w_pt + bleed_pt, h_pt + bleed_pt))

        # Insertar pixmap sin pérdidas directamente en el PDF (DeviceCMYK / DeviceRGB nativo)
        pix_out = pymupdf.Pixmap(cs, canvas_w, canvas_h, canvas.tobytes(), False)
        new_page.insert_image(new_page.rect, pixmap=pix_out)

        # Superponer el contenido vectorial de la página original en el centro exacto
        new_page.show_pdf_page(
            pymupdf.Rect(bleed_pt, bleed_pt, w_pt + bleed_pt, h_pt + bleed_pt),
            src_doc,
            idx
        )

        pages_processed += 1

    temp_mirror_path = str(output_path) + ".tmp.pdf"
    dst_doc.save(temp_mirror_path)
    dst_doc.close()
    src_doc.close()

    # Preservar OutputIntents con pikepdf si existían en el original
    try:
        with pikepdf.open(pdf_path) as src, pikepdf.open(temp_mirror_path) as dst:
            if "/OutputIntents" in src.Root:
                dst.Root.OutputIntents = pikepdf.Array([dst.copy_foreign(x) for x in src.Root.OutputIntents])
            dst.save(output_path)
        Path(temp_mirror_path).unlink(missing_ok=True)
    except Exception as e:
        print(f"[mirror_bleed] Advertencia preservando metadatos: {e}")
        Path(temp_mirror_path).replace(output_path)

    return {
        "status": "success",
        "pages_processed": pages_processed,
        "total_pages": total_pages,
        "bleed_mm": bleed_mm
    }
