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

        # 2. Extensión / clamping perimetral del píxel exterior (1 píxel estirado hacia la sangre)
        # Esto garantiza que el sangrado use el color de fondo exacto que llega al corte a ras,
        # sin arrastrar ni reflejar elementos interiores como filetes decorativos dorados o textos.
        left_edge = img.crop((0, 0, 1, h_px)).resize((bleed_px, h_px), Image.NEAREST)
        right_edge = img.crop((w_px - 1, 0, w_px, h_px)).resize((bleed_px, h_px), Image.NEAREST)
        top_edge = img.crop((0, 0, w_px, 1)).resize((w_px, bleed_px), Image.NEAREST)
        bottom_edge = img.crop((0, h_px - 1, w_px, h_px)).resize((w_px, bleed_px), Image.NEAREST)

        canvas.paste(left_edge, (0, bleed_px))
        canvas.paste(right_edge, (w_px + bleed_px, bleed_px))
        canvas.paste(top_edge, (bleed_px, 0))
        canvas.paste(bottom_edge, (bleed_px, h_px + bleed_px))

        # 3. Cuatro esquinas (estirar el píxel exacto de cada esquina hacia el sangrado)
        c_tl = img.crop((0, 0, 1, 1)).resize((bleed_px, bleed_px), Image.NEAREST)
        c_tr = img.crop((w_px - 1, 0, w_px, 1)).resize((bleed_px, bleed_px), Image.NEAREST)
        c_bl = img.crop((0, h_px - 1, 1, h_px)).resize((bleed_px, bleed_px), Image.NEAREST)
        c_br = img.crop((w_px - 1, h_px - 1, w_px, h_px)).resize((bleed_px, bleed_px), Image.NEAREST)

        canvas.paste(c_tl, (0, 0))
        canvas.paste(c_tr, (w_px + bleed_px, 0))
        canvas.paste(c_bl, (0, h_px + bleed_px))
        canvas.paste(c_br, (w_px + bleed_px, h_px + bleed_px))

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

