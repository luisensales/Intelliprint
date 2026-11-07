"""
mirror_bleed_generator.py - Generador de Sangrado Sintético por Reflejo de Píxeles (Mirror Bleed)
Extiende el sangrado perimetral a 3.0 mm reflejando los píxeles del borde hacia el exterior,
garantizando que el corte en guillotina no deje filetes blancos sin alterar los vectores del documento.
"""

import io
from pathlib import Path
from typing import Dict, Any, List, Optional
import pymupdf
from PIL import Image
import pikepdf


def generate_mirror_bleed(
    pdf_path: str,
    output_path: str,
    bleed_mm: float = 3.0,
    dpi: int = 300
) -> Dict[str, Any]:
    """
    Genera sangrado sintético por reflejo de 3.0 mm en documentos que carecen de sangre.

    - Renderiza a 300 ppp la franja perimetral interior de la página.
    - Refleja simétricamente los píxeles hacia los cuatro márgenes de sangrado (izq, der, sup, inf y esquinas).
    - Preserva el contenido vectorial original y tipografías en el centro (dentro del TrimBox) sin rasterizar.
    - Normaliza las cajas de página: TrimBox = tamaño neto, BleedBox = tamaño con sangrado (+3 mm).
    - Preserva diccionarios /OutputIntents si existen en el PDF.

    :param pdf_path: Ruta al archivo PDF de entrada.
    :param output_path: Ruta de salida para el PDF con sangrado por reflejo.
    :param bleed_mm: Milímetros de sangrado a generar (por defecto 3.0 mm).
    :param dpi: Resolución de muestreo para la franja de reflejo (por defecto 300 DPI).
    :return: Diccionario con estadísticas de la operación.
    """
    bleed_pt = bleed_mm * 72.0 / 25.4
    zoom = dpi / 72.0

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

        # Renderizar la página original a alta resolución para extraer los píxeles perimetrales
        pix = page.get_pixmap(dpi=dpi, clip=trim)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        w_px, h_px = img.size
        bleed_px = max(1, int(round(bleed_pt * zoom)))

        # Crear lienzo ampliado que incluirá el sangrado perimetral
        canvas_w = w_px + 2 * bleed_px
        canvas_h = h_px + 2 * bleed_px
        canvas = Image.new("RGB", (canvas_w, canvas_h))

        # 1. Pegar la imagen original en el centro
        canvas.paste(img, (bleed_px, bleed_px))

        # 2. Reflejar franjas perimetrales
        left_strip = img.crop((0, 0, bleed_px, h_px)).transpose(Image.FLIP_LEFT_RIGHT)
        right_strip = img.crop((w_px - bleed_px, 0, w_px, h_px)).transpose(Image.FLIP_LEFT_RIGHT)
        top_strip = img.crop((0, 0, w_px, bleed_px)).transpose(Image.FLIP_TOP_BOTTOM)
        bottom_strip = img.crop((0, h_px - bleed_px, w_px, h_px)).transpose(Image.FLIP_TOP_BOTTOM)

        canvas.paste(left_strip, (0, bleed_px))
        canvas.paste(right_strip, (w_px + bleed_px, bleed_px))
        canvas.paste(top_strip, (bleed_px, 0))
        canvas.paste(bottom_strip, (bleed_px, h_px + bleed_px))

        # 3. Reflejar las 4 esquinas diagonalmente (rotación 180°)
        canvas.paste(img.crop((0, 0, bleed_px, bleed_px)).transpose(Image.ROTATE_180), (0, 0))
        canvas.paste(img.crop((w_px - bleed_px, 0, w_px, bleed_px)).transpose(Image.ROTATE_180), (w_px + bleed_px, 0))
        canvas.paste(img.crop((0, h_px - bleed_px, bleed_px, h_px)).transpose(Image.ROTATE_180), (0, h_px + bleed_px))
        canvas.paste(img.crop((w_px - bleed_px, h_px - bleed_px, w_px, h_px)).transpose(Image.ROTATE_180), (w_px + bleed_px, h_px + bleed_px))

        tot_w_pt = w_pt + 2 * bleed_pt
        tot_h_pt = h_pt + 2 * bleed_pt

        new_page = dst_doc.new_page(width=tot_w_pt, height=tot_h_pt)
        new_page.set_mediabox(new_page.mediabox)
        new_page.set_bleedbox(new_page.mediabox)
        new_page.set_trimbox(pymupdf.Rect(bleed_pt, bleed_pt, w_pt + bleed_pt, h_pt + bleed_pt))

        # Insertar el fondo con sangre reflejada
        buf = io.BytesIO()
        canvas.save(buf, format="JPEG", quality=95, subsampling=0)
        new_page.insert_image(new_page.rect, stream=buf.getvalue())

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

