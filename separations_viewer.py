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
from security_limits import bounded_render_dpi, release_pdf_memory
from PIL import Image, ImageCms, ImageDraw, ImageFont

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

    # Precomputar LUT de 256 entradas por canal (evita alojar cientos de MB en float32)
    x = np.arange(256, dtype=np.float32) / 255.0
    if gamma != 1.0:
        x = np.power(x, gamma)
    lut = np.clip(
        (black_floor[None, :] + x[:, None] * (paper_white - black_floor)[None, :]) * 255.0,
        0, 255,
    ).astype(np.uint8)

    arr_u8 = np.asarray(img_rgb, dtype=np.uint8)
    result = np.empty_like(arr_u8)
    for ch in range(3):
        result[:, :, ch] = lut[arr_u8[:, :, ch], ch]
    return Image.fromarray(result)


_BOX_STYLES = (
    ("mediabox", "MediaBox", (41, 121, 255), 10, 6, 0),
    ("bleedbox", "BleedBox", (255, 61, 0), 8, 6, 4),
    ("trimbox", "TrimBox", (0, 200, 83), 12, 5, 2),
)


def _extract_box_overlays(page: pymupdf.Page, zoom: float, width: int, height: int) -> list[dict]:
    """Map PDF MediaBox/BleedBox/TrimBox into rendered pixel coordinates."""
    rotm = page.rotation_matrix
    crop_rot = page.cropbox * rotm
    origin_x, origin_y = crop_rot.x0, crop_rot.y0
    pt_to_mm = 25.4 / 72.0

    boxes = []
    for key, label, color, dash_len, gap_len, phase in _BOX_STYLES:
        rect = getattr(page, key, None)
        if rect is None or rect.is_empty:
            continue
        r_rot = rect * rotm
        x0 = (r_rot.x0 - origin_x) * zoom
        y0 = (r_rot.y0 - origin_y) * zoom
        x1 = (r_rot.x1 - origin_x) * zoom
        y1 = (r_rot.y1 - origin_y) * zoom
        boxes.append({
            "key": key,
            "label": label,
            "color": color,
            "dash": dash_len,
            "gap": gap_len,
            "phase": phase,
            "coords": (x0, y0, x1, y1),
            "width_mm": round(abs(r_rot.width) * pt_to_mm, 1),
            "height_mm": round(abs(r_rot.height) * pt_to_mm, 1),
            "img_w": width,
            "img_h": height,
        })
    return boxes


def _draw_dashed_segment(
    draw: ImageDraw.ImageDraw,
    p0: tuple[float, float],
    p1: tuple[float, float],
    color: tuple[int, int, int],
    dash_len: int,
    gap_len: int,
    phase: int,
    width: int = 2,
) -> None:
    """Draw a dashed straight line segment cleanly along a box edge."""
    import math
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    if dist < 1.0:
        return
    ux, uy = dx / dist, dy / dist
    period = max(2, dash_len + gap_len)
    pos = float(phase % period)
    while pos < dist:
        seg_end = min(dist, pos + dash_len)
        draw.line(
            [(x0 + ux * pos, y0 + uy * pos), (x0 + ux * seg_end, y0 + uy * seg_end)],
            fill=color,
            width=width,
        )
        pos += period


def _draw_box_guides(rgb_img: Image.Image, boxes: list[dict]) -> Image.Image:
    """Overlay color-coded dashed PDF page boxes (Trim/Bleed/Media) and compact legend."""
    if not boxes:
        return rgb_img
    out = rgb_img.copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size

    for box in boxes:
        x0, y0, x1, y1 = box["coords"]
        # Keep perimeter lines inset by 1 px when aligned with outer page bounds so they remain visible.
        cx0 = max(1.0, min(w - 2.0, x0))
        cy0 = max(1.0, min(h - 2.0, y0))
        cx1 = max(1.0, min(w - 2.0, x1 - 1.0 if x1 >= w else x1))
        cy1 = max(1.0, min(h - 2.0, y1 - 1.0 if y1 >= h else y1))
        if cx1 <= cx0 or cy1 <= cy0:
            continue
        color = box["color"]
        dash, gap, phase = box["dash"], box["gap"], box["phase"]
        edges = [
            ((cx0, cy0), (cx1, cy0)),
            ((cx1, cy0), (cx1, cy1)),
            ((cx1, cy1), (cx0, cy1)),
            ((cx0, cy1), (cx0, cy0)),
        ]
        for p_start, p_end in edges:
            _draw_dashed_segment(draw, p_start, p_end, color, dash, gap, phase, width=2)

    try:
        font = ImageFont.load_default(size=12)
    except TypeError:
        font = ImageFont.load_default()

    pad_x, pad_y, row_h = 8, 6, 16
    box_w = min(w - 16, 225)
    box_h = pad_y * 2 + len(boxes) * row_h
    if w > 120 and h > box_h + 16:
        legend_overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
        ldraw = ImageDraw.Draw(legend_overlay)
        ldraw.rounded_rectangle([8, 8, 8 + box_w, 8 + box_h], radius=6, fill=(15, 23, 42, 210))
        for idx, box in enumerate(boxes):
            ry = 8 + pad_y + idx * row_h
            ldraw.rectangle([8 + pad_x, ry + 3, 8 + pad_x + 10, ry + 11], fill=box["color"] + (255,))
            text = f"{box['label']}: {box['width_mm']}x{box['height_mm']} mm"
            ldraw.text((8 + pad_x + 16, ry), text, fill=(248, 250, 252, 255), font=font)
        out = Image.alpha_composite(out.convert("RGBA"), legend_overlay).convert("RGB")
    return out


