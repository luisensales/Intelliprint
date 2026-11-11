"""Shared graphics-state tracking for PDF inspection and local corrections."""

import math
from decimal import Decimal

import pikepdf

IDENTITY = (1., 0., 0., 1., 0., 0.)
TEXT_SHOW = ('Tj', 'TJ', "'", '"')
FILL_PATH = ('f', 'F', 'f*', 'B', 'B*', 'b', 'b*')
STROKE_PATH = ('S', 's', 'B', 'B*', 'b', 'b*')


def visible_text(operator, operands):
    if not operands:
        return False
    if operator == 'TJ':
        return any(str(item).strip() for item in operands[0]
                   if not isinstance(item, (int, float, Decimal)))
    return bool(str(operands[-1]).strip())


def resolve_color_space(reference, resources, seen=()):
    if isinstance(reference, pikepdf.Name):
        key = str(reference)
        colors = resources.get('/ColorSpace', {}) if resources is not None else {}
        if key in colors:
            if key in seen:
                raise ValueError('Referencia circular de espacio de color.')
            return resolve_color_space(colors[key], resources, seen + (key,))
        return key.lstrip('/'), None
    if isinstance(reference, pikepdf.Array) and reference:
        family = str(reference[0]).lstrip('/')
        if family == 'ICCBased':
            from icc_manager import validate_icc_bytes
            profile = reference[1]
            channels = int(profile.get('/N', 0))
            device = {1: 'DeviceGray', 3: 'DeviceRGB', 4: 'DeviceCMYK'}.get(channels)
            if device is None:
                raise ValueError('Espacio ICCBased no verificable: número de canales inválido.')
            actual_family, _ = validate_icc_bytes(profile.read_bytes())
            if actual_family != {1: 'GRAY', 3: 'RGB', 4: 'CMYK'}[channels]:
                raise ValueError('El perfil ICCBased no coincide con sus canales declarados.')
            return device, None
        if family == 'Separation':
            return family, str(reference[1]).lstrip('/')
        if family == 'DeviceN':
            return family, tuple(str(name).lstrip('/') for name in reference[1])
        return family, None
    return str(reference), None


def initial_color(space):
    family, names = space
    if family == 'DeviceCMYK':
        return (0., 0., 0., 1.)
    if family == 'DeviceRGB':
        return (0., 0., 0.)
    if family == 'Separation':
        return (1.,)
    if family == 'DeviceN':
        return (1.,) * len(names)
    return (0.,)


def concat_matrix(current, new):
    a, b, c, d, e, f = current
    A, B, C, D, E, F = map(float, new)
    return (a*A + c*B, b*A + d*B, a*C + c*D, b*C + d*D,
            a*E + c*F + e, b*E + d*F + f)


def minimum_scale(matrix):
    a, b, c, d = matrix[:4]
    trace = a*a + b*b + c*c + d*d
    determinant = (a*d - b*c) ** 2
    return math.sqrt(max(0., (trace - math.sqrt(max(0., trace*trace - 4*determinant))) / 2))


def new_graphics_state(page=None):
    unit = float(page.obj.get('/UserUnit', 1)) if page is not None else 1.
    return dict(op=False, OP=False, OPM=0, fill_cs=('DeviceGray', None),
                stroke_cs=('DeviceGray', None), fill_color=(0.,), stroke_color=(0.,),
                text_render_mode=0, font_size=0., font_name='', line_width=1.,
                ctm=(unit, 0., 0., unit, 0., 0.), ctm_scale=unit, text_linear=IDENTITY)


def effective_font_size(state):
    matrix = concat_matrix(state['ctm'], state['text_linear'])
    return abs(state['font_size']) * math.hypot(matrix[2], matrix[3])


def painting_components(operator, operands, state):
    if operator in TEXT_SHOW:
        visible = visible_text(operator, operands)
        mode = state['text_render_mode']
        return visible and mode in (0, 2, 4, 6), visible and mode in (1, 2, 5, 6)
    return operator in FILL_PATH, operator in STROKE_PATH


def color_is_white(space, color):
    family = space[0]
    if family == 'DeviceGray':
        return len(color) == 1 and color[0] >= .99
    if family == 'DeviceRGB':
        return len(color) == 3 and all(c >= .98 for c in color)
    if family == 'DeviceCMYK':
        return len(color) == 4 and all(c <= .01 for c in color)
    return False


