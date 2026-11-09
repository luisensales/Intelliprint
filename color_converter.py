"""
color_converter.py – Conversión gestionada RGB→CMYK de imágenes embebidas en PDF.

Utiliza:
  - PyMuPDF  para extraer imágenes por xref
  - PIL / ImageCms  para aplicar transformaciones ICC
  - pikepdf  para sustituir los streams de imagen en el PDF original
"""

from __future__ import annotations

import io
import tempfile
import traceback
from pathlib import Path
from typing import Optional

import pikepdf
import pymupdf
from PIL import Image, ImageCms


ICC_DIR = Path(__file__).parent / "icc_profiles"
DEFAULT_SRC_ICC = ICC_DIR / "sRGB2014.icc"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_transform(src_icc: Path, dst_icc: Path) -> ImageCms.ImageCmsTransform:
    """Construye un transform ICC RGB→CMYK con intención RELATIVE_COLORIMETRIC."""
    return ImageCms.buildTransform(
        str(src_icc),
        str(dst_icc),
        "RGB",
        "CMYK",
        renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
    )


def _image_to_cmyk_bytes(raw_bytes: bytes, transform: ImageCms.ImageCmsTransform) -> tuple[bytes, int, int]:
    """Aplica el transform ICC y devuelve la imagen CMYK como JPEG bytes y sus dimensiones (w, h)."""
    with Image.open(io.BytesIO(raw_bytes)) as img:
        w, h = img.size

        # Asegurar modo RGB antes de transformar
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            alpha = img.getchannel("A") if "A" in img.getbands() else None
            if alpha:
                bg.paste(img, mask=alpha)
                del alpha
            else:
                bg.paste(img)
            img_rgb = bg
        elif img.mode != "RGB":
            img_rgb = img.convert("RGB")
        else:
            img_rgb = img

        img_cmyk = ImageCms.applyTransform(img_rgb, transform)  # → modo CMYK

        buf = io.BytesIO()
        img_cmyk.save(buf, format="JPEG", quality=92, subsampling=0)
        cmyk_bytes = buf.getvalue()

        if img_rgb is not img:
            img_rgb.close()
        img_cmyk.close()
        del img_cmyk

    return cmyk_bytes, w, h


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def convert_rgb_images_to_cmyk(
    pdf_path: str | Path,
    dst_icc_path: str | Path,
    src_icc_path: Optional[str | Path] = None,
    output_path: Optional[str | Path] = None,
) -> dict:
    """
    Convierte todas las imágenes RGB de un PDF a CMYK usando perfiles ICC.

    Parámetros
    ----------
    pdf_path     : Ruta al PDF de entrada.
    dst_icc_path : Perfil ICC de destino (CMYK).
    src_icc_path : Perfil ICC de origen (RGB). Si es None usa sRGB2014.
    output_path  : Ruta donde guardar el PDF convertido.

    Devuelve
    --------
    dict con claves:
        success          (bool)
        output_path      (str)
        images_converted (int)
        images_skipped   (int)
        errors           (list[str])
    """
    pdf_path = Path(pdf_path)
    dst_icc_path = Path(dst_icc_path)
    src_icc_path = Path(src_icc_path) if src_icc_path else DEFAULT_SRC_ICC

    if output_path is None:
        output_path = pdf_path.parent / (pdf_path.stem + "_cmyk_converted.pdf")
    output_path = Path(output_path)

    result = {
        "success": False,
        "output_path": str(output_path),
        "images_converted": 0,
        "images_skipped": 0,
        "errors": [],
    }

    for label, p in [("PDF de entrada", pdf_path), ("Perfil destino", dst_icc_path), ("Perfil origen", src_icc_path)]:
        if not p.exists():
            result["errors"].append(f"{label} no encontrado: {p}")
            return result

    try:
        transform = _build_transform(src_icc_path, dst_icc_path)
    except Exception as e:
        result["errors"].append(f"Error construyendo transform ICC: {e}")
        return result

    # Recopilar todos los xrefs de imágenes RGB del documento
    mupdf_doc = pymupdf.open(str(pdf_path))
    rgb_xrefs: set[int] = set()

    for page_index in range(len(mupdf_doc)):
        page = mupdf_doc[page_index]
        for img_tuple in page.get_images(full=True):
            xref = img_tuple[0]
            img_info = mupdf_doc.extract_image(xref)
            cs = img_info.get("colorspace", 0)
            if cs == 3:   # RGB
                rgb_xrefs.add(xref)
            else:
                result["images_skipped"] += 1

    mupdf_doc.close()

    if not rgb_xrefs:
        import shutil
        shutil.copy2(str(pdf_path), str(output_path))
        result["success"] = not result["errors"]
        return result

    # Abrir con pikepdf para reemplazar los streams
    try:
        pike_doc = pikepdf.open(str(pdf_path), allow_overwriting_input=True)
    except Exception as e:
        result["errors"].append(f"No se pudo abrir el PDF con pikepdf: {e}")
        return result

    for xref in rgb_xrefs:
        try:
            tmp_doc = pymupdf.open(str(pdf_path))
            img_info = tmp_doc.extract_image(xref)
            tmp_doc.close()
            del tmp_doc

            raw_bytes = img_info.get("image")
            if not raw_bytes:
                result["images_skipped"] += 1
                continue

            cmyk_bytes, w, h = _image_to_cmyk_bytes(raw_bytes, transform)
            del raw_bytes, img_info

            obj = pike_doc.get_object(xref, 0)
            obj.write(cmyk_bytes, filter=pikepdf.Name("/DCTDecode"))
            del cmyk_bytes
            obj["/Width"] = w
            obj["/Height"] = h
            obj["/ColorSpace"] = pikepdf.Name("/DeviceCMYK")
            obj["/BitsPerComponent"] = 8
            obj["/Decode"] = pikepdf.Array([1, 0, 1, 0, 1, 0, 1, 0])

            # Limpiar parametros tecnicos antiguos incompatibles con el nuevo stream DCTDecode
            # NOTA: Se conservan expresamente /SMask y /Mask para preservar las mascaras de transparencia (canales alfa)
            for key in ["/DecodeParms", "/Intent", "/Alternates"]:
                try:
                    del obj[key]
                except KeyError:
                    pass

            result["images_converted"] += 1
            import gc
            gc.collect()

        except Exception as e:
            err_msg = f"xref {xref}: {e}"
            result["errors"].append(err_msg)
            traceback.print_exc()
            result["images_skipped"] += 1

    try:
        pike_doc.save(str(output_path))
        pike_doc.close()
        result["success"] = not result["errors"]
    except Exception as e:
        result["errors"].append(f"Error guardando PDF convertido: {e}")
        try:
            pike_doc.close()
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Extrae el perfil ICC embebido del OutputIntent del PDF
# ---------------------------------------------------------------------------

def extract_embedded_icc_to_tempfile(pdf_path: str | Path) -> Optional[str]:
    """
    Si el PDF tiene un OutputIntent con DestOutputProfile, lo extrae a un
    archivo temporal y devuelve la ruta. Devuelve None si no hay perfil.
    """
    try:
        pike_doc = pikepdf.open(str(pdf_path))
        root = pike_doc.Root
        if "/OutputIntents" not in root:
            pike_doc.close()
            return None

        for intent in root["/OutputIntents"]:
            intent_obj = dict(intent)
            if "/DestOutputProfile" in intent_obj:
                profile_stream = intent_obj["/DestOutputProfile"]
                icc_bytes = bytes(profile_stream.read_bytes())
                if len(icc_bytes) > 100:
                    tmp = tempfile.NamedTemporaryFile(suffix=".icc", delete=False)
                    tmp.write(icc_bytes)
                    tmp.close()
                    pike_doc.close()
                    return tmp.name

        pike_doc.close()
    except Exception as e:
        print(f"[color_converter] Error extrayendo ICC embebido: {e}")

    return None