def _apply_tac_heatmap(rgb_img: Image.Image, tac_pct: np.ndarray, tac_limit: int) -> Image.Image:
    """Highlight CMYK pixels exceeding tac_limit with amber (moderate) and neon red (severe)."""
    rgb_arr = np.asarray(rgb_img, dtype=np.float32)
    limit = float(tac_limit)
    over_mask = tac_pct > limit
    severe_mask = tac_pct > (limit + 30.0)
    mod_mask = over_mask & ~severe_mask

    # Softly wash compliant areas so excess ink spots stand out clearly while layout remains legible.
    out = np.clip(rgb_arr * 0.42 + 142.0, 0.0, 255.0)
    if np.any(mod_mask):
        amber = np.array([255.0, 160.0, 0.0], dtype=np.float32)
        out[mod_mask] = rgb_arr[mod_mask] * 0.15 + amber * 0.85
    if np.any(severe_mask):
        red = np.array([255.0, 23.0, 68.0], dtype=np.float32)
        out[severe_mask] = rgb_arr[severe_mask] * 0.15 + red * 0.85

    return Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGB")


def _encode_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


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
    show_tac_heatmap: bool = False,
    tac_limit: int = 300,
    show_boxes: bool = False,
) -> bytes:
    """Renderiza una página en separación CMYK y devuelve los bytes JPEG."""
    img_bytes, _meta = render_page_separation_with_meta(
        pdf_path=pdf_path,
        page_index=page_index,
        show_c=show_c,
        show_m=show_m,
        show_y=show_y,
        show_k=show_k,
        disabled_spots=disabled_spots,
        view_mode=view_mode,
        dpi=dpi,
        icc_cmyk_path=icc_cmyk_path,
        simulate_paper=simulate_paper,
        paper_type=paper_type,
        simulate_black_ink=simulate_black_ink,
        show_tac_heatmap=show_tac_heatmap,
        tac_limit=tac_limit,
        show_boxes=show_boxes,
    )
    return img_bytes


def render_page_separation_with_meta(
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
    show_tac_heatmap: bool = False,
    tac_limit: int = 300,
    show_boxes: bool = False,
) -> tuple[bytes, dict]:
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
    zoom = bounded_render_dpi(page.rect, dpi) / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    try:
        pix = page._makePixmap(doc, mat, pymupdf.csCMYK, 0, 1, None)
    except Exception:
        pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csCMYK, alpha=False)

    w, h = pix.width, pix.height
    num_channels = pix.n
    box_overlays = _extract_box_overlays(page, zoom, w, h) if show_boxes else []
    doc.close()

    # Convertir muestras a array NumPy de forma (H, W, 4)
    # Canales: 0=Cyan, 1=Magenta, 2=Yellow, 3=Black (valores 0..255)
    raw = np.frombuffer(pix.samples, dtype=np.uint8).reshape((h, w, num_channels))
    arr = raw[:, :, :4].copy()
    del raw, pix
    release_pdf_memory()

    # Filtrar planchas desactivadas antes de evaluar cobertura y renderizar
    if not show_c:
        arr[:, :, 0] = 0
    if not show_m:
        arr[:, :, 1] = 0
    if not show_y:
        arr[:, :, 2] = 0
    if not show_k:
        arr[:, :, 3] = 0

    tac_pct = arr.sum(axis=2, dtype=np.uint16).astype(np.float32) * (100.0 / 255.0)
    tac_limit_clamped = max(180, min(400, int(tac_limit)))
    over_mask = tac_pct > float(tac_limit_clamped)
    meta = {
        "tac_limit": tac_limit_clamped,
        "tac_max_pct": round(float(tac_pct.max()), 1) if tac_pct.size else 0.0,
        "tac_over_area_pct": round(float(np.mean(over_mask) * 100.0), 2) if tac_pct.size else 0.0,
        "boxes": [
            {"label": b["label"], "width_mm": b["width_mm"], "height_mm": b["height_mm"]}
            for b in box_overlays
        ],
    }

    # Si se pide visualización de plancha individual en escala de grises (película RIP)
    active_channels = [c for c, active in enumerate([show_c, show_m, show_y, show_k]) if active]
    if view_mode == "grayscale" and len(active_channels) == 1:
        ch_idx = active_channels[0]
        # Invertir: 0 tinta = 255 (blanco de papel), 255 tinta = 0 (negro de película)
        ch_data = 255 - arr[:, :, ch_idx]
        del arr
        img_gray = Image.fromarray(ch_data, "L")
        del ch_data
        if show_tac_heatmap or show_boxes:
            rgb_img = img_gray.convert("RGB")
            del img_gray
            if show_tac_heatmap:
                rgb_img = _apply_tac_heatmap(rgb_img, tac_pct, tac_limit_clamped)
            if show_boxes:
                rgb_img = _draw_box_guides(rgb_img, box_overlays)
            out_bytes = _encode_jpeg(rgb_img)
            del rgb_img, tac_pct
        else:
            out_bytes = _encode_jpeg(img_gray)
            del img_gray, tac_pct
        release_pdf_memory()
        return out_bytes, meta

    cmyk_img = Image.fromarray(arr, "CMYK")
    del arr

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
    finally:
        del cmyk_img

    # Soft Proofing: Simulación física de papel y tinta si está activada
    if simulate_paper and not show_tac_heatmap:
        rgb_img = apply_substrate_simulation(
            rgb_img,
            paper_type=paper_type,
            simulate_black=simulate_black_ink
        )

    if show_tac_heatmap:
        rgb_img = _apply_tac_heatmap(rgb_img, tac_pct, tac_limit_clamped)
    del tac_pct

    if show_boxes:
        rgb_img = _draw_box_guides(rgb_img, box_overlays)

    out_bytes = _encode_jpeg(rgb_img)
    del rgb_img
    release_pdf_memory()
    return out_bytes, meta

