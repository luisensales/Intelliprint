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
import pikepdf
import pymupdf
from PIL import Image, ImageCms

ICC_DIR = Path(__file__).parent / "icc_profiles"
DEFAULT_CMYK_ICC = ICC_DIR / "ISOcoated_v2_300_bas.icc"
DEFAULT_RGB_ICC = ICC_DIR / "sRGB2014.icc"


def apply_substrate_simulation(
    img_rgb: Image.Image,
    paper_type: str = "uncoated",
    simulate_black: bool = True
) -> Image.Image:
    """
    Aplica simulación física de sustrato (Soft Proofing):
    1. Tono y blanco natural del papel (estucado, offset no estucado, papel prensa ahuesado, kraft).
    2. Ganancia de punto (TVI - oscurecimiento de medios tonos por absorción capilar de fibras).
    3. Simulación de tinta negra (Dmax reducida en papeles porosos, evitando negros irreales de monitor).
    """
    arr = np.array(img_rgb, dtype=np.float32) / 255.0

    if paper_type == "newsprint":
        # Papel prensa: pasta mecánica con lignina, tono ahuesado/grisáceo, alta ganancia de punto
        paper_white = np.array([0.915, 0.885, 0.825], dtype=np.float32)
        black_floor = np.array([0.22, 0.21, 0.20], dtype=np.float32) if simulate_black else np.array([0.05, 0.05, 0.05], dtype=np.float32)
        gamma = 0.84  # TVI Curva E (~26% ganancia en 50%)
    elif paper_type == "kraft":
        # Cartoncillo kraft reciclado: fibra marrón natural, absorción directa
        paper_white = np.array([0.845, 0.755, 0.635], dtype=np.float32)
        black_floor = np.array([0.20, 0.18, 0.15], dtype=np.float32) if simulate_black else np.array([0.05, 0.05, 0.05], dtype=np.float32)
        gamma = 0.87
    elif paper_type == "uncoated":
        # Offset blanco natural / no estucado (FOGRA52): sin blanqueantes ópticos agresivos, tono crema suave
        paper_white = np.array([0.965, 0.950, 0.920], dtype=np.float32)
        black_floor = np.array([0.16, 0.16, 0.15], dtype=np.float32) if simulate_black else np.array([0.05, 0.05, 0.05], dtype=np.float32)
        gamma = 0.89  # TVI Curva C (~19-22% ganancia en 50%)
    else:  # coated (estucado brillante / semimate FOGRA39/51)
        # Papel estucado con capa de carbonato/caolín y abrillantador óptico
        paper_white = np.array([0.992, 0.992, 0.998], dtype=np.float32)
        black_floor = np.array([0.06, 0.06, 0.06], dtype=np.float32) if simulate_black else np.array([0.03, 0.03, 0.03], dtype=np.float32)
        gamma = 1.00  # TVI Curva A (~14% compensado en perfil)

    # Aplicar curva de ganancia de punto a la imagen (en medios tonos)
    if gamma != 1.0:
        arr = np.power(arr, gamma)

    # Interpolar entre cota de negro y blanco de papel
    result = black_floor + arr * (paper_white - black_floor)
    result = np.clip(result * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(result)


def render_page_separation(
    pdf_path: str | Path,
    page_index: int = 0,
    show_c: bool = True,
    show_m: bool = True,
    show_y: bool = True,
    show_k: bool = True,
    disabled_spots: Optional[list[str]] = None,
    view_mode: str = "color",  # "color" o "grayscale"
    dpi: int = 120,
    icc_cmyk_path: Optional[str | Path] = None,
    simulate_paper: bool = False,
    paper_type: str = "coated",
    simulate_black_ink: bool = True,
) -> bytes:
    """
    Renderiza una página PDF simulando la selección de planchas de separación CMYK y tintas planas,
    con soporte opcional de Soft Proofing (simulación de soporte de papel y tinta).

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

    # Si hay tintas directas desactivadas, anulamos su función de color en memoria
    mem_pdf_bytes = None
    if disabled_spots:
        try:
            p_doc = pikepdf.open(str(pdf_path))
            modified = False
            for page in p_doc.pages:
                res = page.obj.get('/Resources')
                if not res:
                    continue
                cs_dict = res.get('/ColorSpace', {})
                for cs_k, cs_v in cs_dict.items():
                    if isinstance(cs_v, pikepdf.Array) and len(cs_v) >= 4 and str(cs_v[0]) == '/Separation':
                        s_name = str(cs_v[1]).lstrip('/')
                        if s_name in disabled_spots:
                            func = cs_v[3]
                            if hasattr(func, 'get') and '/C0' in func:
                                func['/C1'] = func['/C0']
                                modified = True
            if modified:
                buf = io.BytesIO()
                p_doc.save(buf)
                mem_pdf_bytes = buf.getvalue()
            p_doc.close()
        except Exception:
            pass

    if mem_pdf_bytes:
        doc = pymupdf.open(stream=mem_pdf_bytes, filetype="pdf")
    else:
        doc = pymupdf.open(str(pdf_path))

    if page_index < 0 or page_index >= len(doc):
        doc.close()
        raise IndexError(f"Página {page_index + 1} fuera de rango (total {len(doc)}).")

    # Anular la re-separación interna de MuPDF:
    # Cuando un PDF contiene un OutputIntent (PDF/X), MuPDF aplica gestión de color interna
    # re-separando los colores DeviceCMYK nativos (como el texto 100% K u 80% K) en una
    # mezcla de cuatricromía CMYK (C>0, M>0, Y>0, K>0).
    # Al desactivar temporalmente el diccionario OutputIntents del catálogo en memoria,
    # MuPDF rasteriza los canales DeviceCMYK puros directamente en sus planchas nativas
    # (C, M, Y, K exactos), permitiendo aislar o desactivar la plancha negra como en Acrobat.
    try:
        cat = doc.pdf_catalog()
        doc.xref_set_key(cat, "OutputIntents", "null")
    except Exception:
        pass

    page = doc[page_index]

    # Renderizar la página directamente con el draw device nativo de MuPDF
    # (evita DisplayList, que descarta los estados de sobreimpresión /OP True /op True)
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    try:
        pix = page._makePixmap(doc, mat, pymupdf.csCMYK, 0, 1, None)
    except Exception:
        pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csCMYK, alpha=False)

    w, h = pix.width, pix.height
    num_channels = pix.n
    doc.close()

    # Convertir muestras a array NumPy de forma (H, W, 4)
    # Canales: 0=Cyan, 1=Magenta, 2=Yellow, 3=Black (valores 0..255)
    raw = np.frombuffer(pix.samples, dtype=np.uint8).reshape((h, w, num_channels))
    arr = raw[:, :, :4].copy()

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
    intent = ImageCms.Intent.ABSOLUTE_COLORIMETRIC if simulate_paper else ImageCms.Intent.RELATIVE_COLORIMETRIC
    try:
        rgb_img = ImageCms.profileToProfile(
            cmyk_img,
            str(cmyk_profile),
            str(DEFAULT_RGB_ICC),
            renderingIntent=intent,
            outputMode="RGB",
        )
    except Exception:
        # Fallback a conversión básica PIL si falla el transform ICC
        rgb_img = cmyk_img.convert("RGB")

    # Soft Proofing: Simulación física de papel y tinta si está activada
    if simulate_paper:
        rgb_img = apply_substrate_simulation(
            rgb_img,
            paper_type=paper_type,
            simulate_black=simulate_black_ink
        )

    buf = io.BytesIO()
    rgb_img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()

