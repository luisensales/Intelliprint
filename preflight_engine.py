import os
import re
import json
import pymupdf as fitz
import pikepdf
from decimal import Decimal
from pathlib import Path
from icc_manager import detect_pdf_output_intent, apply_icc_to_pdf
from spellcheck_engine import PrepressSpellChecker

VARNISH_KEYWORDS = ['barniz', 'varnish', 'laca', 'lacquer', 'uv', 'gloss', 'brillo', 'mate', 'matt', 'acabado', 'dieline', 'troquel', 'stamping']

def is_varnish_name(name):
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(name)).lower()
    return any(k in clean for k in VARNISH_KEYWORDS)

def is_pantone_name(name):
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(name)).lower()
    return 'pantone' in clean or 'pms' in clean

def resolve_cs(cs_ref, resources):
    if isinstance(cs_ref, pikepdf.Name):
        cs_str = str(cs_ref).lstrip('/')
        if resources and '/ColorSpace' in resources and cs_ref in resources['/ColorSpace']:
            return resolve_cs(resources['/ColorSpace'][cs_ref], resources)
        return (cs_str, None)
    elif isinstance(cs_ref, pikepdf.Array) and len(cs_ref) > 0:
        cs_type = str(cs_ref[0]).lstrip('/')
        if cs_type in ['Separation', 'DeviceN'] and len(cs_ref) > 1:
            spot_name = str(cs_ref[1]).lstrip('/')
            return (cs_type, spot_name)
        return (cs_type, None)
    return (str(cs_ref), None)

def _lab_to_rgb(L, a, b):
    try:
        y = (float(L) + 16.0) / 116.0
        x = float(a) / 500.0 + y
        z = y - float(b) / 200.0
        def f_inv(t):
            return t**3 if t > 0.2068966 else 3.0 * (0.2068966**2) * (t - 4.0/29.0)
        X = 0.95047 * f_inv(x)
        Y = 1.00000 * f_inv(y)
        Z = 1.08883 * f_inv(z)
        r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z
        g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z
        b = 0.0557 * X - 0.2040 * Y + 1.0570 * Z
        def gamma(v):
            v = max(0.0, min(1.0, v))
            return 1.055 * (v ** (1.0/2.4)) - 0.055 if v > 0.0031308 else 12.92 * v
        R = int(round(gamma(r) * 255))
        G = int(round(gamma(g) * 255))
        B = int(round(gamma(b) * 255))
        return f"#{R:02x}{G:02x}{B:02x}"
    except Exception:
        return "#475569"


def _cmyk_to_rgb(c, m, y, k):
    try:
        r = int(round(255 * (1.0 - float(c)) * (1.0 - float(k))))
        g = int(round(255 * (1.0 - float(m)) * (1.0 - float(k))))
        b = int(round(255 * (1.0 - float(y)) * (1.0 - float(k))))
        return f"#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,b)):02x}"
    except Exception:
        return "#475569"


def extract_pdf_spot_colors(pike_doc) -> list[dict]:
    """
    Extrae todas las tintas planas / directas (Separation y DeviceN) del documento PDF,
    identificando su nombre (ej: PANTONE 7545 C, Barniz, Troquel), su tipo y su color
    aproximado en hexadecimal para la muestra en la interfaz.
    """
    spots = {}
    try:
        for p_idx, page in enumerate(pike_doc.pages, 1):
            res = page.obj.get('/Resources')
            if not res:
                continue
            cs_dict = res.get('/ColorSpace', {})
            for cs_name, cs_val in cs_dict.items():
                if not isinstance(cs_val, pikepdf.Array) or len(cs_val) < 2:
                    continue
                cs_type = str(cs_val[0])
                names = []
                if cs_type == '/Separation':
                    name = str(cs_val[1]).lstrip('/')
                    if name not in ('All', 'None'):
                        names.append(name)
                elif cs_type == '/DeviceN' and len(cs_val) >= 2:
                    names_arr = cs_val[1]
                    if isinstance(names_arr, pikepdf.Array):
                        for n in names_arr:
                            name = str(n).lstrip('/')
                            if name not in ('All', 'None', 'Cyan', 'Magenta', 'Yellow', 'Black'):
                                names.append(name)

                # Aproximar color de muestra para la interfaz
                hex_color = "#475569"
                alt_space = str(cs_val[2]) if len(cs_val) > 2 else ""
                func = cs_val[3] if len(cs_val) > 3 else None
                if func and hasattr(func, 'get') and '/C1' in func:
                    try:
                        c1 = [float(x) for x in func['/C1']]
                        if 'Lab' in alt_space or len(c1) == 3:
                            hex_color = _lab_to_rgb(c1[0], c1[1], c1[2])
                        elif len(c1) >= 4:
                            hex_color = _cmyk_to_rgb(c1[0], c1[1], c1[2], c1[3])
                    except Exception:
                        pass

                for name in names:
                    if name not in spots:
                        s_type = "PANTONE" if is_pantone_name(name) else ("BARNIZ" if is_varnish_name(name) else "DIRECTA")
                        spots[name] = {
                            "name": name,
                            "type": s_type,
                            "color_hex": hex_color,
                            "pages": []
                        }
                    if p_idx not in spots[name]["pages"]:
                        spots[name]["pages"].append(p_idx)
    except Exception:
        pass
    return list(spots.values())


def _has_visible_text(op_str: str, operands: list) -> bool:
    """Retorna True si la operacion contiene texto visible (no solo espacios en blanco)."""
    if not operands:
        return False
    txt = []
    if op_str in ('Tj', "'", '"'):
        txt.append(str(operands[0]))
    elif op_str == 'TJ':
        for item in operands[0]:
            if not isinstance(item, (int, float)):
                txt.append(str(item))
    return bool(''.join(txt).strip())


