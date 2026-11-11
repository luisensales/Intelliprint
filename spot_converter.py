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

def _spot_names(space):
    if str(space[0]) == '/DeviceN':
        return [str(name).lstrip('/') for name in space[1]]
    return [str(space[1]).lstrip('/')]


class _SpotColor:
    """Evaluate a supported single-channel tint transform in its actual alternate space."""

    def __init__(self, definition, resources=None):
        self.definition = definition
        self.resources = resources or pikepdf.Dictionary()
        self.names = _spot_names(definition)
        self.name = ', '.join(self.names)
        self.parameters = None

    def _load(self):
        import math
        if len(self.names) != 1:
            raise ValueError(f"DeviceN multicanal no convertible sin perder tintas: {self.name}")
        alternate = self.definition[2]
        visited = set()
        while isinstance(alternate, pikepdf.Name) and str(alternate) not in (
                '/DeviceCMYK', '/DeviceRGB', '/DeviceGray'):
            key = str(alternate)
            if key in visited or key not in self.resources.get('/ColorSpace', {}):
                break
            visited.add(key)
            alternate = self.resources.ColorSpace[key]
        family = str(alternate[0]) if isinstance(alternate, pikepdf.Array) else str(alternate)
        components = {'/DeviceCMYK': 4, '/DeviceRGB': 3, '/DeviceGray': 1, '/Lab': 3}.get(family)
        if components is None:
            raise ValueError(f"Espacio alternativo no soportado para {self.name}: {family}")
        function = self.definition[3]
        if not hasattr(function, 'get') or int(function.get('/FunctionType', -1)) != 2:
            raise ValueError(f"Transformación de tinta no soportada para {self.name}.")
        c0 = tuple(float(v) for v in function.get('/C0', [0]))
        c1 = tuple(float(v) for v in function.get('/C1', [1]))
        exponent = float(function.get('/N', 1))
        domain = tuple(float(v) for v in function.get('/Domain', [0, 1]))
        if (len(c0) != components or len(c1) != components or domain != (0, 1)
                or not all(math.isfinite(v) for v in (*c0, *c1, exponent)) or exponent < 0):
            raise ValueError(f"Parámetros de tinta no válidos para {self.name}.")
        ranges = function.get('/Range')
        if ranges is not None:
            ranges = tuple(float(v) for v in ranges)
            if (len(ranges) != components * 2 or not all(math.isfinite(v) for v in ranges)
                    or any(ranges[i] > ranges[i + 1] for i in range(0, len(ranges), 2))):
                raise ValueError(f"Rango de tinta no válido para {self.name}.")
        self.parameters = family, c0, c1, exponent, ranges

    def color(self, tint):
        import math
        if self.parameters is None:
            self._load()
        tint = float(tint)
        if not math.isfinite(tint):
            raise ValueError("El porcentaje de tinta debe ser finito.")
        family, c0, c1, exponent, ranges = self.parameters
        factor = max(0.0, min(1.0, tint)) ** exponent
        values = [a + factor * (b - a) for a, b in zip(c0, c1)]
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f"Resultado de tinta no válido para {self.name}.")
        if ranges:
            values = [max(ranges[2*i], min(ranges[2*i+1], v)) for i, v in enumerate(values)]
        if family == '/Lab':
            # Retain the existing approximate Lab conversion, only for actual Lab spaces.
            return lab_to_cmyk(*values)
        values = [max(0.0, min(1.0, v)) for v in values]
        if family == '/DeviceRGB':
            return rgb_to_cmyk(*values)
        if family == '/DeviceGray':
            return 0.0, 0.0, 0.0, round(1 - values[0], 4)
        return tuple(round(v, 4) for v in values)


def extract_spot_cmyk_equivalent(cs_val: pikepdf.Array) -> tuple[str, tuple[float, float, float, float]]:
    """Return the full tint's CMYK equivalent; never infer a space from component count."""
    conversion = _SpotColor(cs_val)
    return conversion.name, conversion.color(1)


