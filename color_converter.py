"""
color_converter.py – Conversión gestionada RGB→CMYK de imágenes embebidas en PDF.

Utiliza:
  - PyMuPDF  para extraer imágenes por xref
  - PIL / ImageCms  para aplicar transformaciones ICC
  - pikepdf  para sustituir los streams de imagen en el PDF original
"""

from __future__ import annotations

import io
from pdf_graphics import (
    overprint_state_command,
    painting_components,
    rewrite_page_graphics,
    TEXT_SHOW,
)
from pdf_utils import atomic_output, copy_pdf
from security_limits import release_pdf_memory
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
    seen_xrefs: set[int] = set()

    for page_index in range(len(mupdf_doc)):
        page = mupdf_doc[page_index]
        for img_info in page.get_image_info(xrefs=True):
            xref = img_info.get("xref", 0)
            if not xref or xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            cs_num = img_info.get("colorspace", 0)
            cs_name = str(img_info.get("cs-name", "")).upper()
            if cs_num == 3 or "RGB" in cs_name:
                rgb_xrefs.add(xref)
            else:
                result["images_skipped"] += 1

        for img_tuple in page.get_images(full=True):
            xref = img_tuple[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                ext_info = mupdf_doc.extract_image(xref)
                cs_num = ext_info.get("colorspace", 0)
                del ext_info
                if cs_num == 3:
                    rgb_xrefs.add(xref)
                else:
                    result["images_skipped"] += 1
            except Exception:
                pass

    mupdf_doc.close()
    release_pdf_memory()

    if not rgb_xrefs:
        copy_pdf(pdf_path, output_path)
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
                del img_info
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
            release_pdf_memory()

        except Exception as e:
            err_msg = f"xref {xref}: {e}"
            result["errors"].append(err_msg)
            traceback.print_exc()
            result["images_skipped"] += 1

    try:
        with atomic_output(output_path) as temporary:
            pike_doc.save(str(temporary))
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


class _RgbColorConverter:
    """Translate RGB fill/stroke tuples into prepress-safe CMYK / 100% K."""

    def __init__(
        self,
        transform: ImageCms.ImageCmsTransform,
        pure_black_threshold: float = 0.08,
        neutral_tolerance: float = 0.025,
    ) -> None:
        self.transform = transform
        self.pure_black_threshold = float(pure_black_threshold)
        self.neutral_tolerance = float(neutral_tolerance)
        self._cache: dict[tuple[int, int, int], tuple[list[float], str]] = {}

    def convert(self, rgb: tuple[float, ...]) -> tuple[list[float], str]:
        r = min(1.0, max(0.0, float(rgb[0])))
        g = min(1.0, max(0.0, float(rgb[1])))
        b = min(1.0, max(0.0, float(rgb[2])))

        spread = max(r, g, b) - min(r, g, b)
        if spread <= self.neutral_tolerance:
            if max(r, g, b) <= self.pure_black_threshold:
                return [0.0, 0.0, 0.0, 1.0], "pure_k"
            if min(r, g, b) >= 0.995:
                return [0.0, 0.0, 0.0, 0.0], "neutral_k"
            lum = (r + g + b) / 3.0
            k_val = round(min(1.0, max(0.0, 1.0 - lum)), 4)
            return [0.0, 0.0, 0.0, k_val], "neutral_k"

        key = (round(r * 255), round(g * 255), round(b * 255))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        pixel = Image.new("RGB", (1, 1), key)
        cmyk_px = ImageCms.applyTransform(pixel, self.transform)
        c, m, y, k = cmyk_px.getpixel((0, 0))
        del pixel, cmyk_px
        out = ([round(c / 255.0, 4), round(m / 255.0, 4), round(y / 255.0, 4), round(k / 255.0, 4)], "chromatic_cmyk")
        self._cache[key] = out
        return out


def convert_rgb_vectors_to_cmyk(
    pdf_path: str | Path,
    dst_icc_path: str | Path,
    src_icc_path: Optional[str | Path] = None,
    output_path: Optional[str | Path] = None,
    pure_black_threshold: float = 0.08,
    neutral_tolerance: float = 0.025,
    overprint_black_text: bool = True,
) -> dict:
    """Convert RGB vector fills/strokes and text in a PDF to CMYK and pure 100% K."""
    pdf_path = Path(pdf_path)
    out_path = Path(output_path) if output_path else pdf_path
    src_icc = Path(src_icc_path) if src_icc_path else DEFAULT_SRC_ICC
    dst_icc = Path(dst_icc_path)

    result = {
        "success": False,
        "text_ops_converted": 0,
        "vector_ops_converted": 0,
        "pure_k_ops": 0,
        "neutral_k_ops": 0,
        "chromatic_cmyk_ops": 0,
        "black_text_overprinted": 0,
        "pages_modified": 0,
        "errors": [],
    }

    if not src_icc.exists():
        result["errors"].append(f"Perfil ICC fuente no encontrado: {src_icc}")
        return result
    if not dst_icc.exists():
        result["errors"].append(f"Perfil ICC destino no encontrado: {dst_icc}")
        return result

    try:
        transform = _build_transform(src_icc, dst_icc)
    except Exception as exc:
        result["errors"].append(f"Error cargando perfiles ICC: {exc}")
        return result

    converter = _RgbColorConverter(
        transform=transform,
        pure_black_threshold=pure_black_threshold,
        neutral_tolerance=neutral_tolerance,
    )

    try:
        with atomic_output(out_path) as temporary:
            with pikepdf.open(str(pdf_path)) as pdf:
                def convert_op(operands, op, state, resources):
                    fill, stroke = painting_components(op, operands, state)
                    if not (fill or stroke):
                        return [], []

                    before, after = [], []
                    is_text = op in TEXT_SHOW
                    converted_any = False
                    set_fill_overprint = False

                    if fill and state["fill_cs"][0] in ("DeviceRGB", "CalRGB") and len(state["fill_color"]) >= 3:
                        orig_fill = [float(v) for v in state["fill_color"][:3]]
                        cmyk_fill, kind = converter.convert(tuple(orig_fill))
                        before.append((cmyk_fill, pikepdf.Operator("k")))
                        after.append((orig_fill, pikepdf.Operator("rg")))
                        result[kind + "_ops"] += 1
                        converted_any = True
                        if overprint_black_text and is_text and kind == "pure_k" and not state["op"]:
                            set_fill_overprint = True

                    if stroke and state["stroke_cs"][0] in ("DeviceRGB", "CalRGB") and len(state["stroke_color"]) >= 3:
                        orig_stroke = [float(v) for v in state["stroke_color"][:3]]
                        cmyk_stroke, kind = converter.convert(tuple(orig_stroke))
                        before.append((cmyk_stroke, pikepdf.Operator("K")))
                        after.append((orig_stroke, pikepdf.Operator("RG")))
                        result[kind + "_ops"] += 1
                        converted_any = True

                    if set_fill_overprint:
                        before.append(overprint_state_command(resources, True, state["OP"], 1))
                        after.insert(0, overprint_state_command(resources, state["op"], state["OP"], state["OPM"]))
                        result["black_text_overprinted"] += 1

                    if converted_any:
                        if is_text:
                            result["text_ops_converted"] += 1
                        else:
                            result["vector_ops_converted"] += 1
                    return before, after

                for page in pdf.pages:
                    if rewrite_page_graphics(pdf, page, convert_op):
                        result["pages_modified"] += 1
                pdf.save(str(temporary))
                release_pdf_memory()
        result["success"] = True
    except Exception as exc:
        result["errors"].append(f"Error convirtiendo vectores/textos RGB a CMYK: {exc}")
        traceback.print_exc()

    return result
