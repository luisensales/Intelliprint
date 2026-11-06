"""
technical_ink_fixer.py
======================
Motor de corrección automática de sobreimpresión para tintas técnicas
(barnices, lacas, estampaciones y troqueles).

Garantiza que cualquier capa técnica (ej. Barniz UV, Troquel, Acabado)
sobreimprima siempre sobre la impresión de fondo para evitar que
calado (knockout) perfore en blanco la cuatricromía inferior.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Union

import pikepdf

logger = logging.getLogger(__name__)

VARNISH_KEYWORDS = [
    'barniz', 'varnish', 'laca', 'lacquer', 'uv', 'gloss', 'brillo',
    'mate', 'matt', 'acabado', 'dieline', 'troquel', 'stamping', 'corte'
]


def is_technical_ink(name: str) -> bool:
    """True si la tinta es técnica (barniz, troquel, laca)."""
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(name)).lower()
    return any(k in clean for k in VARNISH_KEYWORDS)


def apply_overprint_to_technical_inks(
    pdf_path: Union[str, Path],
    output_path: Union[str, Path],
) -> dict:
    """
    Recorre todas las páginas del PDF y fuerza la sobreimpresión obligatoria
    (op=True, OP=True, OPM=1) en todos los objetos que usen tintas técnicas
    (barnices, lacas, troqueles).
    
    Retorna dict con:
        success: bool
        pages_modified: int
        objects_fixed: int
        technical_spots_fixed: list[str]
        errors: list[str]
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    errors: list[str] = []
    pages_modified_count = 0
    total_objects_fixed = 0
    technical_spots_found = set()

    try:
        pdf = pikepdf.open(str(pdf_path))
    except Exception as e:
        return {
            "success": False,
            "pages_modified": 0,
            "objects_fixed": 0,
            "technical_spots_fixed": [],
            "errors": [f"No se pudo abrir el PDF: {e}"],
        }

    try:
        for page_num, page in enumerate(pdf.pages, 1):
            res = page.obj.get('/Resources')
            if not res or '/ColorSpace' not in res:
                continue

            cs_dict = res['/ColorSpace']
            # Identificar qué nombres de ColorSpace corresponden a tintas técnicas
            tech_cs_keys = set()
            for cs_key, cs_val in cs_dict.items():
                if isinstance(cs_val, pikepdf.Array) and len(cs_val) >= 2:
                    cs_type = str(cs_val[0])
                    if cs_type in ('/Separation', '/DeviceN'):
                        spot_name = str(cs_val[1]).lstrip('/')
                        if is_technical_ink(spot_name):
                            tech_cs_keys.add(str(cs_key))
                            technical_spots_found.add(spot_name)

            if not tech_cs_keys:
                continue

            # Inyectar /IP_OP y /IP_KO en Resources.ExtGState si no existen
            _ensure_extgstate(page)
            _inject_gs_entries(pdf, page)

            # Procesar el stream de contenido de la página
            try:
                raw_cmds = pikepdf.parse_content_stream(page)
                extgs_dict = _get_extgstate_dict(page)
                new_cmds, n_fixed = _process_stream_technical_overprint(raw_cmds, tech_cs_keys, extgs_dict)
                if n_fixed > 0:
                    page.Contents = pikepdf.Stream(pdf, pikepdf.unparse_content_stream(new_cmds))
                    pages_modified_count += 1
                    total_objects_fixed += n_fixed
                    logger.info(f"[technical_ink_fixer] Pág {page_num}: {n_fixed} objetos de tinta técnica corregidos.")
            except Exception as e:
                errors.append(f"Error procesando pág {page_num}: {e}")

            # Procesar XObjects Form si los hay
            if '/XObject' in res:
                for xk, xv in res['/XObject'].items():
                    if isinstance(xv, pikepdf.Stream) and xv.get('/Subtype') == '/Form':
                        try:
                            f_cmds = pikepdf.parse_content_stream(xv)
                            f_extgs = _get_extgstate_dict(xv)
                            new_f_cmds, f_fixed = _process_stream_technical_overprint(f_cmds, tech_cs_keys, f_extgs)
                            if f_fixed > 0:
                                xv.write(pikepdf.unparse_content_stream(new_f_cmds))
                                total_objects_fixed += f_fixed
                        except Exception:
                            pass

        pdf.save(str(output_path))
        logger.info(f"[technical_ink_fixer] Guardado en {output_path} con {total_objects_fixed} objetos corregidos.")

    except Exception as e:
        errors.append(f"Error al guardar el PDF: {e}")
        return {
            "success": False,
            "pages_modified": pages_modified_count,
            "objects_fixed": total_objects_fixed,
            "technical_spots_fixed": sorted(list(technical_spots_found)),
            "errors": errors,
        }
    finally:
        pdf.close()

    return {
        "success": True,
        "pages_modified": pages_modified_count,
        "objects_fixed": total_objects_fixed,
        "technical_spots_fixed": sorted(list(technical_spots_found)),
        "errors": errors,
    }


