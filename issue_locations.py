"""Locate preflight findings in the unrotated coordinates returned by MuPDF.

Coordinates are relative to the CropBox and include UserUnit, exactly like
Page.get_text() and Page.get_image_info(). Rotation and visible-page clipping
belong to the viewer. Missing evidence returns no regions instead of guessing.
"""

import math
import re

import pymupdf


_IMAGE_RULES = {"PRINT_IMAGE_EFFECTIVE_PPI", "SOURCE_COLOR_DIAGNOSTIC"}


def _positive_int(value):
    try:
        number = int(value)
        return number if not isinstance(value, bool) and number > 0 and number == float(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _box(value):
    if not isinstance(value, (list, tuple, pymupdf.Rect)) or len(value) != 4:
        return None
    try:
        bounds = [float(number) for number in value]
    except (ValueError, TypeError, OverflowError):
        return None
    if not all(math.isfinite(number) for number in bounds):
        return None
    return bounds if bounds[0] < bounds[2] and bounds[1] < bounds[3] else None


def _transform_box(transform):
    if not isinstance(transform, (list, tuple)) or len(transform) != 6:
        return None
    try:
        a, b, c, d, e, f = (float(value) for value in transform)
    except (ValueError, TypeError, OverflowError):
        return None
    return _box([min(e, a + e, c + e, a + c + e),
                 min(f, b + f, d + f, b + d + f),
                 max(e, a + e, c + e, a + c + e),
                 max(f, b + f, d + f, b + d + f)])


def _font_key(name):
    name = re.sub(r"^[A-Z]{6}\+", "", str(name).lstrip("/"))
    return re.sub(r"[\s,_-]+", "", name).casefold()


def _font_locations(page, finding):
    name = finding.get("font_name") or finding.get("font")
    if not isinstance(name, str) or not name.strip():
        match = re.search(r"fuente no incrustada:\s*(.+)$", str(finding.get("title") or ""), re.I)
        if not match:
            match = re.search(r"la fuente\s+['\"]([^'\"]+)['\"]", str(finding.get("message") or ""), re.I)
        name = match[1].strip() if match else None
    if not name:
        return []
    target = _font_key(name)
    names = {target}
    try:
        # Full resources include fonts inside Form XObjects. A resource alias
        # such as F1 must first be resolved to its base font, never a substring.
        for font in page.get_fonts(full=True):
            base, alias = _font_key(font[3]), _font_key(font[4])
            if target in (base, alias):
                names.add(base)
        flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
        blocks = page.get_text("dict", flags=flags).get("blocks", [])
    except (ValueError, RuntimeError):
        return []
    locations = []
    seen = set()
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if _font_key(span.get("font", "")) not in names or not span.get("text", "").strip():
                    continue
                bounds = _box(span.get("bbox"))
                if bounds is not None and tuple(bounds) not in seen:
                    locations.append(bounds)
                    seen.add(tuple(bounds))
    return locations


def _image_location(page, finding, summary):
    index = _positive_int(finding.get("image_index")) or _positive_int(finding.get("index"))
    if index is None:
        match = re.search(r"(?:imagen|colocaci[oó]n)\s+(\d+)", str(finding.get("message") or ""), re.I)
        index = _positive_int(match[1]) if match else None
    if index is None:
        # An xref identifies an image resource, not where or how often it paints.
        return []
    page_number = page.number + 1
    inventory = summary.get("images_inventory") or []
    for image in inventory:
        if (isinstance(image, dict) and _positive_int(image.get("page")) == page_number
                and _positive_int(image.get("index")) == index):
            bounds = _box(image.get("bbox")) or _transform_box(image.get("transform"))
            if bounds is not None:
                return [bounds]
    # The ordinal matches the preflight's get_image_info() paint occurrences,
    # including reused XObjects, Forms and inline images. Do not use get_images().
    try:
        images = page.get_image_info()
        if index <= len(images):
            bounds = _box(images[index - 1].get("bbox"))
            if bounds is not None:
                return [bounds]
    except (ValueError, RuntimeError):
        pass
    return []


def _bleed_locations(page, finding):
    """Show the relevant cut boundaries, not a guessed artwork object."""
    try:
        crop, trim = page.cropbox, page.trimbox
        width = page.rect.height if page.rotation in (90, 270) else page.rect.width
        unit = width / crop.width
        bounds = _box([(trim.x0 - crop.x0) * unit, (trim.y0 - crop.y0) * unit,
                       (trim.x1 - crop.x0) * unit, (trim.y1 - crop.y0) * unit])
    except (ValueError, RuntimeError, ZeroDivisionError):
        return []
    if bounds is None:
        return []
    x0, y0, x1, y1 = bounds
    band = min(3 * 72 / 25.4, (x1 - x0) / 2, (y1 - y0) / 2)
    edges = {"izquierdo": [x0, y0, x0 + band, y1],
             "superior": [x0, y0, x1, y0 + band],
             "derecho": [x1 - band, y0, x1, y1],
             "inferior": [x0, y1 - band, x1, y1]}
    text = f"{finding.get('title', '')} {finding.get('message', '')}".casefold()
    selected = [name for name in edges if re.search(rf"\b{name}\b", text)]
    return [edges[name] for name in selected or edges]


def locate_finding(page, finding, summary):
    """Return reliable [x0,y0,x1,y1] regions for a finding on this page.

    No rotation, cropping or normalization is applied to MuPDF object bounds.
    Font findings can have several spans; an image finding selects one painted
    occurrence. Document-level/unsupported findings stay at page level.
    """
    if not isinstance(finding, dict):
        return []
    finding_page = _positive_int(finding.get("page"))
    if finding_page is not None and finding_page != page.number + 1:
        return []
    bounds = _box(finding.get("bbox"))
    if bounds is not None:
        return [bounds]
    rule = finding.get("rule_id")
    if rule in _IMAGE_RULES:
        return _image_location(page, finding, summary if isinstance(summary, dict) else {})
    if rule == "USED_FONTS_EMBEDDED":
        return _font_locations(page, finding)
    if rule == "BLEED_GEOMETRY_3MM":
        return _bleed_locations(page, finding)
    return []
