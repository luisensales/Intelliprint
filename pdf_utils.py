"""Shared PDF preservation and atomic output helpers."""

import os
import tempfile
import math
from contextlib import contextmanager
from pathlib import Path

import pikepdf


def pdf_numbers(values):
    """Serialize finite PDF coordinates without locale-dependent formatting."""
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError('Coordenadas PDF no válidas.')
    return ' '.join(format(float(value), '.8f').rstrip('0').rstrip('.') or '0' for value in values)


def rect_clip(rect):
    x0, y0, x1, y1 = map(float, rect)
    return pdf_numbers((x0, y0, x1 - x0, y1 - y0)) + ' re W n\n'


def add_form_resource(page, form):
    """Do not mutate a resource dictionary captured by an existing page Form."""
    resources = pikepdf.Dictionary(page.resources)
    if '/XObject' in resources:
        resources.XObject = pikepdf.Dictionary(resources.XObject)
    page.Resources = resources
    return page.add_resource(form, pikepdf.Name.XObject, prefix='IntelliPrint')


@contextmanager
def atomic_output(destination):
    """Keep the previous document intact until a complete output is available."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".intelliprint_", suffix=".pdf", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        yield temporary
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def copy_output_intents(source, destination):
    """Copy the entire object graph, including direct dictionaries and ICC streams."""
    if "/OutputIntents" in source.Root:
        intents = source.make_indirect(source.Root.OutputIntents)
        destination.Root.OutputIntents = destination.copy_foreign(intents)


def preserve_output_intents(source_path, generated_path, output_path=None):
    output_path = Path(output_path or generated_path)
    with atomic_output(output_path) as temporary:
        with pikepdf.open(source_path) as source, pikepdf.open(generated_path) as generated:
            copy_output_intents(source, generated)
            generated.save(temporary)


def copy_pdf(source_path, output_path):
    """A no-op is valid when the cumulative source is already the destination."""
    import shutil
    if Path(source_path).resolve() != Path(output_path).resolve():
        with atomic_output(output_path) as temporary:
            shutil.copyfile(source_path, temporary)


def iter_resources(pdf):
    """Include resources in nested Form XObjects, with cycle protection."""
    for page_index, page in enumerate(pdf.pages, 1):
        pending = [page.obj.get('/Resources', pikepdf.Dictionary())]
        seen = set()
        while pending:
            resources = pending.pop()
            yield page_index, resources
            for obj in resources.get('/XObject', {}).values():
                if str(obj.get('/Subtype')) != '/Form' or obj.objgen in seen:
                    continue
                seen.add(obj.objgen)
                pending.append(obj.get('/Resources', resources))


def used_spot_names(pdf):
    """Check actual color-space operators, excluding unused legacy resources."""
    names = set()
    seen = set()

    def scan(content, resources):
        for operands, operator in pikepdf.parse_content_stream(content):
            if str(operator) in ('cs', 'CS') and operands:
                color = resources.get('/ColorSpace', {}).get(operands[0])
                if isinstance(color, pikepdf.Array) and len(color) > 1:
                    if str(color[0]) == '/Separation':
                        names.add(str(color[1]).lstrip('/'))
                    elif str(color[0]) == '/DeviceN':
                        names.update(str(n).lstrip('/') for n in color[1])
            if str(operator) == 'Do' and operands:
                form = resources.get('/XObject', {}).get(operands[0])
                if form is not None and str(form.get('/Subtype')) == '/Form' and form.objgen not in seen:
                    seen.add(form.objgen)
                    scan(form, form.get('/Resources', resources))

    for page in pdf.pages:
        scan(page, page.obj.get('/Resources', pikepdf.Dictionary()))
    return names - {'All', 'None', 'Cyan', 'Magenta', 'Yellow', 'Black'}
