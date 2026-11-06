"""
overprint_fixer.py
==================
Motor de corrección automática de sobreimpresión (auto-trapping) para IntelliPrint.

Detecta textos con relleno oscuro (K >= 0.70, CMY < 0.05) que están en calado
e inyecta estados graficos /IP_OP (overprint=True) antes de cada operacion de
texto afectada, y /IP_KO (overprint=False) al salir, para evitar filetes blancos
por desajuste de registro.

Uso:
    result = apply_overprint_to_dark_text("input.pdf", "output.pdf")
    # result = {"success": True, "pages_modified": 2, "text_ops_fixed": 7, "errors": []}
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import pikepdf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Umbrales de deteccion de "negro oscuro"
# ---------------------------------------------------------------------------
DARK_K_THRESHOLD = 0.70    # K minimo para considerar color oscuro
CMY_MAX = 0.05             # CMY maximo para que sea negro puro (no color compuesto)
GRAY_DARK_THRESHOLD = 0.30 # Para operador 'g': escala de grises <= este valor -> oscuro


# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------

def apply_overprint_to_dark_text(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    dark_k_threshold: float = DARK_K_THRESHOLD,
    cmy_max: float = CMY_MAX,
) -> dict:
    """
    Recorre todas las paginas del PDF e inyecta sobreimpresion automatica
    para textos negros oscuros en calado.

    Retorna dict con claves: success, pages_modified, text_ops_fixed, errors
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    errors: list[str] = []
    pages_modified = 0
    text_ops_fixed = 0

    try:
        pdf = pikepdf.open(str(pdf_path))
    except Exception as e:
        return {
            "success": False,
            "pages_modified": 0,
            "text_ops_fixed": 0,
            "errors": [f"No se pudo abrir el PDF: {e}"],
        }

    try:
        for page_num, page in enumerate(pdf.pages):
            try:
                n_fixed = _fix_page(pdf, page, dark_k_threshold, cmy_max)
                if n_fixed > 0:
                    pages_modified += 1
                    text_ops_fixed += n_fixed
                    logger.info(
                        "[overprint_fixer] Pagina %d: %d operaciones corregidas.",
                        page_num + 1, n_fixed
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
            "errors": errors,
        }
    finally:
        pdf.close()

    return {
        "success": True,
        "pages_modified": pages_modified,
        "text_ops_fixed": text_ops_fixed,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Procesado de una pagina
# ---------------------------------------------------------------------------

def _fix_page(pdf: pikepdf.Pdf, page: pikepdf.Page, dark_k_threshold: float, cmy_max: float) -> int:
    """
    Inyecta /IP_OP y /IP_KO en la pagina segun el color de relleno activo.
    Devuelve el numero de operaciones de texto que se corrigieron.
    """
    # 1. Garantizar que la pagina tiene Resources.ExtGState
    _ensure_extgstate(page)

    # 2. Inyectar los dos estados graficos necesarios
    _inject_gs_entries(pdf, page)

    # 3. Parsear el flujo de contenido y reconstruirlo con las inserciones
    new_commands, n_fixed = _process_content_stream(page, dark_k_threshold, cmy_max)

    if n_fixed == 0:
        return 0  # Nada que modificar

    # 4. Reemplazar el contenido de la pagina
    new_data = pikepdf.unparse_content_stream(new_commands)
    page.Contents = pikepdf.Stream(pdf, new_data)

    return n_fixed


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
) -> tuple[list, int]:
    """
    Recorre los operadores del stream, rastreando color de relleno y estado
    de overprint, e inserta /IP_OP o /IP_KO donde sea necesario.

    Devuelve (new_commands, n_fixed).
    """
    # Estado de color de relleno actual
    fill_c = fill_m = fill_y = fill_k = 0.0
    fill_gray: float | None = None
    color_space = "cmyk"  # 'cmyk', 'gray', 'rgb', 'other'

    # Estado de overprint actual (best-effort tracking)
    currently_overprinting = False

    # ExtGState dict de la pagina para resolver operadores 'gs' existentes
    extgs_dict = _get_extgstate_dict(page)

    new_commands: list = []
    n_fixed = 0

    try:
        raw_commands = pikepdf.parse_content_stream(page)
    except Exception as e:
        logger.warning("[overprint_fixer] No se pudo parsear el stream: %s", e)
        return [], 0

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
            is_dark = _current_fill_is_dark(
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

            elif not is_dark and currently_overprinting:
                # Restaurar calado antes del texto no-oscuro
                new_commands.append(
                    ([pikepdf.Name("/IP_KO")], pikepdf.Operator("gs"))
                )
                currently_overprinting = False

        new_commands.append((operands, op))

    return new_commands, n_fixed


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
        return gray <= GRAY_DARK_THRESHOLD
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