def is_fill_color_white(cs_type, fill_color):
    """Retorna True si el color de relleno es blanco (0% tinta en CMYK/Gray o 100% RGB)."""
    if not fill_color:
        return False
    if cs_type == 'DeviceGray' and len(fill_color) >= 1:
        return fill_color[0] >= 0.99
    elif cs_type == 'DeviceRGB' and len(fill_color) >= 3:
        return all(c >= 0.98 for c in fill_color[:3])
    elif cs_type == 'DeviceCMYK' and len(fill_color) >= 4:
        return all(c <= 0.01 for c in fill_color[:4])
    return False

def is_stroke_color_white(cs_type, stroke_color):
    """Retorna True si el color de trazo es blanco (0% tinta en CMYK/Gray o 100% RGB)."""
    if not stroke_color:
        return False
    if cs_type == 'DeviceGray' and len(stroke_color) >= 1:
        return stroke_color[0] >= 0.99
    elif cs_type == 'DeviceRGB' and len(stroke_color) >= 3:
        return all(c >= 0.98 for c in stroke_color[:3])
    elif cs_type == 'DeviceCMYK' and len(stroke_color) >= 4:
        return all(c <= 0.01 for c in stroke_color[:4])
    return False

def scan_content_stream(commands, resources, page_num, overprint_data):
    ext_gstates = {}
    if resources and '/ExtGState' in resources:
        for k, v in resources['/ExtGState'].items():
            ext_gstates[k] = v

    xobjects = {}
    if resources and '/XObject' in resources:
        for k, v in resources['/XObject'].items():
            xobjects[k] = v

    state_stack = []
    state = {
        'op': False,
        'OP': False,
        'OPM': 0,
        'fill_cs': ('DeviceGray', None),
        'stroke_cs': ('DeviceGray', None),
        'fill_color': (0,),
        'stroke_color': (0,),
        'text_render_mode': 0,
        'font_size': 0.0,          # tamaño de fuente actual (pt)
        'ctm_scale': 1.0,          # escala del CTM para calcular tamaño real
        'line_width': 1.0,         # grosor de línea en pt (por defecto 1.0 en spec PDF)
    }

    for operands, operator in commands:
        op_str = str(operator)

        if op_str == 'q':
            state_stack.append(dict(state))
        elif op_str == 'Q':
            if state_stack:
                state = state_stack.pop()
        elif op_str == 'gs':
            if operands and operands[0] in ext_gstates:
                gs_dict = ext_gstates[operands[0]]
                if '/op' in gs_dict:
                    state['op'] = bool(gs_dict['/op'])
                if '/OP' in gs_dict:
                    state['OP'] = bool(gs_dict['/OP'])
                if '/OPM' in gs_dict:
                    state['OPM'] = int(gs_dict['/OPM'])
        elif op_str == 'Tr':
            if operands:
                try:
                    state['text_render_mode'] = int(operands[0])
                except Exception:
                    pass
        elif op_str == 'Tf':
            # Tf fontname fontsize — rastrear tamaño de fuente actual
            if len(operands) >= 2:
                try:
                    state['font_size'] = float(operands[1])
                except Exception:
                    pass
        elif op_str == 'cm':
            # cm a b c d e f — actualizar escala aproximada del CTM
            if len(operands) >= 6:
                try:
                    import math
                    a, b = float(operands[0]), float(operands[1])
                    state['ctm_scale'] = math.sqrt(a*a + b*b)
                except Exception:
                    pass
        elif op_str == 'w':
            # w line_width — grosor de trazo en espacio de usuario
            if operands:
                try:
                    state['line_width'] = float(operands[0])
                except Exception:
                    pass
        elif op_str == 'g':
            state['fill_cs'] = ('DeviceGray', None)
            state['fill_color'] = tuple(float(x) for x in operands)
        elif op_str == 'G':
            state['stroke_cs'] = ('DeviceGray', None)
            state['stroke_color'] = tuple(float(x) for x in operands)
        elif op_str == 'k':
            state['fill_cs'] = ('DeviceCMYK', None)
            state['fill_color'] = tuple(float(x) for x in operands)
        elif op_str == 'K':
            state['stroke_cs'] = ('DeviceCMYK', None)
            state['stroke_color'] = tuple(float(x) for x in operands)
        elif op_str == 'rg':
            state['fill_cs'] = ('DeviceRGB', None)
            state['fill_color'] = tuple(float(x) for x in operands)
        elif op_str == 'RG':
            state['stroke_cs'] = ('DeviceRGB', None)
            state['stroke_color'] = tuple(float(x) for x in operands)
        elif op_str == 'cs':
            if operands:
                state['fill_cs'] = resolve_cs(operands[0], resources)
        elif op_str == 'CS':
            if operands:
                state['stroke_cs'] = resolve_cs(operands[0], resources)
        elif op_str in ['sc', 'scn']:
            state['fill_color'] = tuple(float(x) for x in operands if isinstance(x, (int, float, Decimal)))
        elif op_str in ['SC', 'SCN']:
            state['stroke_color'] = tuple(float(x) for x in operands if isinstance(x, (int, float, Decimal)))
        elif op_str == 'Do':
            if operands and operands[0] in xobjects:
                xobj = xobjects[operands[0]]
                if isinstance(xobj, pikepdf.Stream) and xobj.get('/Subtype') == '/Form':
                    sub_resources = xobj.get('/Resources', resources)
                    try:
                        sub_cmds = list(pikepdf.parse_content_stream(xobj))
                        scan_content_stream(sub_cmds, sub_resources, page_num, overprint_data)
                    except Exception:
                        pass

        # Text operations
        elif op_str in ['Tj', "'", '"', 'TJ']:
            mode = state['text_render_mode']
            is_fill = (mode in [0, 2])
            is_stroke = (mode in [1, 2])

            is_dark_black = False
            k_percent = 100
            cs_type, spot_name = state['fill_cs']
            if cs_type == 'DeviceGray' and len(state['fill_color']) >= 1:
                gray_val = state['fill_color'][0]
                if gray_val <= 0.01:
                    is_dark_black = True
                    k_percent = 100
            elif cs_type == 'DeviceCMYK' and len(state['fill_color']) >= 4:
                c, m, y, k = state['fill_color'][:4]
                if c <= 0.05 and m <= 0.05 and y <= 0.05 and k >= 0.99:
                    is_dark_black = True
                    k_percent = 100

            # Solo evaluar sobreimpresion si hay texto visible real en negro puro 100% K
            if is_dark_black and is_fill and _has_visible_text(op_str, operands):
                if state['op']:
                    overprint_data["black_text_overprint"] += 1
                    overprint_data["black_100_overprint"] += 1
                else:
                    overprint_data["black_text_knockout"] += 1
                    overprint_data["black_100_knockout"] += 1
                    inc_type = "BLACK_TEXT_KNOCKOUT_100"
                    inc_title = "Texto 100% K en calado (knockout)"
                    inc_msg = f"Texto en negro puro 100% K sin sobreimpresión en pág {page_num}. Debe sobreimprimir para evitar filetes blancos."

                    # Registrar maximo 1 incidencia por tipo y pagina
                    if not any(inc["page"] == page_num and inc["type"] == inc_type for inc in overprint_data["incidents"]):
                        overprint_data["incidents"].append({
                            "page": page_num,
                            "type": inc_type,
                            "severity": "WARNING",
                            "category": "Sobreimpresión",
                            "title": inc_title,
                            "message": inc_msg
                        })

            # Comprobar texto blanco en sobreimpresión (Error Crítico: desaparece en plancha)
            if not spot_name and _has_visible_text(op_str, operands):
                is_white_fill = is_fill and is_fill_color_white(cs_type, state['fill_color'])
                stroke_cs_type, stroke_spot = state['stroke_cs']
                is_white_stroke = is_stroke and not stroke_spot and is_stroke_color_white(stroke_cs_type, state['stroke_color'])
                if (is_white_fill and state['op']) or (is_white_stroke and state['OP']):
                    overprint_data["white_overprint"] += 1
                    if not any(inc["page"] == page_num and inc["type"] == "WHITE_OVERPRINT" for inc in overprint_data["incidents"]):
                        overprint_data["incidents"].append({
                            "page": page_num,
                            "type": "WHITE_OVERPRINT",
                            "severity": "ERROR",
                            "category": "Sobreimpresión",
                            "title": "Texto blanco en sobreimpresión (desaparecerá en plancha)",
                            "message": f"Texto blanco configurado para sobreimprimir en pág {page_num}. En plancha se borrará por completo al no calar las tintas inferiores."
                        })

            if spot_name:
                check_spot(spot_name, state['op'] if is_fill else state['OP'], page_num, overprint_data, "texto")

            # Comprobar negro enriquecido en texto pequeño (< 12 pt)
            # En imprenta offset el negro enriquecido en cuerpo pequeño provoca halos por desajuste de registro
            if is_fill and not spot_name and _has_visible_text(op_str, operands):
                font_pt = state.get('font_size', 0.0) * state.get('ctm_scale', 1.0)
                is_small = 0 < font_pt < 12.0
                cs_type_f, _ = state['fill_cs']
                if is_small and cs_type_f == 'DeviceCMYK' and len(state['fill_color']) >= 4:
                    fc, fm, fy, fk = state['fill_color'][:4]
                    # Negro enriquecido = K > 0 pero también hay CMY significativo (> 5%)
                    is_rich_black = fk > 0.3 and (fc > 0.05 or fm > 0.05 or fy > 0.05)
                    if is_rich_black:
                        overprint_data["rich_black_small_text"] += 1
                        if not any(inc["page"] == page_num and inc["type"] == "RICH_BLACK_SMALL_TEXT" for inc in overprint_data["incidents"]):
                            overprint_data["incidents"].append({
                                "page": page_num,
                                "type": "RICH_BLACK_SMALL_TEXT",
                                "severity": "WARNING",
                                "category": "Color",
                                "title": f"Texto pequeño ({font_pt:.1f} pt) en negro enriquecido",
                                "message": f"Texto de {font_pt:.1f} pt con negro enriquecido (C:{int(fc*100)}% M:{int(fm*100)}% Y:{int(fy*100)}% K:{int(fk*100)}%) en pág {page_num}. En texto < 12 pt el negro enriquecido provoca halos de color por desajuste de registro. Debe usarse negro puro 0/0/0/100."
                            })

        # Vector fills
        elif op_str in ['f', 'F', 'f*', 'b', 'b*', 'B', 'B*']:
            cs_type, spot_name = state['fill_cs']
            if spot_name:
                check_spot(spot_name, state['op'], page_num, overprint_data, "relleno")
            elif state['op'] and is_fill_color_white(cs_type, state['fill_color']):
                overprint_data["white_overprint"] += 1
                if not any(inc["page"] == page_num and inc["type"] == "WHITE_OVERPRINT" for inc in overprint_data["incidents"]):
                    overprint_data["incidents"].append({
                        "page": page_num,
                        "type": "WHITE_OVERPRINT",
                        "severity": "ERROR",
                        "category": "Sobreimpresión",
                        "title": "Vector blanco en sobreimpresión (desaparecerá en plancha)",
                        "message": f"Relleno vectorial blanco con sobreimpresión activa en pág {page_num}. En plancha se borrará por completo."
                    })

        # Vector strokes
        elif op_str in ['s', 'S', 'b', 'b*', 'B', 'B*']:
            cs_type, spot_name = state['stroke_cs']
            if spot_name:
                check_spot(spot_name, state['OP'], page_num, overprint_data, "trazo")
            elif state['OP'] and is_stroke_color_white(cs_type, state['stroke_color']):
                overprint_data["white_overprint"] += 1
                if not any(inc["page"] == page_num and inc["type"] == "WHITE_OVERPRINT" for inc in overprint_data["incidents"]):
                    overprint_data["incidents"].append({
                        "page": page_num,
                        "type": "WHITE_OVERPRINT",
                        "severity": "ERROR",
                        "category": "Sobreimpresión",
                        "title": "Trazo blanco en sobreimpresión (desaparecerá en plancha)",
                        "message": f"Línea o trazo blanco con sobreimpresión activa en pág {page_num}. Desaparecerá en la impresión."
                    })

            # Comprobar filetes demasiado finos (< 0.25 pt / hairline)
            lw = state.get('line_width', 1.0)
            ctm = state.get('ctm_scale', 1.0)
            effective_lw = lw * ctm if ctm > 0 else lw
            if 0.0 <= effective_lw < 0.25:
                overprint_data["hairlines_count"] = overprint_data.get("hairlines_count", 0) + 1
                if not any(inc["page"] == page_num and inc["type"] == "HAIRLINE_DETECTED" for inc in overprint_data["incidents"]):
                    overprint_data["incidents"].append({
                        "page": page_num,
                        "type": "HAIRLINE_DETECTED",
                        "severity": "WARNING",
                        "category": "Trazos y Geometría",
                        "title": "Filetes demasiado finos (< 0,25 pt)",
                        "message": f"Se detectan trazos con grosor inferior a 0,25 pt ({effective_lw:.2f} pt) en pág {page_num}. En plancha CTP o imprenta pueden romperse o no imprimirse.",
                        "can_autofix": True,
                    })

