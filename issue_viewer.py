"""Read-only issue inspection tied to the exact PDF that produced the findings."""

import math

import pymupdf

from document_identity import sha256_file
from issue_locations import locate_finding
from security_limits import bounded_render_dpi


class StaleIssueAnalysis(ValueError):
    pass


def checked_pdf_identity(pdf_path, job_data, expected_sha256=None):
    digest = sha256_file(pdf_path)
    meta = job_data.get("job_meta", {})
    recorded = meta.get("current_sha256") or meta.get("sha256")
    if (expected_sha256 and digest != expected_sha256.lower()) or (recorded and digest != recorded):
        raise StaleIssueAnalysis("El PDF ha cambiado. Actualiza el análisis antes de abrir el visor.")
    return digest


def normalized_regions(page, rectangles):
    """Rotate physical CropBox-relative coordinates, including older MuPDF UserUnit behavior.

    Some MuPDF versions return an unscaled translation in rotation_matrix when
    UserUnit is present. Work directly in the physical dimensions of page.rect.
    """
    visible = page.rect
    rotation = page.rotation % 360
    width, height = ((visible.height, visible.width) if rotation in (90, 270)
                     else (visible.width, visible.height))
    result = []
    for rectangle in rectangles:
        try:
            box = pymupdf.Rect(rectangle)
            if not all(math.isfinite(value) for value in box) or box.is_empty or not box.is_valid:
                continue
            x0, y0, x1, y1 = box
            if rotation == 90:
                box = pymupdf.Rect(height - y1, x0, height - y0, x1)
            elif rotation == 180:
                box = pymupdf.Rect(width - x1, height - y1, width - x0, height - y0)
            elif rotation == 270:
                box = pymupdf.Rect(y0, width - x1, y1, width - x0)
            box = box & pymupdf.Rect(0, 0, visible.width, visible.height)
            if box.is_empty or not box.is_valid:
                continue
            result.append({"x": box.x0 / visible.width, "y": box.y0 / visible.height,
                           "width": box.width / visible.width, "height": box.height / visible.height})
        except (ValueError, TypeError, OverflowError):
            continue
    return result


def inspect_finding(pdf_path, job_data, finding_index, expected_sha256=None):
    findings = job_data.get("findings") or []
    if not 0 <= finding_index < len(findings):
        raise IndexError("Incidencia no encontrada en el análisis actual.")
    finding = findings[finding_index]
    if not isinstance(finding, dict):
        raise ValueError("La incidencia no contiene datos válidos.")
    page_number = finding.get("page") or 1
    if isinstance(page_number, bool) or not isinstance(page_number, int):
        raise ValueError("La incidencia no indica una página válida.")
    digest = checked_pdf_identity(pdf_path, job_data, expected_sha256)
    with pymupdf.open(pdf_path) as doc:
        if not 1 <= page_number <= len(doc):
            raise ValueError("La página de la incidencia está fuera del documento.")
        page = doc[page_number - 1]
        regions = normalized_regions(page, locate_finding(page, finding, job_data.get("job_summary") or {}))
        result = {"sha256": digest, "page": page_number, "pages": len(doc),
                  "width": page.rect.width, "height": page.rect.height,
                  "regions": regions, "location_status": "exact" if regions else "page",
                  "finding": dict(finding)}
    return result


def render_issue_page(pdf_path, job_data, page_number, expected_sha256, dpi):
    digest = checked_pdf_identity(pdf_path, job_data, expected_sha256)
    with pymupdf.open(pdf_path) as doc:
        if not 1 <= page_number <= len(doc):
            raise ValueError("Página fuera del documento.")
        page = doc[page_number - 1]
        pixmap = page.get_pixmap(dpi=bounded_render_dpi(page.rect, dpi), alpha=False)
        rendered = pixmap.tobytes("png")
    if sha256_file(pdf_path) != digest:
        raise StaleIssueAnalysis("El PDF cambió durante la previsualización. Actualiza el análisis.")
    return rendered
