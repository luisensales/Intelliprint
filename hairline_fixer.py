"""
hairline_fixer.py
=================
Motor de engrosamiento de líneas finas (Hairline Fixer) para IntelliPrint.
Ajusta filetes y trazos con grosor inferior a un umbral mínimo (p.ej. 0.25 pt / 0.088 mm)
elevándolos al grosor seguro para imprenta offset y digital (0.30 pt).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Union

import pikepdf

logger = logging.getLogger(__name__)

HAIRLINE_THRESHOLD = 0.25  # Grosor en pt por debajo del cual se considera hairline
SAFE_LINE_WIDTH = 0.30     # Grosor seguro mínimo en pt


def fix_hairlines(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
    hairline_threshold: float = HAIRLINE_THRESHOLD,
    target_width: float = SAFE_LINE_WIDTH,
) -> dict:
    """
    Recorre todas las páginas del PDF y engrosa trazos vectoriales inferiores
    a hairline_threshold elevándolos a target_width.

    Retorna:
        dict con claves: success, pages_modified, lines_fixed, errors
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    errors: list[str] = []
    pages_modified = 0
    lines_fixed = 0

    try:
        pdf = pikepdf.open(str(pdf_path), allow_overwriting_input=True)
    except Exception as e:
        return {
            "success": False,
            "pages_modified": 0,
            "lines_fixed": 0,
            "errors": [f"No se pudo abrir el PDF: {e}"],
        }

    try:
        for page_num, page in enumerate(pdf.pages):
            try:
                page_fixed = _fix_page_stream_hairlines(pdf, page, hairline_threshold, target_width)

                # También revisar Form XObjects en los recursos de la página
                xobj_fixed = _fix_page_xobjects_hairlines(pdf, page, hairline_threshold, target_width)

                total_page_fixed = page_fixed + xobj_fixed
                if total_page_fixed > 0:
                    pages_modified += 1
                    lines_fixed += total_page_fixed
                    logger.info(
                        "[hairline_fixer] Página %d: %d trazos engrosados a %.2f pt",
                        page_num + 1, total_page_fixed, target_width
                    )
            except Exception as e:
                msg = f"Error en página {page_num + 1}: {e}"
                logger.warning(msg)
                errors.append(msg)

        pdf.save(str(output_path))
        logger.info("[hairline_fixer] PDF guardado en: %s", output_path)

    except Exception as e:
        errors.append(f"Error al guardar el PDF: {e}")
        return {
            "success": False,
            "pages_modified": pages_modified,
            "lines_fixed": lines_fixed,
            "errors": errors,
        }
    finally:
        pdf.close()

    return {
        "success": True,
        "pages_modified": pages_modified,
        "lines_fixed": lines_fixed,
        "errors": errors,
    }


def _fix_page_stream_hairlines(
    pdf: pikepdf.Pdf,
    page: pikepdf.Page,
    hairline_threshold: float,
    target_width: float,
) -> int:
    """Procesa el flujo de contenido de una página individual."""
    try:
        commands = list(pikepdf.parse_content_stream(page))
    except Exception as e:
        logger.warning("[hairline_fixer] No se pudo parsear el stream de la página: %s", e)
        return 0

    new_commands, count = _process_stream_commands(commands, hairline_threshold, target_width)
    if count > 0:
        new_data = pikepdf.unparse_content_stream(new_commands)
        page.Contents = pdf.make_stream(new_data)
    return count


def _fix_page_xobjects_hairlines(
    pdf: pikepdf.Pdf,
    page: pikepdf.Page,
    hairline_threshold: float,
    target_width: float,
) -> int:
    """Procesa Form XObjects vectoriales incluidos en la página."""
    total = 0
    try:
        resources = page.obj.get("/Resources")
        if not resources:
            return 0
        xobjects = resources.get("/XObject")
        if not xobjects:
            return 0

        for key, xobj in xobjects.items():
            try:
                # Solo Form XObjects tienen streams vectoriales
                if xobj.get("/Subtype") == pikepdf.Name("/Form"):
                    commands = list(pikepdf.parse_content_stream(xobj))
                    new_cmds, count = _process_stream_commands(commands, hairline_threshold, target_width)
                    if count > 0:
                        new_data = pikepdf.unparse_content_stream(new_cmds)
                        xobj.write(new_data)
                        total += count
            except Exception:
                continue
    except Exception as e:
        logger.warning("[hairline_fixer] Error al inspeccionar XObjects: %s", e)
    return total


def _process_stream_commands(
    commands: list,
    hairline_threshold: float,
    target_width: float,
) -> tuple[list, int]:
    """
    Recorre los operadores de un stream y reemplaza 'w' si su valor < hairline_threshold.
    Retorna (nuevos_comandos, cantidad_modificada).
    """
    new_commands = []
    count = 0

    for operands, operator in commands:
        op_str = str(operator)
        if op_str == "w" and operands:
            try:
                current_w = float(operands[0])
                if 0.0 <= current_w < hairline_threshold:
                    # Sustituir por target_width usando Decimal para un formateo limpio en el PDF
                    new_operands = [Decimal(str(target_width))]
                    new_commands.append((new_operands, operator))
                    count += 1
                    continue
            except Exception as e:
                logger.debug("[hairline_fixer] Error al leer operando w: %s", e)

        new_commands.append((operands, operator))

    return new_commands, count