def _mapped_color(conversion, tint):
    if isinstance(conversion, _SpotColor):
        return conversion.color(tint)
    # Retain the internal helper's previous (name, CMYK base) calling contract.
    import math
    if not math.isfinite(float(tint)):
        raise ValueError("El porcentaje de tinta debe ser finito.")
    tint = max(0.0, min(1.0, float(tint)))
    return tuple(round(tint * float(v), 4) for v in conversion[1])


def _transform_stream_spots_to_cmyk(commands, spots_map, initial_state=(None, None),
                                    form_handler=None, on_convert=None):
    """Track independent fill/stroke spaces through the complete q/Q stack."""
    fill, stroke = initial_state
    stack = []
    output = []

    def note(key, conversion):
        if on_convert is not None:
            on_convert(key, conversion)

    for command in commands:
        if isinstance(command, pikepdf.ContentStreamInlineImage):
            output.append(command)
            continue
        operands, operator = command
        op = str(operator)
        if op == 'q':
            stack.append((fill, stroke))
        elif op == 'Q':
            if not stack:
                raise ValueError("El PDF contiene un Q sin su q correspondiente.")
            fill, stroke = stack.pop()
        elif op in ('cs', 'CS') and operands:
            key = str(operands[0])
            conversion = spots_map.get(key)
            if op == 'cs':
                fill = conversion
            else:
                stroke = conversion
            if conversion is not None:
                output.append(([pikepdf.Name.DeviceCMYK], pikepdf.Operator(op)))
                # cs/CS reset the original Separation tint to 1, not CMYK black.
                output.append((list(_mapped_color(conversion, 1)),
                               pikepdf.Operator('k' if op == 'cs' else 'K')))
                note(key, conversion)
                continue
        elif op in ('sc', 'scn', 'SC', 'SCN'):
            conversion = fill if op.islower() else stroke
            if conversion is not None:
                if len(operands) != 1:
                    raise ValueError("La tinta seleccionada exige un único componente.")
                tint = float(operands[0])
                output.append((list(_mapped_color(conversion, tint)),
                               pikepdf.Operator('k' if op.islower() else 'K')))
                note(None, conversion)
                continue
        elif op in ('g', 'rg', 'k'):
            fill = None
        elif op in ('G', 'RG', 'K'):
            stroke = None
        elif op == 'Do' and operands and form_handler is not None:
            replacement = form_handler(operands[0], (fill, stroke))
            if replacement is not None:
                output.append(([replacement], operator))
                continue
        output.append((operands, operator))
    if stack:
        raise ValueError("El PDF contiene bloques q/Q sin equilibrar.")
    return output


def _contains_name(value, key, seen=None):
    """Find named color references in resources that are not content streams."""
    if isinstance(value, pikepdf.Name):
        return str(value) == key
    if not isinstance(value, (pikepdf.Array, pikepdf.Dictionary, pikepdf.Stream)):
        return False
    seen = set() if seen is None else seen
    # Direct dictionaries cannot form cycles without an indirect reference.
    # Their temporary Python wrappers can reuse ids while iterating siblings.
    if value.objgen != (0, 0):
        if value.objgen in seen:
            return False
        seen.add(value.objgen)
    children = value if isinstance(value, pikepdf.Array) else value.values()
    return any(_contains_name(child, key, seen) for child in children)


def _needs_original_color(resources, key, commands):
    if any(isinstance(cmd, pikepdf.ContentStreamInlineImage) for cmd in commands):
        return True
    for name, space in resources.get('/ColorSpace', {}).items():
        if str(name) != key and _contains_name(space, key):
            return True
    for section in ('/Pattern', '/Shading'):
        if _contains_name(resources.get(section), key):
            return True
    for obj in resources.get('/XObject', {}).values():
        if str(obj.get('/Subtype')) != '/Form' and _contains_name(obj, key):
            return True
    return False


