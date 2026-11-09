"""Extend artwork beyond TrimBox without rescaling or converting its colours."""

import math
from typing import Any, Dict

import pikepdf

from pdf_utils import atomic_output, add_form_resource, pdf_numbers, rect_clip


def generate_mirror_bleed(pdf_path: str, output_path: str, bleed_mm: float = 3.0,
                          dpi: int = 300) -> Dict[str, Any]:
    """Reflect native PDF edge strips; dpi is retained for API compatibility.

    Original ICC, spots, annotations, rotation and coordinates stay intact.
    Reflections are an underlay outside TrimBox: real bleed takes precedence.
    """
    if not math.isfinite(bleed_mm) or bleed_mm < 0 or bleed_mm > 100:
        raise ValueError('El sangrado debe estar entre 0 y 100 mm.')
    details = []
    with atomic_output(output_path) as temporary:
        with pikepdf.open(pdf_path) as pdf:
            for index, page in enumerate(pdf.pages, 1):
                trim = list(map(float, page.trimbox))
                x0, y0, x1, y1 = trim
                unit = float(page.obj.get('/UserUnit', 1))
                if not math.isfinite(unit) or unit <= 0:
                    raise ValueError('Unidad de página PDF no válida.')
                bleed = bleed_mm * 72 / 25.4 / unit
                if x1 <= x0 or y1 <= y0 or bleed > min(x1 - x0, y1 - y0):
                    raise ValueError('El sangrado es mayor que la pieza o el corte no es válido.')
                if bleed == 0:
                    continue
                # Capture the original BEFORE attaching its reflected Form.
                artwork = page.as_form_xobject(handle_transformations=False)
                artwork.BBox = trim
                name = add_form_resource(page, artwork)
                bleedbox = [x0 - bleed, y0 - bleed, x1 + bleed, y1 + bleed]
                # Slight overlap under the original avoids white antialias seams.
                overlap = min(0.3 / unit, bleed / 10, (x1 - x0) / 100, (y1 - y0) / 100)
                left, right = 2 * x0 + overlap, 2 * x1 - overlap
                bottom, top = 2 * y0 + overlap, 2 * y1 - overlap
                regions = [
                    ([x0 - bleed, y0, x0 + overlap, y1], [-1, 0, 0, 1, left, 0]),
                    ([x1 - overlap, y0, x1 + bleed, y1], [-1, 0, 0, 1, right, 0]),
                    ([x0, y0 - bleed, x1, y0 + overlap], [1, 0, 0, -1, 0, bottom]),
                    ([x0, y1 - overlap, x1, y1 + bleed], [1, 0, 0, -1, 0, top]),
                    ([x0 - bleed, y0 - bleed, x0 + overlap, y0 + overlap], [-1, 0, 0, -1, left, bottom]),
                    ([x1 - overlap, y0 - bleed, x1 + bleed, y0 + overlap], [-1, 0, 0, -1, right, bottom]),
                    ([x0 - bleed, y1 - overlap, x0 + overlap, y1 + bleed], [-1, 0, 0, -1, left, top]),
                    ([x1 - overlap, y1 - overlap, x1 + bleed, y1 + bleed], [-1, 0, 0, -1, right, top]),
                ]
                commands = ''.join('q\n' + rect_clip(rect) + pdf_numbers(matrix) +
                                   f' cm\n{name} Do\nQ\n' for rect, matrix in regions)
                page.contents_add(commands.encode('ascii'), prepend=True)
                media = list(map(float, page.mediabox))
                page.MediaBox = [min(media[0], bleedbox[0]), min(media[1], bleedbox[1]),
                                 max(media[2], bleedbox[2]), max(media[3], bleedbox[3])]
                page.CropBox = page.MediaBox
                page.TrimBox = trim
                page.BleedBox = bleedbox
                details.append({'page': index, 'trim_box': trim, 'bleed_box': bleedbox})
            total_pages = len(pdf.pages)
            pdf.save(temporary)
    return {'success': True, 'status': 'success', 'pages_processed': len(details),
            'total_pages': total_pages, 'bleed_mm': bleed_mm,
            'method': 'native_pdf_reflection', 'details': details}