def check_spot(spot_name, is_overprinting, page_num, overprint_data, context="objeto"):
    if is_varnish_name(spot_name):
        if is_overprinting:
            overprint_data["varnish_overprint"] += 1
        else:
            overprint_data["varnish_knockout"] += 1
            overprint_data["incidents"].append({
                "page": page_num,
                "type": "VARNISH_KNOCKOUT",
                "severity": "ERROR",
                "category": "Sobreimpresión",
                "title": f"Barniz/Acabado '{spot_name}' en calado",
                "message": f"El barniz o capa técnica '{spot_name}' ({context}) no sobreimprime. ¡Borrará la impresión subyacente!"
            })
    elif is_pantone_name(spot_name):
        if is_overprinting:
            overprint_data["pantone_overprint"] += 1
            overprint_data["incidents"].append({
                "page": page_num,
                "type": "PANTONE_OVERPRINT",
                "severity": "WARNING",
                "category": "Sobreimpresión",
                "title": f"Color Pantone '{spot_name}' sobreimprimiendo",
                "message": f"El color directo '{spot_name}' ({context}) sobreimprime sobre tintas inferiores, lo que puede alterar su tono real."
            })
        else:
            overprint_data["pantone_knockout"] += 1


def is_color_white(color):
    """
    Checks if a fill color is white/neutral/empty.
    In prepress, a white background does not require physical bleed.
    """
    if color is None:
        return True
    if isinstance(color, (int, float)):
        return abs(color - 1.0) < 0.02
    if isinstance(color, (list, tuple)):
        if len(color) == 1:
            return abs(color[0] - 1.0) < 0.02
        elif len(color) == 3:
            return all(abs(c - 1.0) < 0.02 for c in color)
        elif len(color) == 4:
            return all(abs(c) < 0.02 for c in color)
    return False


