"""
overprint_fixer.py
==================
Motor de corrección automática de sobreimpresión (auto-trapping) para IntelliPrint.

Módulos incluidos:
  1. apply_overprint_to_dark_text   – Auto-trapping de textos negros/oscuros (≥80% K)
  2. apply_overprint_to_technical_inks – Sobreimpresión obligatoria de barnices/troqueles
  3. fix_white_overprint            – White Overprint Killer: corrige objetos blancos
                                      que sobreimprimen (desaparecerían en plancha)

Uso:
    result = apply_overprint_to_dark_text("input.pdf", "output.pdf")
    result = fix_white_overprint("input.pdf", "output.pdf")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union, Optional

import pikepdf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Umbrales de deteccion de "negro oscuro"
# ---------------------------------------------------------------------------
DARK_K_THRESHOLD = 0.80    # K minimo para considerar color oscuro (>= 80% K)
CMY_MAX = 0.05             # CMY maximo para que sea negro puro (no color compuesto)
GRAY_DARK_THRESHOLD = 0.20 # Para operador 'g': escala de grises <= este valor (<= 0.20 equivale a >= 80% K)


# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------

def _is_visible_text(op_str: str, operands: list) -> bool:
    """Verifica si la operacion de texto tiene caracteres visibles (no solo espacios)."""
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


def apply_overprint_to_dark_text(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    dark_k_threshold: float = DARK_K_THRESHOLD,
    cmy_max: float = CMY_MAX,
) -> dict:
    """
    Recorre todas las paginas del PDF e inyecta sobreimpresion automatica
    para textos negros oscuros en calado.

    Retorna dict con claves: success, pages_modified, text_ops_fixed, text_100_fixed, text_80_fixed, errors
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    errors: list[str] = []
    pages_modified = 0
    text_ops_fixed = 0
    text_100_fixed = 0
    text_80_fixed = 0

    try:
        pdf = pikepdf.open(str(pdf_path))
    except Exception as e:
        return {
            "success": False,
            "pages_modified": 0,
            "text_ops_fixed": 0,
            "text_100_fixed": 0,
            "text_80_fixed": 0,
            "errors": [f"No se pudo abrir el PDF: {e}"],
        }

    try:
        for page_num, page in enumerate(pdf.pages):
            try:
                n_fixed, n_100, n_80 = _fix_page(pdf, page, dark_k_threshold, cmy_max)
                if n_fixed > 0:
                    pages_modified += 1
                    text_ops_fixed += n_fixed
                    text_100_fixed += n_100
                    text_80_fixed += n_80
                    logger.info(
                        "[overprint_fixer] Pagina %d: %d ops (%d de 100%%, %d de 80%%)",
                        page_num + 1, n_fixed, n_100, n_80
                    )
            except Exception as e:
                msg = f"Error en pagina {page_num + 1}: {e}"
                logger.warning(msg)
                errors.append(msg)

        pdf.save(str(output_path))
        logger.info("[overprint_fixer] PDF guardado en: %s", output_path)

    except Exception as e:
        errors.append(f"Error al guardar el PDF: {e}")
        return {
            "success": False,
            "pages_modified": pages_modified,
            "text_ops_fixed": text_ops_fixed,
            "text_100_fixed": text_100_fixed,
            "text_80_fixed": text_80_fixed,
            "errors": errors,
        }
    finally:
        pdf.close()

    return {
        "success": True,
        "pages_modified": pages_modified,
        "text_ops_fixed": text_ops_fixed,
        "text_100_fixed": text_100_fixed,
        "text_80_fixed": text_80_fixed,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Procesado de una pagina
# ---------------------------------------------------------------------------

def _fix_page(pdf: pikepdf.Pdf, page: pikepdf.Page, dark_k_threshold: float, cmy_max: float) -> tuple[int, int, int]:
    """
    Inyecta /IP_OP y /IP_KO en la pagina segun el color de relleno activo.
    Devuelve (n_fixed, n_100, n_80).
    """
    # 1. Garantizar que la pagina tiene Resources.ExtGState
    _ensure_extgstate(page)

    # 2. Inyectar los dos estados graficos necesarios
    _inject_gs_entries(pdf, page)

    # 3. Parsear el flujo de contenido y reconstruirlo con las inserciones
    new_commands, n_fixed, n_100, n_80 = _process_content_stream(page, dark_k_threshold, cmy_max)

    if n_fixed == 0:
        return 0, 0, 0  # Nada que modificar

    # 4. Reemplazar el contenido de la pagina
    new_data = pikepdf.unparse_content_stream(new_commands)
    page.Contents = pikepdf.Stream(pdf, new_data)

    return n_fixed, n_100, n_80


def _ensure_extgstate(page: pikepdf.Page) -> None:
    """Garantiza que page.Resources.ExtGState existe."""
    res = page.obj.get("/Resources")
    if res is None:
        page.obj["/Resources"] = pikepdf.Dictionary()
        res = page.obj["/Resources"]
    if "/ExtGState" not in res:
        res["/ExtGState"] = pikepdf.Dictionary()


def _inject_gs_entries(pdf: pikepdf.Pdf, page: pikepdf.Page) -> None:
    """Anade /IP_OP (overprint) y /IP_KO (knockout) si no existen ya."""
    extgs = page.obj["/Resources"]["/ExtGState"]

    if "/IP_OP" not in extgs:
        extgs["/IP_OP"] = pikepdf.Dictionary(
            op=pikepdf.Object.parse(b"true"),
            OP=pikepdf.Object.parse(b"true"),
            OPM=pikepdf.Object.parse(b"1"),
            Type=pikepdf.Name("/ExtGState"),
        )

    if "/IP_KO" not in extgs:
        extgs["/IP_KO"] = pikepdf.Dictionary(
            op=pikepdf.Object.parse(b"false"),
            OP=pikepdf.Object.parse(b"false"),
            OPM=pikepdf.Object.parse(b"0"),
            Type=pikepdf.Name("/ExtGState"),
        )


# ---------------------------------------------------------------------------
# Parser del flujo de contenido
# ---------------------------------------------------------------------------

def _process_content_stream(
    page: pikepdf.Page,
    dark_k_threshold: float,
    cmy_max: float,
) -> tuple[list, int, int, int]:
    """
    Recorre los operadores del stream, rastreando color de relleno y estado
    de overprint, e inserta /IP_OP o /IP_KO donde sea necesario.

    Devuelve (new_commands, n_fixed, n_100, n_80).
    """
    # Estado de color de relleno inicial: por especificacion PDF el espacio por defecto es DeviceGray 0.0
    fill_c = fill_m = fill_y = fill_k = 0.0
    fill_gray: float | None = 0.0
    color_space = "gray"  # 'cmyk', 'gray', 'rgb', 'other'

    # Estado de overprint actual (best-effort tracking)
    currently_overprinting = False

    # ExtGState dict de la pagina para resolver operadores 'gs' existentes
    extgs_dict = _get_extgstate_dict(page)

    new_commands: list = []
    n_fixed = 0
    n_100 = 0
    n_80 = 0

    try:
        raw_commands = pikepdf.parse_content_stream(page)
    except Exception as e:
        logger.warning("[overprint_fixer] No se pudo parsear el stream: %s", e)
        return [], 0, 0, 0

    for operands, op in raw_commands:
        op_str = str(op)

        # ---- Rastrear color de relleno ----
        if op_str == "k":
            # CMYK fill: C M Y K k
            if len(operands) == 4:
                fill_c = float(operands[0])
                fill_m = float(operands[1])
                fill_y = float(operands[2])
                fill_k = float(operands[3])
                fill_gray = None
                color_space = "cmyk"

        elif op_str == "g":
            # Grayscale fill: gray g  (0=negro, 1=blanco)
            if len(operands) == 1:
                fill_gray = float(operands[0])
                color_space = "gray"

        elif op_str == "rg":
            # RGB fill → no es "negro oscuro" en nuestro umbral
            color_space = "rgb"
            fill_k = 0.0
            fill_gray = None

        elif op_str in ("sc", "scn"):
            # Color generico — sin CMYK claro, tratar como no-negro
            color_space = "other"
            fill_k = 0.0
            fill_gray = None

        elif op_str == "cs":
            # Cambio de espacio de color de relleno
            color_space = "other"
            fill_k = 0.0
            fill_gray = None

        # ---- Rastrear estado de overprint via 'gs' ----
        elif op_str == "gs":
            if len(operands) == 1:
                gs_name_clean = str(operands[0]).lstrip("/")
                gs_entry = extgs_dict.get(gs_name_clean)
                if gs_entry is not None:
                    # 'op' = fill overprint; 'OP' = stroke overprint
                    for key in ("/op", "/OP"):
                        if key in gs_entry:
                            val = gs_entry[key]
                            currently_overprinting = bool(val)
                            break

        # ---- Detectar operaciones de texto y corregir ----
        if op_str in ("Tj", "TJ", "'", '"'):
            has_text = _is_visible_text(op_str, operands)
            is_dark = has_text and _current_fill_is_dark(
                color_space, fill_c, fill_m, fill_y, fill_k, fill_gray,
                dark_k_threshold, cmy_max
            )

            if is_dark and not currently_overprinting:
                # Insertar gs /IP_OP antes del texto oscuro en calado
                new_commands.append(
                    ([pikepdf.Name("/IP_OP")], pikepdf.Operator("gs"))
                )
                currently_overprinting = True
                n_fixed += 1
                is_pure_100 = (
                    (color_space == "cmyk" and fill_k >= 0.99)
                    or (color_space == "gray" and fill_gray is not None and fill_gray <= 0.01)
                )
                if is_pure_100:
                    n_100 += 1
                else:
                    n_80 += 1

            elif not is_dark and currently_overprinting and has_text:
                # Restaurar calado antes de un texto no-oscuro visible
                new_commands.append(
                    ([pikepdf.Name("/IP_KO")], pikepdf.Operator("gs"))
                )
                currently_overprinting = False

        new_commands.append((operands, op))

    return new_commands, n_fixed, n_100, n_80


def _current_fill_is_dark(
    color_space: str,
    c: float, m: float, y: float, k: float,
    gray: float | None,
    dark_k_threshold: float,
    cmy_max: float,
) -> bool:
    """True si el color de relleno actual es oscuro (candidato a sobreimprimir)."""
    if color_space == "cmyk":
        return k >= dark_k_threshold and c <= cmy_max and m <= cmy_max and y <= cmy_max
    if color_space == "gray" and gray is not None:
        gray_thresh = 0.01 if dark_k_threshold >= 0.99 else GRAY_DARK_THRESHOLD
        return gray <= gray_thresh
    return False


def _get_extgstate_dict(page: pikepdf.Page) -> dict:
    """
    Extrae el diccionario ExtGState de la pagina como dict[str, pikepdf.Object]
    para facilitar la consulta de estados graficos existentes.
    """
    result: dict = {}
    try:
        res = page.obj.get("/Resources")
        if res is None:
            return result
        extgs = res.get("/ExtGState")
        if extgs is None:
            return result
        for key in extgs.keys():
            result[key.lstrip("/")] = extgs[key]
    except Exception as e:
        logger.warning("[overprint_fixer] No se pudo leer ExtGState: %s", e)
    return result


# ---------------------------------------------------------------------------
# White Overprint Killer – Elimina sobreimpresión en objetos blancos
# ---------------------------------------------------------------------------

def _is_white_color(color_space: str, fill_c: float, fill_m: float,
                    fill_y: float, fill_k: float, fill_gray: Optional[float],
                    fill_rgb: Optional[tuple]) -> bool:
    """True si el color actual es blanco (0% tinta)."""
    if color_space == "cmyk":
        return fill_c <= 0.01 and fill_m <= 0.01 and fill_y <= 0.01 and fill_k <= 0.01
    if color_space == "gray" and fill_gray is not None:
        return fill_gray >= 0.99
    if color_space == "rgb" and fill_rgb is not None:
        return all(c >= 0.98 for c in fill_rgb)
    return False


def fix_white_overprint(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
) -> dict:
    """
    White Overprint Killer: detecta objetos blancos (texto, vectores) con
    sobreimpresión activa y los fuerza a calado (knockout=True, op=False, OP=False).

    En preimpresión offset, un blanco con sobreimpresión activa se borra
    completamente en plancha porque el RIP no genera punto de tinta blanca:
    el objeto transparenta y deja ver el color de fondo impreso debajo.

    Retorna dict con claves:
        success: bool
        pages_modified: int
        objects_fixed: int
        errors: list[str]
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    errors: list[str] = []
    pages_modified = 0
    objects_fixed = 0

    try:
        pdf = pikepdf.open(str(pdf_path))
    except Exception as e:
        return {"success": False, "pages_modified": 0, "objects_fixed": 0,
                "errors": [f"No se pudo abrir el PDF: {e}"]}

    try:
        for page_num, page in enumerate(pdf.pages):
            try:
                n_fixed = _fix_page_white_overprint(pdf, page)
                if n_fixed > 0:
                    pages_modified += 1
                    objects_fixed += n_fixed
                    logger.info(
                        "[white_overprint_killer] Pág %d: %d objetos blancos corregidos a calado.",
                        page_num + 1, n_fixed
                    )
            except Exception as e:
                msg = f"Error en página {page_num + 1}: {e}"
                logger.warning(msg)
                errors.append(msg)

        pdf.save(str(output_path))
        logger.info("[white_overprint_killer] PDF guardado en: %s", output_path)

    except Exception as e:
        errors.append(f"Error al guardar el PDF: {e}")
        return {"success": False, "pages_modified": pages_modified,
                "objects_fixed": objects_fixed, "errors": errors}
    finally:
        pdf.close()

    return {
        "success": True,
        "pages_modified": pages_modified,
        "objects_fixed": objects_fixed,
        "errors": errors,
    }


def _fix_page_white_overprint(pdf: pikepdf.Pdf, page: pikepdf.Page) -> int:
    """
    Recorre el stream de la página e inyecta /IP_KO (knockout) antes de cualquier
    operación de dibujo que sea blanca y tenga sobreimpresión activa.
    Devuelve el número de objetos corregidos.
    """
    _ensure_extgstate(page)

    # Inyectar /IP_KO si no existe (estado gráfico de calado forzado)
    extgs = page.obj["/Resources"]["/ExtGState"]
    if "/IP_KO" not in extgs:
        extgs["/IP_KO"] = pikepdf.Dictionary(
            op=pikepdf.Object.parse(b"false"),
            OP=pikepdf.Object.parse(b"false"),
            OPM=pikepdf.Object.parse(b"0"),
            Type=pikepdf.Name("/ExtGState"),
        )

    extgs_dict = _get_extgstate_dict(page)

    try:
        raw_commands = pikepdf.parse_content_stream(page)
    except Exception as e:
        logger.warning("[white_overprint_killer] No se pudo parsear el stream: %s", e)
        return 0

    # Rastreo de estado de color y sobreimpresión
    color_space = "gray"
    fill_c = fill_m = fill_y = fill_k = 0.0
    fill_gray: Optional[float] = 0.0
    fill_rgb: Optional[tuple] = None
    currently_overprinting = False

    new_commands: list = []
    n_fixed = 0

    for operands, op in raw_commands:
        op_str = str(op)

        # Rastrear color de relleno
        if op_str == "k":
            if len(operands) == 4:
                fill_c, fill_m, fill_y, fill_k = (float(x) for x in operands)
                fill_gray = None
                fill_rgb = None
                color_space = "cmyk"
        elif op_str == "g":
            if len(operands) == 1:
                fill_gray = float(operands[0])
                fill_rgb = None
                color_space = "gray"
        elif op_str == "rg":
            if len(operands) == 3:
                fill_rgb = tuple(float(x) for x in operands)
                fill_gray = None
                color_space = "rgb"
        elif op_str in ("sc", "scn", "cs"):
            # Espacio genérico (spot, pattern…): no es blanco CMYK/gray/RGB claro
            color_space = "other"
            fill_gray = None
            fill_rgb = None

        # Rastrear estado de sobreimpresión vía gs
        elif op_str == "gs":
            if len(operands) == 1:
                gs_name = str(operands[0]).lstrip("/")
                gs_entry = extgs_dict.get(gs_name)
                if gs_entry is not None:
                    for key in ("/op", "/OP"):
                        if key in gs_entry:
                            currently_overprinting = bool(gs_entry[key])
                            break

        # Detectar dibujo blanco con sobreimpresión activa
        is_draw_op = op_str in (
            "f", "F", "f*", "b", "b*", "B", "B*",
            "s", "S", "Tj", "TJ", "'", '"'
        )

        if is_draw_op and currently_overprinting:
            is_white = _is_white_color(
                color_space, fill_c, fill_m, fill_y, fill_k, fill_gray, fill_rgb
            )
            if is_white:
                # Insertar /IP_KO para forzar calado antes del objeto blanco
                new_commands.append(
                    ([pikepdf.Name("/IP_KO")], pikepdf.Operator("gs"))
                )
                currently_overprinting = False
                n_fixed += 1

        new_commands.append((operands, op))

    if n_fixed == 0:
        return 0

    new_data = pikepdf.unparse_content_stream(new_commands)
    page.Contents = pikepdf.Stream(pdf, new_data)
    return n_fixed


# ---------------------------------------------------------------------------
# Corrección de Sobreimpresión para Tintas Técnicas (Barnices, Troqueles, UV)
# ---------------------------------------------------------------------------

VARNISH_KEYWORDS = [
    'barniz', 'varnish', 'laca', 'lacquer', 'uv', 'gloss', 'brillo',
    'mate', 'matt', 'acabado', 'dieline', 'troquel', 'stamping', 'corte'
]

def _is_technical_ink_name(name: str) -> bool:
    import re
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(name)).lower()
    return any(k in clean for k in VARNISH_KEYWORDS)


def apply_overprint_to_technical_inks(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    target_spots: Optional[list[str]] = None,
) -> dict:
    """
    Inyecta sobreimpresion obligatoria (/IP_OP) a las capas tecnicas (barnices,
    lacas, troqueles) que se encuentren en calado (knockout).

    Retorna dict con:
        success: bool
        pages_modified: int
        ops_fixed: int
        technical_spots_fixed: list[str]
        errors: list[str]
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    errors: list[str] = []
    pages_modified = 0
    ops_fixed = 0
    technical_spots_found = set()

    try:
        pdf = pikepdf.open(str(pdf_path))
    except Exception as e:
        return {
            "success": False,
            "pages_modified": 0,
            "ops_fixed": 0,
            "technical_spots_fixed": [],
            "errors": [f"No se pudo abrir el PDF: {e}"],
        }

    try:
        for page_num, page in enumerate(pdf.pages):
            try:
                n_fixed, spots = _fix_page_technical_inks(pdf, page, target_spots)
                if n_fixed > 0:
                    pages_modified += 1
                    ops_fixed += n_fixed
                    technical_spots_found.update(spots)
                    logger.info(
                        "[overprint_fixer] Pagina %d: %d operaciones de tintas tecnicas sobreimpresas: %s",
                        page_num + 1, n_fixed, spots
                    )
            except Exception as e:
                msg = f"Error en pagina {page_num + 1}: {e}"
                logger.warning(msg)
                errors.append(msg)

        pdf.save(str(output_path))
        logger.info("[overprint_fixer] PDF con barnices sobreimpresos guardado en: %s", output_path)

    except Exception as e:
        errors.append(f"Error al guardar el PDF: {e}")
        return {
            "success": False,
            "pages_modified": pages_modified,
            "ops_fixed": ops_fixed,
            "technical_spots_fixed": list(technical_spots_found),
            "errors": errors,
        }
    finally:
        pdf.close()

    return {
        "success": True,
        "pages_modified": pages_modified,
        "ops_fixed": ops_fixed,
        "technical_spots_fixed": list(technical_spots_found),
        "errors": errors,
    }


def _fix_page_technical_inks(
    pdf: pikepdf.Pdf,
    page: pikepdf.Page,
    target_spots: Optional[list[str]] = None
) -> tuple[int, list[str]]:
    """Inyecta /IP_OP en las operaciones con tintas tecnicas de la pagina."""
    res = page.obj.get('/Resources')
    if not res or '/ColorSpace' not in res:
        return 0, []

    cs_dict = res['/ColorSpace']
    tech_keys = {}  # cs_name -> spot_name

    for cs_key, cs_val in cs_dict.items():
        if not isinstance(cs_val, pikepdf.Array) or len(cs_val) < 2:
            continue
        cs_type = str(cs_val[0])
        if cs_type not in ('/Separation', '/DeviceN'):
            continue
        spot_name = str(cs_val[1]).lstrip('/')
        if target_spots is not None:
            if spot_name in target_spots:
                tech_keys[str(cs_key)] = spot_name
        else:
            if _is_technical_ink_name(spot_name):
                tech_keys[str(cs_key)] = spot_name

    if not tech_keys:
        return 0, []

    _ensure_extgstate(page)
    _inject_gs_entries(pdf, page)

    raw_cmds = pikepdf.parse_content_stream(page)
    new_cmds, n_fixed = _process_technical_stream(raw_cmds, tech_keys, page)

    if n_fixed == 0:
        return 0, list(tech_keys.values())

    page.Contents = pikepdf.Stream(pdf, pikepdf.unparse_content_stream(new_cmds))
    return n_fixed, list(tech_keys.values())


def _process_technical_stream(
    commands: list,
    tech_keys: dict[str, str],
    page: pikepdf.Page
) -> tuple[list, int]:
    """Recorre el stream e inyecta /IP_OP antes de pintar con tintas tecnicas."""
    extgs_dict = _get_extgstate_dict(page)
    new_commands = []
    n_fixed = 0

    fill_is_technical = False
    stroke_is_technical = False
    currently_overprinting = False

    for operands, op in commands:
        op_str = str(op)

        if op_str == 'cs':
            if operands and str(operands[0]) in tech_keys:
                fill_is_technical = True
            else:
                fill_is_technical = False
        elif op_str == 'CS':
            if operands and str(operands[0]) in tech_keys:
                stroke_is_technical = True
            else:
                stroke_is_technical = False
        elif op_str in ('g', 'rg', 'k'):
            fill_is_technical = False
        elif op_str in ('G', 'RG', 'K'):
            stroke_is_technical = False
        elif op_str == 'gs':
            if len(operands) == 1:
                gs_name_clean = str(operands[0]).lstrip("/")
                gs_entry = extgs_dict.get(gs_name_clean)
                if gs_entry is not None:
                    for key in ("/op", "/OP"):
                        if key in gs_entry:
                            val = gs_entry[key]
                            currently_overprinting = bool(val)
                            break

        # Operaciones de relleno vectorial o texto
        is_fill_draw = op_str in ('f', 'F', 'f*', 'b', 'b*', 'B', 'B*', 'Tj', 'TJ', "'", '"')
        is_stroke_draw = op_str in ('s', 'S', 'b', 'b*', 'B', 'B*')

        needs_op = (is_fill_draw and fill_is_technical) or (is_stroke_draw and stroke_is_technical)

        if needs_op and not currently_overprinting:
            new_commands.append(([pikepdf.Name('/IP_OP')], pikepdf.Operator('gs')))
            currently_overprinting = True
            n_fixed += 1
        elif not needs_op and (is_fill_draw or is_stroke_draw) and currently_overprinting and not fill_is_technical and not stroke_is_technical:
            # Restaurar knockout para no sobreimprimir objetos normales
            new_commands.append(([pikepdf.Name('/IP_KO')], pikepdf.Operator('gs')))
            currently_overprinting = False

        new_commands.append((operands, op))

    return new_commands, n_fixed

