"""
font_vectorizer.py - Vectorizador / Trazador de Tipografías a Curvas (Outlines)
Convierte textos y fuentes no incrustadas en trazados vectoriales puros (<path>),
garantizando la integridad del documento en cualquier RIP o CTP de imprenta.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import pymupdf
import pikepdf


def outline_fonts_in_pdf(
    pdf_path: str,
    output_path: str,
    target_pages: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Traza las tipografías de un documento PDF a curvas vectoriales directas.

    - Convierte los glifos de texto en vectores matemáticos exactos (sin rasterizar a mapa de bits).
    - Preserva intactas las cajas de página (MediaBox, CropBox, TrimBox, BleedBox).
    - Si el PDF original contenía OutputIntent ICC formal (PDF/X), lo preserva íntegro en el nuevo catálogo.
    - Elimina cualquier riesgo de fuentes no incrustadas, sustitución tipográfica o fuentes protegidas.

    :param pdf_path: Ruta al PDF original.
    :param output_path: Ruta al PDF de salida trazado.
    :param target_pages: Lista opcional de páginas (1-based) a trazar. Si es None, traza todas las páginas con fuentes.
    :return: Diccionario con estadísticas del proceso.
    """
    if target_pages is not None and len(target_pages) == 0:
        import shutil
        shutil.copy2(pdf_path, output_path)
        return {
            "success": True,
            "status": "success",
            "total_pages": 0,
            "pages_vectorized": 0
        }

    doc_orig = pymupdf.open(pdf_path)
    doc_dest = pymupdf.open()

    total_pages = len(doc_orig)
    pages_vectorized = 0

    for idx in range(total_pages):
        p_num = idx + 1
        p_orig = doc_orig[idx]
        fonts_on_page = p_orig.get_fonts()

        # Determinar si requiere vectorización
        should_vectorize = False
        if target_pages is not None:
            should_vectorize = (p_num in target_pages)
        else:
            # Traza si la página contiene fuentes
            should_vectorize = (len(fonts_on_page) > 0)

        if should_vectorize and len(fonts_on_page) > 0:
            # Convertir la página a SVG con texto convertido a curvas (<path>)
            svg_data = p_orig.get_svg_image(text_as_path=True)
            svg_doc = pymupdf.open(stream=svg_data.encode("utf-8"), filetype="svg")
            page_pdf_bytes = svg_doc.convert_to_pdf()
            svg_doc.close()

            # Insertar la página trazada
            page_doc = pymupdf.open("pdf", page_pdf_bytes)
            doc_dest.insert_pdf(page_doc)
            page_doc.close()

            p_dest = doc_dest[-1]
            # Preservar exactamente las cajas geométricas de forma segura
            try:
                p_dest.set_mediabox(p_orig.mediabox)
            except Exception:
                pass

            try:
                # CropBox debe estar estrictamente dentro de MediaBox
                safe_crop = p_orig.cropbox & p_orig.mediabox
                if safe_crop.is_valid and not safe_crop.is_empty:
                    p_dest.set_cropbox(safe_crop)
                else:
                    p_dest.set_cropbox(p_orig.mediabox)
            except Exception:
                try:
                    p_dest.set_cropbox(p_dest.mediabox)
                except Exception:
                    pass

            try:
                p_dest.set_trimbox(p_orig.trimbox)
            except Exception:
                pass

            try:
                p_dest.set_bleedbox(p_orig.bleedbox)
            except Exception:
                pass

            pages_vectorized += 1
        else:
            # Si no tiene fuentes, copiar la página original directamente
            doc_dest.insert_pdf(doc_orig, from_page=idx, to_page=idx)

    # Guardar documento trazado intermedio
    temp_vector_path = str(output_path) + ".tmp.pdf"
    doc_dest.save(temp_vector_path)
    doc_dest.close()
    doc_orig.close()

    # Preservar exactamente las cajas geométricas y OutputIntents con pikepdf
    try:
        with pikepdf.open(pdf_path) as src, pikepdf.open(temp_vector_path, allow_overwriting_input=True) as dst:
            if "/OutputIntents" in src.Root:
                dst.Root.OutputIntents = pikepdf.Array([dst.copy_foreign(x) for x in src.Root.OutputIntents])
            for i, dst_page in enumerate(dst.pages):
                if i < len(src.pages):
                    src_page = src.pages[i]
                    for box_name in ["/MediaBox", "/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"]:
                        if box_name in src_page:
                            try:
                                dst_page[box_name] = dst.copy_foreign(src_page[box_name])
                            except Exception:
                                pass
            dst.save(output_path)
        Path(temp_vector_path).unlink(missing_ok=True)
    except Exception as e:
        print(f"[font_vectorizer] Advertencia preservando metadatos pikepdf: {e}")
        Path(temp_vector_path).replace(output_path)

    return {
        "success": True,
        "status": "success",
        "total_pages": total_pages,
        "pages_vectorized": pages_vectorized
    }