def detect_page_edge_elements(page, tol_pt=2.83):
    """
    Detects whether a PDF page contains images or non-white vector fills/backgrounds
    that touch or extend beyond the TrimBox edges (a ras de página / bleeding).
    tol_pt = 2.83 pt corresponds to ~1 mm tolerance.
    Calculates extension (mm) beyond TrimBox on each touching edge.
    """
    trim = page.trimbox
    if trim.width <= 0 or trim.height <= 0:
        trim = page.mediabox

    edge_elements = []

    # 1. Raster images
    for img in page.get_images(full=True):
        xref = img[0]
        for r in page.get_image_rects(xref):
            if r.width < 5 or r.height < 5:
                continue
            touches_left = (r.x0 <= trim.x0 + tol_pt and r.x1 > trim.x0)
            touches_top = (r.y0 <= trim.y0 + tol_pt and r.y1 > trim.y0)
            touches_right = (r.x1 >= trim.x1 - tol_pt and r.x0 < trim.x1)
            touches_bottom = (r.y1 >= trim.y1 - tol_pt and r.y0 < trim.y1)
            if touches_left or touches_top or touches_right or touches_bottom:
                ext_l = (trim.x0 - r.x0) * 25.4 / 72.0 if touches_left else None
                ext_t = (trim.y0 - r.y0) * 25.4 / 72.0 if touches_top else None
                ext_r = (r.x1 - trim.x1) * 25.4 / 72.0 if touches_right else None
                ext_b = (r.y1 - trim.y1) * 25.4 / 72.0 if touches_bottom else None
                exts = [e for e in [ext_l, ext_t, ext_r, ext_b] if e is not None]
                min_ext = min(exts) if exts else 0.0
                edge_elements.append({
                    "type": "image",
                    "xref": xref,
                    "rect": [round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)],
                    "min_ext": max(0.0, min_ext),
                    "touches": {
                        "left": touches_left,
                        "top": touches_top,
                        "right": touches_right,
                        "bottom": touches_bottom
                    },
                    "exts": {
                        "left": ext_l,
                        "top": ext_t,
                        "right": ext_r,
                        "bottom": ext_b
                    }
                })

    # 2. Vector drawings / fills / backgrounds
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []

    for d in drawings:
        fill_color = d.get("fill")
        if fill_color is None or is_color_white(fill_color):
            continue
        r = d.get("rect")
        if not r or r.width < 5 or r.height < 5:
            continue
        touches_left = (r.x0 <= trim.x0 + tol_pt and r.x1 > trim.x0)
        touches_top = (r.y0 <= trim.y0 + tol_pt and r.y1 > trim.y0)
        touches_right = (r.x1 >= trim.x1 - tol_pt and r.x0 < trim.x1)
        touches_bottom = (r.y1 >= trim.y1 - tol_pt and r.y0 < trim.y1)
        if touches_left or touches_top or touches_right or touches_bottom:
            ext_l = (trim.x0 - r.x0) * 25.4 / 72.0 if touches_left else None
            ext_t = (trim.y0 - r.y0) * 25.4 / 72.0 if touches_top else None
            ext_r = (r.x1 - trim.x1) * 25.4 / 72.0 if touches_right else None
            ext_b = (r.y1 - trim.y1) * 25.4 / 72.0 if touches_bottom else None
            exts = [e for e in [ext_l, ext_t, ext_r, ext_b] if e is not None]
            min_ext = min(exts) if exts else 0.0
            edge_elements.append({
                "type": "vector_fill",
                "color": fill_color,
                "rect": [round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)],
                "min_ext": max(0.0, min_ext),
                "touches": {
                    "left": touches_left,
                    "top": touches_top,
                    "right": touches_right,
                    "bottom": touches_bottom
                },
                "exts": {
                    "left": ext_l,
                    "top": ext_t,
                    "right": ext_r,
                    "bottom": ext_b
                }
            })

    return edge_elements


