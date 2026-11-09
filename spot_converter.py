"""
spot_converter.py
=================
Motor de conversión de tintas planas / directas (Pantone, PMS, HKS, directas)
a cuatricromía (CMYK de proceso).

Preserva intactas las tintas técnicas como barnices, lacas, estampaciones y troqueles
(dieline), transformando las tintas planas comerciales en sus equivalentes DeviceCMYK.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Union, Optional
from decimal import Decimal

import pikepdf

logger = logging.getLogger(__name__)

VARNISH_KEYWORDS = [
    'barniz', 'varnish', 'laca', 'lacquer', 'uv', 'gloss', 'brillo',
    'mate', 'matt', 'acabado', 'dieline', 'troquel', 'stamping', 'corte'
]


def is_technical_ink(name: str) -> bool:
    """True si la tinta es técnica (barniz, troquel, laca), no comercial (Pantone)."""
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(name)).lower()
    return any(k in clean for k in VARNISH_KEYWORDS)


def lab_to_cmyk(L: float, a: float, b: float) -> tuple[float, float, float, float]:
    """Convierte Lab a CMYK aproximado (mediante sRGB intermedio)."""
    try:
        y = (float(L) + 16.0) / 116.0
        x = float(a) / 500.0 + y
        z = y - float(b) / 200.0

        def f_inv(t):
            return t**3 if t > 0.2068966 else 3.0 * (0.2068966**2) * (t - 4.0 / 29.0)

        X = 0.95047 * f_inv(x)
        Y = 1.00000 * f_inv(y)
        Z = 1.08883 * f_inv(z)

        r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z
        g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z
        bl = 0.0557 * X - 0.2040 * Y + 1.0570 * Z

        def gamma(v):
            v = max(0.0, min(1.0, v))
            return 1.055 * (v ** (1.0 / 2.4)) - 0.055 if v > 0.0031308 else 12.92 * v

        rf = max(0.0, min(1.0, gamma(r)))
        gf = max(0.0, min(1.0, gamma(g)))
        bf = max(0.0, min(1.0, gamma(bl)))

        # RGB a CMYK estándar
        k = 1.0 - max(rf, gf, bf)
        if k >= 1.0:
            return 0.0, 0.0, 0.0, 1.0
        c = (1.0 - rf - k) / (1.0 - k)
        m = (1.0 - gf - k) / (1.0 - k)
        y_val = (1.0 - bf - k) / (1.0 - k)
        return round(c, 4), round(m, 4), round(y_val, 4), round(k, 4)
    except Exception:
        return 0.0, 0.0, 0.0, 1.0


def rgb_to_cmyk(r: float, g: float, b: float) -> tuple[float, float, float, float]:
    """Convierte RGB (0-1) a CMYK (0-1)."""
    k = 1.0 - max(r, g, b)
    if k >= 1.0:
        return 0.0, 0.0, 0.0, 1.0
    c = (1.0 - r - k) / (1.0 - k)
    m = (1.0 - g - k) / (1.0 - k)
    y = (1.0 - b - k) / (1.0 - k)
    return round(c, 4), round(m, 4), round(y, 4), round(k, 4)


def extract_spot_cmyk_equivalent(cs_val: pikepdf.Array) -> tuple[str, tuple[float, float, float, float]]:
    """
    Dada la definición de un espacio de color Separation o DeviceN,
    devuelve (nombre_tinta, (c, m, y, k)) con su equivalente CMYK al 100%.
    """
    if len(cs_val) < 2:
        return "", (0.0, 0.0, 0.0, 1.0)

    name = str(cs_val[1]).lstrip('/')
    alt_space = str(cs_val[2]) if len(cs_val) > 2 else "/DeviceCMYK"
    func = cs_val[3] if len(cs_val) > 3 else None

    cmyk = (0.0, 0.0, 0.0, 1.0)

    if func and hasattr(func, 'get') and '/C1' in func:
        try:
            c1 = [float(x) for x in func['/C1']]
            if '/DeviceCMYK' in alt_space or len(c1) == 4:
                cmyk = (round(c1[0], 4), round(c1[1], 4), round(c1[2], 4), round(c1[3], 4))
            elif 'Lab' in alt_space or len(c1) == 3:
                cmyk = lab_to_cmyk(c1[0], c1[1], c1[2])
            elif '/DeviceRGB' in alt_space:
                cmyk = rgb_to_cmyk(c1[0], c1[1], c1[2])
        except Exception as e:
            logger.warning(f"No se pudo extraer C1 de la tinta {name}: {e}")

    return name, cmyk


def convert_spot_colors_to_cmyk(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    target_spots: Optional[list[str]] = None,
    convert_technical: bool = False,
) -> dict:
    """
    Convierte tintas planas (Separation y DeviceN) a cuatricromía (CMYK).
    
    - target_spots: si se indica, solo convierte las tintas de la lista.
    - convert_technical: si es False (por defecto), nunca convierte barnices ni troqueles.
    
    Retorna dict con claves:
        success: bool
        spots_converted: list[dict]
        pages_modified: int
        errors: list[str]
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    errors: list[str] = []
    converted_info: dict[str, dict] = {}
    pages_modified_count = 0

    try:
        pdf = pikepdf.open(str(pdf_path), allow_overwriting_input=True)
    except Exception as e:
        return {
            "success": False,
            "spots_converted": [],
            "pages_modified": 0,
            "errors": [f"No se pudo abrir el PDF: {e}"],
        }

    try:
        for p_idx, page in enumerate(pdf.pages, 1):
            page_modified = False
            res = page.obj.get('/Resources')
            if not res or '/ColorSpace' not in res:
                continue

            cs_dict = res['/ColorSpace']
            # Mapeo: cs_key_in_resources -> (spot_name, (c, m, y, k))
            spots_to_convert: dict[str, tuple[str, tuple[float, float, float, float]]] = {}

            for cs_key, cs_val in list(cs_dict.items()):
                if not isinstance(cs_val, pikepdf.Array) or len(cs_val) < 2:
                    continue

                cs_type = str(cs_val[0])
                if cs_type not in ('/Separation', '/DeviceN'):
                    continue

                spot_name, cmyk_base = extract_spot_cmyk_equivalent(cs_val)
                if not spot_name or spot_name in ('All', 'None'):
                    continue

                # Filtrar si no se deben convertir barnices/troqueles
                if not convert_technical and is_technical_ink(spot_name):
                    continue

                # Filtrar por lista objetivo si se especificó
                if target_spots is not None and spot_name not in target_spots:
                    continue

                key_str = str(cs_key)
                spots_to_convert[key_str] = (spot_name, cmyk_base)
                if spot_name not in converted_info:
                    converted_info[spot_name] = {
                        "name": spot_name,
                        "cmyk_base": list(cmyk_base),
                        "cmyk_str": f"C:{int(round(cmyk_base[0]*100))}% M:{int(round(cmyk_base[1]*100))}% Y:{int(round(cmyk_base[2]*100))}% K:{int(round(cmyk_base[3]*100))}%",
                        "pages": []
                    }
                if p_idx not in converted_info[spot_name]["pages"]:
                    converted_info[spot_name]["pages"].append(p_idx)

            if not spots_to_convert:
                continue

            # Procesar el stream de contenido de la página
            try:
                raw_cmds = pikepdf.parse_content_stream(page)
                new_cmds = _transform_stream_spots_to_cmyk(raw_cmds, spots_to_convert)
                page.Contents = pikepdf.Stream(pdf, pikepdf.unparse_content_stream(new_cmds))
                page_modified = True
            except Exception as e:
                errors.append(f"Error procesando stream de pág {p_idx}: {e}")

            # También procesar XObjects Form si los hay en la página
            if '/XObject' in res:
                for xk, xv in res['/XObject'].items():
                    if isinstance(xv, pikepdf.Stream) and xv.get('/Subtype') == '/Form':
                        try:
                            f_cmds = pikepdf.parse_content_stream(xv)
                            new_f_cmds = _transform_stream_spots_to_cmyk(f_cmds, spots_to_convert)
                            xv.write(pikepdf.unparse_content_stream(new_f_cmds))
                            page_modified = True
                        except Exception:
                            pass

            # Eliminar o sustituir los ColorSpaces convertidos de Resources
            for cs_key in spots_to_convert.keys():
                try:
                    cs_dict[cs_key] = pikepdf.Name('/DeviceCMYK')
                except Exception:
                    pass

            if page_modified:
                pages_modified_count += 1

        pdf.save(str(output_path))
        logger.info(f"[spot_converter] Guardado en {output_path} con {len(converted_info)} tintas convertidas.")

    except Exception as e:
        errors.append(f"Error al guardar el PDF convertido: {e}")
        return {
            "success": False,
            "spots_converted": list(converted_info.values()),
            "pages_modified": pages_modified_count,
            "errors": errors,
        }
    finally:
        pdf.close()

    return {
        "success": True,
        "spots_converted": list(converted_info.values()),
        "pages_modified": pages_modified_count,
        "errors": errors,
    }