class GraphicsState:
    def __init__(self, initial=None):
        self.state = dict(initial) if initial is not None else new_graphics_state()
        self.stack = []

    def feed(self, operands, operator, resources):
        state = self.state
        if operator == 'q':
            self.stack.append(dict(state))
        elif operator == 'Q':
            if not self.stack:
                raise ValueError('El PDF contiene un Q sin su q correspondiente.')
            self.state = self.stack.pop()
        elif operator == 'gs' and operands:
            entry = resources.get('/ExtGState', {}).get(operands[0])
            if entry is not None:
                if '/OP' in entry:
                    state['OP'] = bool(entry.OP)
                    if '/op' not in entry:
                        state['op'] = state['OP']
                if '/op' in entry:
                    state['op'] = bool(entry.op)
                if '/OPM' in entry:
                    state['OPM'] = int(entry.OPM)
                if '/LW' in entry:
                    state['line_width'] = float(entry.LW)
                if '/Font' in entry:
                    state['font_size'] = float(entry.Font[1])
        elif operator == 'cm' and len(operands) == 6:
            state['ctm'] = concat_matrix(state['ctm'], operands)
            state['ctm_scale'] = minimum_scale(state['ctm'])
        elif operator == 'w' and operands:
            state['line_width'] = float(operands[0])
        elif operator == 'Tr' and operands:
            state['text_render_mode'] = int(operands[0])
        elif operator == 'Tf' and len(operands) == 2:
            state['font_name'], state['font_size'] = str(operands[0]), float(operands[1])
        elif operator == 'BT':
            state['text_linear'] = IDENTITY
        elif operator == 'Tm' and len(operands) == 6:
            state['text_linear'] = tuple(float(v) for v in operands)
        elif operator in ('g', 'rg', 'k', 'G', 'RG', 'K'):
            component = 'fill' if operator.islower() else 'stroke'
            family = {'g': 'DeviceGray', 'rg': 'DeviceRGB', 'k': 'DeviceCMYK'}[operator.lower()]
            state[component + '_cs'] = family, None
            state[component + '_color'] = tuple(float(v) for v in operands)
        elif operator in ('cs', 'CS') and operands:
            component = 'fill' if operator == 'cs' else 'stroke'
            space = resolve_color_space(operands[0], resources)
            state[component + '_cs'] = space
            state[component + '_color'] = initial_color(space)
        elif operator in ('sc', 'scn', 'SC', 'SCN'):
            component = 'fill' if operator.islower() else 'stroke'
            state[component + '_color'] = tuple(float(v) for v in operands
                                               if isinstance(v, (int, float, Decimal)))
        return self.state


def form_initial_state(form, state):
    initial = dict(state)
    initial['ctm'] = concat_matrix(state['ctm'], form.get('/Matrix', IDENTITY))
    initial['ctm_scale'] = minimum_scale(initial['ctm'])
    return initial


def overprint_state_command(resources, fill, stroke, mode):
    """Create an isolated resource without trusting existing producer IP_* names."""
    if '/ExtGState' not in resources:
        resources.ExtGState = pikepdf.Dictionary()
    states = resources.ExtGState
    entry = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, op=bool(fill), OP=bool(stroke), OPM=int(mode))
    prefix = f'/IPState{int(fill)}{int(stroke)}_{int(mode)}'
    name = prefix
    index = 1
    while name in states and states[name] != entry:
        name = prefix + '_' + str(index)
        index += 1
    states[name] = entry
    return [pikepdf.Name(name)], pikepdf.Operator('gs')


def rewrite_page_graphics(pdf, page, callback):
    """Rewrite paint operations and clone Forms for each inherited decision state.

    The callback returns commands before/after the original paint operation and
    restores every parameter it changes. No q/Q is inserted inside text objects,
    preserving text matrices and the effects of quote operators.
    """
    def scope(content, original_resources, initial, ancestors):
        if len(ancestors) > 50:
            raise ValueError('Demasiados formularios PDF anidados.')
        resources = pikepdf.Dictionary(original_resources)
        resources.ExtGState = pikepdf.Dictionary(resources.get('/ExtGState', {}))
        originals = original_resources.get('/XObject', {})
        xobjects = pikepdf.Dictionary(originals)
        tracker = GraphicsState(initial)
        commands, modified = [], False
        cache = {}

        for command in pikepdf.parse_content_stream(content):
            if isinstance(command, pikepdf.ContentStreamInlineImage):
                commands.append(command)
                continue
            operands, operator = command
            op = str(operator)
            state = tracker.feed(operands, op, original_resources)
            before, after = callback(operands, op, state, resources)
            if before or after:
                modified = True
            commands.extend(before)
            if op == 'Do' and operands:
                key = operands[0]
                form = originals.get(key)
                if form is not None and str(form.get('/Subtype')) == '/Form':
                    identity = form.objgen
                    if identity in ancestors:
                        raise ValueError('Referencia circular entre formularios PDF.')
                    # Translation does not affect any correction decision.
                    signature = tuple((k, v[:4] if k in ('ctm', 'text_linear') else v)
                                      for k, v in sorted(state.items()))
                    cache_key = str(key), signature
                    if cache_key not in cache:
                        child_commands, child_resources, changed = scope(
                            form, form.get('/Resources', original_resources),
                            form_initial_state(form, state), ancestors + (identity,))
                        replacement = None
                        if changed:
                            # Keep the original name for invocations that do not
                            # need correction under a different inherited state.
                            index = 1
                            while f'/IPFixForm{index}' in xobjects:
                                index += 1
                            replacement = pikepdf.Name(f'/IPFixForm{index}')
                            clone = pdf.make_stream(pikepdf.unparse_content_stream(child_commands))
                            for attr, value in form.items():
                                if str(attr) not in ('/Length', '/Filter', '/DecodeParms', '/Resources'):
                                    clone[attr] = value
                            clone.Resources = child_resources
                            xobjects[replacement] = clone
                        cache[cache_key] = replacement
                    replacement = cache[cache_key]
                    if replacement is not None:
                        modified = True
                        operands = [replacement]
            commands.append((operands, operator))
            commands.extend(after)
        if tracker.stack:
            raise ValueError('El PDF contiene bloques q/Q sin equilibrar.')
        if '/XObject' in original_resources:
            resources.XObject = xobjects
        return commands, resources, modified

    commands, resources, changed = scope(page, page.resources, new_graphics_state(page), ())
    if changed:
        page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(commands))
        page.Resources = resources
    return changed