class IntelliPrintEngine:
    def __init__(self):
        self.spellchecker = PrepressSpellChecker()

    def run_preflight(self, pdf_path, profile_id="OFFSET_300", icc_choice="preserve", selected_icc=None):
        findings = []
        rules_evaluated = {}

        # 1. Target Profile Criteria (Dinámico desde profile_manager)
        try:
            from profile_manager import get_profile_by_id
            prof = get_profile_by_id(profile_id)
        except Exception:
            prof = {}

        target_dpi = prof.get("target_dpi", 300)
        req_family = prof.get("color_family", "CMYK")
        min_bleed_req_mm = prof.get("min_bleed_mm", 3.0)
        requires_bleed = min_bleed_req_mm > 0.5
        max_tac_limit = prof.get("max_tac", 300)
        min_hairline_threshold = prof.get("min_hairline_pt", 0.25)
        allow_spot_colors = prof.get("allow_spot_colors", True)
        require_fonts_embedded = prof.get("require_fonts_embedded", True)

        # Inspect original OutputIntent of uploaded PDF before applying any custom choices
        original_icc_info = detect_pdf_output_intent(pdf_path)

        # Apply ICC profile to PDF if user chose a custom profile from catalog/folder
        applied_icc_info = None
        if icc_choice == "custom_selection" and selected_icc:
            applied_icc_info = apply_icc_to_pdf(pdf_path, selected_icc)

        # Open with PyMuPDF
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            return {
                "technical_result": "fail",
                "error": f"No se pudo abrir el documento PDF: {e}",
                "findings": []
            }

        page_count = len(doc)
        total_images = 0
        low_res_images = 0
        non_cmyk_images = 0

        # Boxes, Bleed and Edge-content inspection (per page)
        pages_requiring_bleed = 0
        pages_failing_bleed = 0
        min_detected_bleed = 999.0
        has_any_bleed_req = False

        for p_idx in range(page_count):
            page = doc[p_idx]
            trimbox = page.trimbox
            mediabox = page.mediabox
            bleedbox = page.bleedbox

            if trimbox.width <= 0 or trimbox.height <= 0:
                trimbox = mediabox

            # Has explicit trim distinct from mediabox (e.g. crop marks or PDF/X trim)
            has_explicit_trim = (trimbox != mediabox and trimbox.width > 0 and trimbox.height > 0)
            # Has explicit bleedbox distinct from trimbox
            has_explicit_bleedbox = (bleedbox != trimbox and bleedbox.width > 0 and bleedbox.height > 0)

            # Box Bleed measurement (between TrimBox and BleedBox)
            if has_explicit_trim and has_explicit_bleedbox:
                b_top = max(0.0, (trimbox.y0 - bleedbox.y0) * 25.4 / 72.0)
                b_bottom = max(0.0, (bleedbox.y1 - trimbox.y1) * 25.4 / 72.0)
                b_left = max(0.0, (trimbox.x0 - bleedbox.x0) * 25.4 / 72.0)
                b_right = max(0.0, (bleedbox.x1 - trimbox.x1) * 25.4 / 72.0)
                box_bleed_mm = round(min(b_top, b_bottom, b_left, b_right), 1)
            else:
                box_bleed_mm = 0.0

            edge_elements = detect_page_edge_elements(page)
            page_needs_bleed = (len(edge_elements) > 0)

            if requires_bleed:
                if page_needs_bleed:
                    has_any_bleed_req = True
                    pages_requiring_bleed += 1

                    # Check each edge of TrimBox where elements reach
                    left_exts = [e["exts"]["left"] for e in edge_elements if e["exts"]["left"] is not None]
                    top_exts = [e["exts"]["top"] for e in edge_elements if e["exts"]["top"] is not None]
                    right_exts = [e["exts"]["right"] for e in edge_elements if e["exts"]["right"] is not None]
                    bottom_exts = [e["exts"]["bottom"] for e in edge_elements if e["exts"]["bottom"] is not None]

                    edges_checked = []
                    if left_exts:   edges_checked.append(('izquierdo', max(left_exts)))
                    if top_exts:    edges_checked.append(('superior',  max(top_exts)))
                    if right_exts:  edges_checked.append(('derecho',   max(right_exts)))
                    if bottom_exts: edges_checked.append(('inferior',  max(bottom_exts)))

                    # 1. Structural check: does PDF define BleedBox and TrimBox?
                    if has_explicit_trim and not has_explicit_bleedbox:
                        pages_failing_bleed += 1
                        min_detected_bleed = min(min_detected_bleed, 0.0)
                        findings.append({
                            "page": p_idx + 1,
                            "rule_id": "BLEED_GEOMETRY_3MM",
                            "severity": "ERROR",
                            "category": "Geometría",
                            "title": f"Sangrado insuficiente en pág {p_idx+1} (0.0 mm)",
                            "message": f"La página {p_idx+1} contiene elementos al corte y marcas de corte, pero el PDF carece de BleedBox (0.0 mm configurados, se requieren 3.0 mm)."
                        })
                    elif not has_explicit_trim:
                        pages_failing_bleed += 1
                        min_detected_bleed = min(min_detected_bleed, 0.0)
                        findings.append({
                            "page": p_idx + 1,
                            "rule_id": "BLEED_GEOMETRY_3MM",
                            "severity": "ERROR",
                            "category": "Geometría",
                            "title": f"Sangrado insuficiente en pág {p_idx+1} (0.0 mm)",
                            "message": f"La página {p_idx+1} contiene elementos al corte pero el documento no define TrimBox ni sangrado exterior de 3.0 mm."
                        })
                    else:
                        # 2. Per-edge content artwork check
                        failing_edges = []
                        page_eff_bleed = box_bleed_mm
                        bleed_thresh = max(0.5, min_bleed_req_mm - 0.5)
                        for edge_name, max_ext in edges_checked:
                            eff = round(max(0.0, max_ext), 1)
                            page_eff_bleed = min(page_eff_bleed, eff)
                            if eff < bleed_thresh:
                                failing_edges.append((edge_name, eff))

                        min_detected_bleed = min(min_detected_bleed, page_eff_bleed)

                        if failing_edges:
                            pages_failing_bleed += 1
                            desc = ', '.join([f'{name} ({ext} mm)' for name, ext in failing_edges])
                            findings.append({
                                "page": p_idx + 1,
                                "rule_id": "BLEED_GEOMETRY_3MM",
                                "severity": "ERROR",
                                "category": "Geometría",
                                "title": f"Sangrado insuficiente en pág {p_idx+1} ({page_eff_bleed} mm en borde {failing_edges[0][0]})",
                                "message": f"La página {p_idx+1} contiene elementos a ras de corte que no alcanzan los {min_bleed_req_mm:.1f} mm exigidos por el perfil en borde: {desc}."
                            })

        if requires_bleed:
            if pages_failing_bleed == 0 and has_any_bleed_req:
                rules_evaluated["BLEED_GEOMETRY_3MM"] = "PASS"
            elif not has_any_bleed_req:
                rules_evaluated["BLEED_GEOMETRY_3MM"] = "NOT_APPLICABLE"
            else:
                rules_evaluated["BLEED_GEOMETRY_3MM"] = "FAIL"

        # Images & Resolution inspection
        images_inventory = []
        for p_idx in range(page_count):
            page = doc[p_idx]
            img_list = page.get_images(full=True)
            total_images += len(img_list)

            for i_idx, img in enumerate(img_list):
                xref = img[0]
                base_img = doc.extract_image(xref)
                if not base_img:
                    continue

                cs = base_img.get("colorspace", "Desconocido")
                width_px = base_img.get("width", 0)
                height_px = base_img.get("height", 0)

                rects = page.get_image_rects(xref)
                dpi_x, dpi_y = 0, 0
                effective_dpi = 0
                placed_w_mm, placed_h_mm = 0.0, 0.0
                if rects and rects[0].width > 0 and rects[0].height > 0:
                    r = rects[0]
                    dpi_x = round(width_px / (r.width / 72.0))
                    dpi_y = round(height_px / (r.height / 72.0))
                    effective_dpi = round((dpi_x + dpi_y) / 2)
                    placed_w_mm = round(r.width * 25.4 / 72.0, 1)
                    placed_h_mm = round(r.height * 25.4 / 72.0, 1)

                # Color check for images
                is_cmyk = (cs == 4 or "CMYK" in str(cs).upper())
                is_gray = (cs == 1 or "GRAY" in str(cs).upper() or "GRIS" in str(cs).upper())
                is_rgb = (cs == 3 or "RGB" in str(cs).upper())

                CS_NAMES = {1: "Escala de grises", 2: "Calcomp", 3: "RGB", 4: "CMYK"}
                cs_label = CS_NAMES.get(cs, str(cs)) if isinstance(cs, int) else str(cs)
                if is_cmyk:
                    cs_label = "CMYK"
                elif is_rgb:
                    cs_label = "RGB"
                elif is_gray:
                    cs_label = "Escala de grises"

                dpi_desc = f"{effective_dpi} ppp" if effective_dpi > 0 else "Resolución N/D"

                # Check Resolution
                if effective_dpi > 0 and effective_dpi < target_dpi:
                    low_res_images += 1
                    findings.append({
                        "page": p_idx + 1,
                        "rule_id": "PRINT_IMAGE_EFFECTIVE_PPI",
                        "severity": "ERROR" if (requires_bleed and effective_dpi < 150) else "WARNING",
                        "category": "Imágenes",
                        "title": f"Resolución insuficiente ({effective_dpi} ppp · {cs_label})",
                        "message": f"Imagen {i_idx+1} en pág {p_idx+1}: espacio {cs_label}, resolución efectiva de {effective_dpi} ppp ({width_px} × {height_px} px, tamaño colocado: {placed_w_mm} × {placed_h_mm} mm). El perfil {profile_id} exige un mínimo de {target_dpi} ppp."
                    })

                # Color mode warning for images (e.g. RGB in Offset/Digital, or CMYK in Web/Screen)
                if req_family == "CMYK" and not is_cmyk and not is_gray:
                    non_cmyk_images += 1
                    findings.append({
                        "page": p_idx + 1,
                        "rule_id": "SOURCE_COLOR_DIAGNOSTIC",
                        "severity": "WARNING",
                        "category": "Color",
                        "title": f"Imagen en modo {cs_label} · {dpi_desc} (requiere CMYK)",
                        "message": f"Imagen {i_idx+1} en pág {p_idx+1}: espacio de color {cs_label}, resolución efectiva {dpi_desc} ({width_px} × {height_px} px, tamaño colocado: {placed_w_mm} × {placed_h_mm} mm). El perfil {profile_id} exige imágenes CMYK. Se admite conversión gestionada pero debe verificarse su apariencia en destino."
                    })
                elif req_family == "RGB" and is_cmyk:
                    findings.append({
                        "page": p_idx + 1,
                        "rule_id": "SOURCE_COLOR_DIAGNOSTIC",
                        "severity": "WARNING",
                        "category": "Color",
                        "title": f"Imagen en modo CMYK · {dpi_desc} (se recomienda sRGB)",
                        "message": f"Imagen {i_idx+1} en pág {p_idx+1}: espacio de color CMYK. El perfil {profile_id} está optimizado para web y pantallas (sRGB); se recomienda sRGB para evitar colores apagados en navegadores y dispositivos móviles."
                    })

                # Register full image inventory entry
                images_inventory.append({
                    "page": p_idx + 1,
                    "index": i_idx + 1,
                    "xref": xref,
                    "colorspace": cs_label,
                    "effective_dpi": effective_dpi,
                    "width_px": width_px,
                    "height_px": height_px,
                    "placed_mm": f"{placed_w_mm} × {placed_h_mm} mm" if placed_w_mm > 0 else "N/D",
                    "is_cmyk": is_cmyk,
                    "is_rgb": is_rgb,
                    "is_gray": is_gray
                })

        # Font Embedding Inspection
        fonts_found = []
        for p_idx in range(page_count):
            page = doc[p_idx]
            for f in page.get_fonts():
                font_name = f[3]
                is_embedded = (f[1] not in ("", "n/a", None))
                fonts_found.append({"name": font_name, "embedded": is_embedded, "page": p_idx + 1})
                if not is_embedded:
                    findings.append({
                        "page": p_idx + 1,
                        "rule_id": "USED_FONTS_EMBEDDED",
                        "severity": "ERROR",
                        "category": "Tipografías",
                        "title": f"Fuente no incrustada: {font_name}",
                        "message": f"La fuente '{font_name}' no está incrustada en el PDF. Puede sustituirse o corromperse al imprimir."
                    })

        # OutputIntent & Document Color
        output_intent_info = {"has_output_intent": False, "identifier": "No declarado"}
        overprint_data = {
            "black_100_overprint": 0,
            "black_100_knockout": 0,
            "dark_80_overprint": 0,
            "dark_80_knockout": 0,
            "black_text_overprint": 0,
            "black_text_knockout": 0,
            "white_overprint": 0,
            "rich_black_small_text": 0,
            "varnish_overprint": 0,
            "varnish_knockout": 0,
            "pantone_overprint": 0,
            "pantone_knockout": 0,
            "hairlines_count": 0,
            "incidents": []
        }

        spot_colors_detected = []
        try:
            pike_doc = pikepdf.open(pdf_path)
            output_intent_info = detect_pdf_output_intent(pike_doc)
            spot_colors_detected = extract_pdf_spot_colors(pike_doc)
            
            # Run overprint & spot check
            for p_idx, p_page in enumerate(pike_doc.pages, 1):
                cmds = list(pikepdf.parse_content_stream(p_page))
                scan_content_stream(cmds, p_page.get('/Resources'), p_idx, overprint_data)
            pike_doc.close()
        except Exception:
            pass

        # If custom ICC was applied, ensure output_intent_info reflects it
        if applied_icc_info and applied_icc_info.get("applied"):
            output_intent_info = applied_icc_info

        # Check Output Intent requirements
        if req_family == "CMYK":
            if not output_intent_info["has_output_intent"] or output_intent_info["detected_family"] != "CMYK":
                findings.append({
                    "page": 1,
                    "rule_id": "DOCUMENT_OUTPUT_ICC",
                    "severity": "ERROR",
                    "category": "Color",
                    "title": "ICC de salida CMYK ausente o no detectado",
                    "message": f"El perfil {profile_id} exige un OutputIntent documental CMYK válido incrustado."
                })
        elif req_family == "RGB":
            if not output_intent_info["has_output_intent"] or output_intent_info["detected_family"] != "RGB":
                findings.append({
                    "page": 1,
                    "rule_id": "DOCUMENT_OUTPUT_ICC",
                    "severity": "WARNING",
                    "category": "Color",
                    "title": "ICC de salida RGB ausente",
                    "message": "Se recomienda declarar un perfil sRGB para garantizar reproducción uniforme en pantalla."
                })

        # Merge overprint & geometry incidents
        for inc in overprint_data["incidents"]:
            finding_dict = {
                "page": inc["page"],
                "rule_id": inc["type"],
                "severity": inc["severity"],
                "category": inc["category"],
                "title": inc["title"],
                "message": inc["message"]
            }
            if inc.get("can_autofix"):
                finding_dict["can_autofix"] = True
            findings.append(finding_dict)

        # Run Spellchecker
        spell_suggestions = self.spellchecker.check_pdf_text(doc)

        doc.close()

        # Compute Technical Result
        has_errors = any(f["severity"] == "ERROR" for f in findings)
        has_warnings = any(f["severity"] == "WARNING" for f in findings)
        
        if has_errors:
            tech_status = "FAIL"
            tech_label = "NO CUMPLE"
        elif has_warnings:
            tech_status = "PASS_WITH_WARNINGS"
            tech_label = "CUMPLE CON AVISOS"
        else:
            tech_status = "PASS"
            tech_label = "CUMPLE"

        content_status = "PENDING_REVIEW" if spell_suggestions else "RESOLVED"
        content_label = f"Revisión editorial pendiente ({len(spell_suggestions)} sugerencias)" if spell_suggestions else "Sin erratas detectadas"

        bleed_status = "NOT_REQUIRED" if pages_requiring_bleed == 0 else ("PASS" if pages_failing_bleed == 0 else "FAIL")
        if pages_requiring_bleed == 0:
            bleed_note = "No requerida (márgenes blancos, sin elementos al corte)"
            detected_bleed_val = 0.0
        elif pages_failing_bleed == 0:
            detected_bleed_val = round(min_detected_bleed if min_detected_bleed < 990 else 3.0, 1)
            bleed_note = f"{pages_requiring_bleed} pág(s) con elementos al corte: {detected_bleed_val} mm OK"
        else:
            detected_bleed_val = round(min_detected_bleed if min_detected_bleed < 990 else 0.0, 1)
            bleed_note = f"{pages_failing_bleed} pág(s) con elementos al corte sin 3 mm de sangre ({detected_bleed_val} mm)"

        return {
            "job_summary": {
                "profile_id": profile_id,
                "target_dpi": target_dpi,
                "min_bleed_req_mm": min_bleed_req_mm,
                "max_tac_limit": max_tac_limit,
                "min_hairline_threshold": min_hairline_threshold,
                "pages": page_count,
                "total_images": total_images,
                "low_res_images": low_res_images,
                "non_cmyk_images": non_cmyk_images,
                "images_inventory": images_inventory,
                "fonts_count": len(fonts_found),
                "bleed_detected_mm": detected_bleed_val,
                "pages_requiring_bleed": pages_requiring_bleed,
                "pages_failing_bleed": pages_failing_bleed,
                "bleed_status": bleed_status,
                "bleed_note": bleed_note,
                "original_icc_detected": original_icc_info,
                "icc_detected": output_intent_info,
                "icc_choice_applied": icc_choice,
                "selected_icc": selected_icc,
                "spot_colors": spot_colors_detected,
                "overprint_stats": {
                    "black_100_overprint": overprint_data.get("black_100_overprint", 0),
                    "black_100_knockout": overprint_data.get("black_100_knockout", 0),
                    "dark_80_overprint": overprint_data.get("dark_80_overprint", 0),
                    "dark_80_knockout": overprint_data.get("dark_80_knockout", 0),
                    "black_text_overprint": overprint_data["black_text_overprint"],
                    "black_text_knockout": overprint_data["black_text_knockout"],
                    "white_overprint": overprint_data.get("white_overprint", 0),
                    "rich_black_small_text": overprint_data.get("rich_black_small_text", 0),
                    "varnish_overprint": overprint_data["varnish_overprint"],
                    "varnish_knockout": overprint_data["varnish_knockout"],
                    "pantone_overprint": overprint_data["pantone_overprint"],
                    "pantone_knockout": overprint_data["pantone_knockout"]
                }
            },
            "triple_result": {
                "technical": {
                    "status": tech_status,
                    "label": tech_label,
                    "errors_count": sum(1 for f in findings if f["severity"] == "ERROR"),
                    "warnings_count": sum(1 for f in findings if f["severity"] == "WARNING")
                },
                "content": {
                    "status": content_status,
                    "label": content_label,
                    "suggestions_count": len(spell_suggestions)
                },
                "release": {
                    "status": "PENDING_AUTHORIZATION",
                    "label": "Pendiente de visto bueno del operario"
                }
            },
            "findings": findings,
            "spell_suggestions": spell_suggestions
        }