def _ensure_extgstate(page: pikepdf.Page) -> None:
    res = page.obj.get("/Resources")
    if res is None:
        page.obj["/Resources"] = pikepdf.Dictionary()
        res = page.obj["/Resources"]
    if "/ExtGState" not in res:
        res["/ExtGState"] = pikepdf.Dictionary()


def _inject_gs_entries(pdf: pikepdf.Pdf, page: pikepdf.Page) -> None:
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


def _get_extgstate_dict(obj) -> dict:
    result = {}
    try:
        res = obj.get("/Resources") if hasattr(obj, 'get') else obj.obj.get("/Resources")
        if res and "/ExtGState" in res:
            extgs = res["/ExtGState"]
            for key in extgs.keys():
                result[key.lstrip("/")] = extgs[key]
    except Exception:
        pass
    return result


def _process_stream_technical_overprint(
    commands: list,
    tech_cs_keys: set[str],
    extgs_dict: dict
) -> tuple[list, int]:
    """
    Inyecta /IP_OP antes de objetos que utilicen una tinta técnica si no están sobreimprimiendo,
    y /IP_KO al salir.
    """
    new_commands = []
    n_fixed = 0

    current_fill_is_tech = False
    current_stroke_is_tech = False
    currently_overprinting = False

    for operands, op in commands:
        op_str = str(op)

        if op_str == 'cs':
            if operands:
                cs_key = str(operands[0])
                current_fill_is_tech = (cs_key in tech_cs_keys)
        elif op_str == 'CS':
            if operands:
                cs_key = str(operands[0])
                current_stroke_is_tech = (cs_key in tech_cs_keys)
        elif op_str in ('g', 'rg', 'k'):
            current_fill_is_tech = False
        elif op_str in ('G', 'RG', 'K'):
            current_stroke_is_tech = False

        elif op_str == 'gs':
            if len(operands) == 1:
                gs_name_clean = str(operands[0]).lstrip("/")
                gs_entry = extgs_dict.get(gs_name_clean)
                if gs_entry is not None:
                    for key in ("/op", "/OP"):
                        if key in gs_entry:
                            currently_overprinting = bool(gs_entry[key])
                            break

        # Comprobar operaciones de dibujo (vectorial o texto)
        is_fill_draw = op_str in ('f', 'F', 'f*', 'b', 'b*', 'B', 'B*', 'Tj', 'TJ', "'", '"')
        is_stroke_draw = op_str in ('s', 'S', 'b', 'b*', 'B', 'B*')

        needs_tech_overprint = (
            (is_fill_draw and current_fill_is_tech) or
            (is_stroke_draw and current_stroke_is_tech)
        )

        if needs_tech_overprint and not currently_overprinting:
            new_commands.append(([pikepdf.Name("/IP_OP")], pikepdf.Operator("gs")))
            currently_overprinting = True
            n_fixed += 1
        elif not needs_tech_overprint and currently_overprinting and (is_fill_draw or is_stroke_draw):
            # Si un objeto que no es técnico se va a dibujar pero el overprint estaba activo,
            # restaurar calado por seguridad
            new_commands.append(([pikepdf.Name("/IP_KO")], pikepdf.Operator("gs")))
            currently_overprinting = False

        new_commands.append((operands, op))

    return new_commands, n_fixed

