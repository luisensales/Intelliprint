"""
separations_viewer.py – Motor de separación de color CMYK para previsualización estilo Adobe Acrobat.

Permite:
  1. Renderizar páginas PDF en DeviceCMYK a resolución configurada.
  2. Filtrar canales activos (C, M, Y, K) simulando sobreimpresión y calado.
  3. Visualizar en color compuesto (simulación de imprenta con ICC) o en película monocroma de plancha RIP.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

import numpy as np
import pymupdf
from PIL import Image, ImageCms

ICC_DIR = Path(__file__).parent / "icc_profiles"
DEFAULT_CMYK_ICC = ICC_DIR / "ISOcoated_v2_300_bas.icc"
DEFAULT_RGB_ICC = ICC_DIR / "sRGB2014.icc"


def render_page_separation(
    pdf_path: str | Path,
    page_index: int = 0,
    show_c: bool = True,
    show_m: bool = True,
    show_y: bool = True,
    show_k: bool = True,
    view_mode: str = "color",  # "color" o "grayscale"
    dpi: int = 120,
    icc_cmyk_path: Optional[str | Path] = None,
) -> bytes:
    """
    Renderiza una página PDF simulando la selección de planchas de separación CMYK.

    Devuelve los bytes JPEG de la imagen resultante.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    cmyk_profile = Path(icc_cmyk_path) if icc_cmyk_path else DEFAULT_CMYK_ICC
    if not cmyk_profile.exists():
        cmyk_profile = DEFAULT_CMYK_ICC
    else:
        try:
            prof = ImageCms.ImageCmsProfile(str(cmyk_profile))
            if str(prof.profile.xcolor_space).strip().upper() != "CMYK":
                cmyk_profile = DEFAULT_CMYK_ICC
        except Exception:
            cmyk_profile = DEFAULT_CMYK_ICC

    doc = pymupdf.open(str(pdf_path))
    if page_index < 0 or page_index >= len(doc):
        doc.close()
        raise IndexError(f"Página {page_index + 1} fuera de rango (total {len(doc)}).")

    page = doc[page_index]

    # Renderizar la página en DeviceCMYK nativo con sobreimpresión activa
    pix = page.get_pixmap(colorspace=pymupdf.csCMYK, dpi=dpi, alpha=False)
    w, h = pix.width, pix.height
    doc.close()

    # Convertir muestras a array NumPy de forma (H, W, 4)
    # Canales: 0=Cyan, 1=Magenta, 2=Yellow, 3=Black (valores 0..255)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape((h, w, 4)).copy()

    # Si se pide visualización de plancha individual en escala de grises (película RIP)
    active_channels = [c for c, active in enumerate([show_c, show_m, show_y, show_k]) if active]
    if view_mode == "grayscale" and len(active_channels) == 1:
        ch_idx = active_channels[0]
        # Invertir: 0 tinta = 255 (blanco de papel), 255 tinta = 0 (negro de película)
        ch_data = 255 - arr[:, :, ch_idx]
        img_gray = Image.fromarray(ch_data, "L")
        buf = io.BytesIO()
        img_gray.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    # Modo simulación de color compuesto
    if not show_c:
        arr[:, :, 0] = 0
    if not show_m:
        arr[:, :, 1] = 0
    if not show_y:
        arr[:, :, 2] = 0
    if not show_k:
        arr[:, :, 3] = 0

    cmyk_img = Image.fromarray(arr, "CMYK")

    # Conversión colorimétrica CMYK -> RGB con perfiles ICC
    try:
        rgb_img = ImageCms.profileToProfile(
            cmyk_img,
            str(cmyk_profile),
            str(DEFAULT_RGB_ICC),
            renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
            outputMode="RGB",
        )
    except Exception:
        # Fallback a conversión básica PIL si falla el transform ICC
        rgb_img = cmyk_img.convert("RGB")

    buf = io.BytesIO()
    rgb_img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()