def convert_spot_colors_to_cmyk(pdf_path: Union[str, Path], output_path: Union[str, Path],
                                target_spots: Optional[list[str]] = None,
                                convert_technical: bool = False) -> dict:
    """Convert vector spots atomically, including nested Forms and inherited state.

    Unsupported tint functions and multi-channel DeviceN are rejected explicitly,
    keeping both the source and any previous output intact.
    """
    from pdf_utils import atomic_output
    converted_info = {}
    pages_modified = 0

    def eligible(definition):
        if not isinstance(definition, pikepdf.Array) or len(definition) < 4:
            return False
        if str(definition[0]) not in ('/Separation', '/DeviceN'):
            return False
        names = _spot_names(definition)
        return (names and not any(n in ('All', 'None') for n in names)
                and (convert_technical or not any(is_technical_ink(n) for n in names))
                and (target_spots is None or any(n in target_spots for n in names)))

    try:
        with atomic_output(output_path) as temporary:
            with pikepdf.open(pdf_path) as pdf:
                def process_scope(content, original_resources, page_index,
                                  initial_state=(None, None), ancestors=()):
                    if len(ancestors) > 50:
                        raise ValueError("Demasiados formularios PDF anidados.")
                    resources = pikepdf.Dictionary(original_resources)
                    colors = pikepdf.Dictionary(resources.get('/ColorSpace', {}))
                    originals = resources.get('/XObject', {})
                    xobjects = pikepdf.Dictionary(originals)
                    spots = {str(key): _SpotColor(value, original_resources)
                             for key, value in colors.items() if eligible(value)}
                    changed_keys = set()
                    modified = False
                    form_cache = {}

                    def record(key, conversion):
                        nonlocal modified
                        modified = True
                        if key is not None:
                            changed_keys.add(key)
                        base = conversion.color(1)
                        info = converted_info.setdefault(conversion.name, {
                            'name': conversion.name, 'cmyk_base': list(base),
                            'cmyk_str': ' '.join(f'{label}:{round(value*100)}%'
                                                 for label, value in zip('CMYK', base)),
                            'pages': []})
                        if page_index not in info['pages']:
                            info['pages'].append(page_index)

                    def form_handler(key, state):
                        nonlocal modified
                        original = originals.get(key)
                        if original is None or str(original.get('/Subtype')) != '/Form':
                            return None
                        cache_key = (str(key), id(state[0]), id(state[1]))
                        if cache_key in form_cache:
                            return form_cache[cache_key]
                        identity = original.objgen
                        if identity in ancestors:
                            raise ValueError("El PDF contiene referencias cíclicas entre formularios.")
                        own_resources = original.get('/Resources', original_resources)
                        commands, child_resources, changed = process_scope(
                            original, own_resources, page_index, state, ancestors + (identity,))
                        replacement = None
                        if changed:
                            index = 1
                            while f'/IPSpotForm{index}' in xobjects:
                                index += 1
                            replacement = pikepdf.Name(f'/IPSpotForm{index}')
                            clone = pdf.make_stream(pikepdf.unparse_content_stream(commands))
                            for attr, value in original.items():
                                if str(attr) not in ('/Length', '/Filter', '/DecodeParms', '/Resources'):
                                    clone[attr] = value
                            clone.Resources = child_resources
                            xobjects[replacement] = clone
                            modified = True
                        form_cache[cache_key] = replacement
                        return replacement

                    raw_commands = list(pikepdf.parse_content_stream(content))
                    new_commands = _transform_stream_spots_to_cmyk(
                        raw_commands, spots, initial_state, form_handler, record)
                    for key in changed_keys:
                        if not _needs_original_color(original_resources, key, raw_commands):
                            colors[key] = pikepdf.Name.DeviceCMYK
                    if '/ColorSpace' in resources:
                        resources.ColorSpace = colors
                    if '/XObject' in resources:
                        resources.XObject = xobjects
                    return new_commands, resources, modified

                for page_index, page in enumerate(pdf.pages, 1):
                    commands, resources, modified = process_scope(page, page.resources, page_index)
                    if modified:
                        page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(commands))
                        page.Resources = resources
                        pages_modified += 1
                pdf.save(temporary)
        return {'success': True, 'spots_converted': list(converted_info.values()),
                'pages_modified': pages_modified, 'errors': []}
    except Exception as exc:
        logger.warning("Spot conversion aborted: %s", exc)
        return {'success': False, 'spots_converted': [], 'pages_modified': 0, 'errors': [str(exc)]}

