"""
overprint_fixer.py
==================
Motor de corrección automática de sobreimpresión (auto-trapping) para IntelliPrint.

Módulos incluidos:
  1. apply_overprint_to_dark_text      – Auto-trapping de textos en negro puro 100% K en calado
  2. apply_overprint_to_technical_inks – Sobreimpresión obligatoria de barnices/troqueles
  3. fix_white_overprint               – White Overprint Killer: objetos blancos en sobreimpresión
  4. fix_rich_black_small_text         – Rich Black Killer: negro enriquecido en texto < 12 pt → 100% K puro

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
DARK_K_THRESHOLD = 0.99    # K minimo para considerar negro puro (100% K)
CMY_MAX = 0.05             # CMY maximo para que sea negro puro (no color compuesto)
GRAY_DARK_THRESHOLD = 0.01 # Para operador 'g': escala de grises <= 0.01 equivale a 100% K


# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------

from pdf_graphics import (
    color_is_white, effective_font_size, overprint_state_command,
    painting_components, rewrite_page_graphics, visible_text, TEXT_SHOW,
)
from pdf_utils import atomic_output

RICH_BLACK_MAX_PT = 12.0
RICH_BLACK_K_MIN = .30
RICH_BLACK_CMY_MIN = .05

VARNISH_KEYWORDS = [
    'barniz', 'varnish', 'laca', 'lacquer', 'uv', 'gloss', 'brillo',
    'mate', 'matt', 'acabado', 'dieline', 'troquel', 'stamping', 'corte'
]


def _is_visible_text(op_str, operands):
    return visible_text(op_str, operands)


def _is_technical_ink_name(name):
    import re
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(name)).lower()
    return any(k in clean for k in VARNISH_KEYWORDS)


def _flags_change(resources, state, fill, stroke, mode):
    if (fill, stroke, mode) == (state['op'], state['OP'], state['OPM']):
        return [], []
    return ([overprint_state_command(resources, fill, stroke, mode)],
            [overprint_state_command(resources, state['op'], state['OP'], state['OPM'])])


def _run_fixer(pdf_path, output_path, kind, dark_k_threshold=DARK_K_THRESHOLD,
               cmy_max=CMY_MAX, max_pt=RICH_BLACK_MAX_PT, target_spots=None):
    """Every paint correction restores its original color and overprint flags."""
    import math
    counts = dict(pages_modified=0)
    key = {'dark': 'text_ops_fixed', 'white': 'objects_fixed',
           'rich': 'texts_fixed', 'technical': 'ops_fixed'}[kind]
    counts[key] = 0
    technical_spots = set()

    def result(success, errors):
        values = dict(counts) if success else {name: 0 for name in counts}
        if kind == 'dark':
            values['text_100_fixed'] = values[key]
        if kind == 'technical':
            values['technical_spots_fixed'] = sorted(technical_spots) if success else []
        return dict(success=success, errors=errors, **values)

    try:
        if not all(math.isfinite(float(v)) for v in (dark_k_threshold, cmy_max, max_pt)) or max_pt <= 0:
            raise ValueError('Umbrales de corrección no válidos.')
        with atomic_output(output_path) as temporary:
            with pikepdf.open(pdf_path) as pdf:
                def correct(operands, op, state, resources):
                    fill, stroke = painting_components(op, operands, state)
                    before, after = [], []
                    if kind == 'rich' and op in TEXT_SHOW and fill:
                        color = state['fill_color']
                        if (state['fill_cs'][0] == 'DeviceCMYK' and len(color) == 4
                                and 0 < effective_font_size(state) < max_pt
                                and color[3] > RICH_BLACK_K_MIN
                                and any(v > RICH_BLACK_CMY_MIN for v in color[:3])):
                            before, after = _flags_change(resources, state, True, state['OP'], 1)
                            before.insert(0, ([0, 0, 0, 1], pikepdf.Operator('k')))
                            after.append((list(color), pikepdf.Operator('k')))
                    elif kind == 'dark' and op in TEXT_SHOW and fill:
                        family, _ = state['fill_cs']
                        color = state['fill_color']
                        dark = ((family == 'DeviceGray' and len(color) == 1 and color[0] <= GRAY_DARK_THRESHOLD)
                                or (family == 'DeviceCMYK' and len(color) == 4
                                    and color[3] >= dark_k_threshold
                                    and all(v <= cmy_max for v in color[:3])))
                        if dark:
                            before, after = _flags_change(resources, state, True, state['OP'], 1)
                    elif kind == 'white':
                        white_fill = fill and state['op'] and color_is_white(state['fill_cs'], state['fill_color'])
                        white_stroke = stroke and state['OP'] and color_is_white(state['stroke_cs'], state['stroke_color'])
                        if white_fill or white_stroke:
                            before, after = _flags_change(
                                resources, state, False if white_fill else state['op'],
                                False if white_stroke else state['OP'], state['OPM'])
                    elif kind == 'technical':
                        def selected(space):
                            names = space[1]
                            names = names if isinstance(names, tuple) else (names,) if names else ()
                            return [name for name in names if (
                                name in target_spots if target_spots is not None else _is_technical_ink_name(name))]
                        fill_spots = selected(state['fill_cs']) if fill else []
                        stroke_spots = selected(state['stroke_cs']) if stroke else []
                        if fill_spots or stroke_spots:
                            before, after = _flags_change(resources, state, True if fill_spots else state['op'],
                                                         True if stroke_spots else state['OP'], 1)
                            if before:
                                technical_spots.update(fill_spots + stroke_spots)
                    if before or after:
                        counts[key] += 1
                    return before, after

                for page in pdf.pages:
                    if rewrite_page_graphics(pdf, page, correct):
                        counts['pages_modified'] += 1
                pdf.save(temporary)
        return result(True, [])
    except Exception as exc:
        logger.warning('Overprint correction aborted: %s', exc)
        return result(False, [str(exc)])


def apply_overprint_to_dark_text(pdf_path: Union[str, Path], output_path: Union[str, Path],
                                 dark_k_threshold: float = DARK_K_THRESHOLD, cmy_max: float = CMY_MAX) -> dict:
    """Apply overprint only to each visible pure-black text operation."""
    return _run_fixer(pdf_path, output_path, 'dark', dark_k_threshold=dark_k_threshold, cmy_max=cmy_max)


def fix_white_overprint(pdf_path: Union[str, Path], output_path: Union[str, Path]) -> dict:
    """Disable overprint only for white components actually painted by an object."""
    return _run_fixer(pdf_path, output_path, 'white')


def fix_rich_black_small_text(pdf_path: Union[str, Path], output_path: Union[str, Path],
                              max_pt: float = RICH_BLACK_MAX_PT) -> dict:
    """Convert small rich-black fills to pure K without changing subsequent objects."""
    return _run_fixer(pdf_path, output_path, 'rich', max_pt=max_pt)


def apply_overprint_to_technical_inks(pdf_path: Union[str, Path], output_path: Union[str, Path],
                                      target_spots: Optional[list[str]] = None) -> dict:
    """Overprint selected technical colorants without changing other paint operations."""
    return _run_fixer(pdf_path, output_path, 'technical', target_spots=target_spots)