def _transform_stream_spots_to_cmyk(
    commands: list,
    spots_map: dict[str, tuple[str, tuple[float, float, float, float]]]
) -> list:
    """
    Sustituye los operadores de tintas directas en el stream por operadores DeviceCMYK equivalentes.
    """
    new_commands = []
    current_fill_cmyk: Optional[tuple[float, float, float, float]] = None
    current_stroke_cmyk: Optional[tuple[float, float, float, float]] = None

    for operands, op in commands:
        op_str = str(op)

        if op_str == 'cs':
            if operands:
                cs_key = str(operands[0])
                if cs_key in spots_map:
                    current_fill_cmyk = spots_map[cs_key][1]
                    new_commands.append(([pikepdf.Name('/DeviceCMYK')], pikepdf.Operator('cs')))
                    continue
                else:
                    current_fill_cmyk = None
        elif op_str == 'CS':
            if operands:
                cs_key = str(operands[0])
                if cs_key in spots_map:
                    current_stroke_cmyk = spots_map[cs_key][1]
                    new_commands.append(([pikepdf.Name('/DeviceCMYK')], pikepdf.Operator('CS')))
                    continue
                else:
                    current_stroke_cmyk = None
        elif op_str in ('sc', 'scn') and current_fill_cmyk:
            try:
                tint = float(operands[0]) if operands else 1.0
                tint = max(0.0, min(1.0, tint))
                c = round(tint * current_fill_cmyk[0], 4)
                m = round(tint * current_fill_cmyk[1], 4)
                y = round(tint * current_fill_cmyk[2], 4)
                k = round(tint * current_fill_cmyk[3], 4)
                new_commands.append(([c, m, y, k], pikepdf.Operator('k')))
                continue
            except Exception:
                pass
        elif op_str in ('SC', 'SCN') and current_stroke_cmyk:
            try:
                tint = float(operands[0]) if operands else 1.0
                tint = max(0.0, min(1.0, tint))
                c = round(tint * current_stroke_cmyk[0], 4)
                m = round(tint * current_stroke_cmyk[1], 4)
                y = round(tint * current_stroke_cmyk[2], 4)
                k = round(tint * current_stroke_cmyk[3], 4)
                new_commands.append(([c, m, y, k], pikepdf.Operator('K')))
                continue
            except Exception:
                pass
        elif op_str in ('g', 'rg', 'k'):
            current_fill_cmyk = None
        elif op_str in ('G', 'RG', 'K'):
            current_stroke_cmyk = None

        new_commands.append((operands, op))

    return new_commands

