"""Identify affected image placements for human-readable preflight reports."""

import math
import re


_RESOLUTION = "PRINT_IMAGE_EFFECTIVE_PPI"
_COLOR = "SOURCE_COLOR_DIAGNOSTIC"
_FIELDS = ("effective_dpi", "target_dpi", "colorspace", "width_px", "height_px", "placed_mm", "bbox", "xref")


def _positive_int(value):
    try:
        parsed = int(value)
        return parsed if not isinstance(value, bool) and parsed > 0 and parsed == float(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _number(value):
    try:
        parsed = float(str(value).replace(",", "."))
        return parsed if math.isfinite(parsed) else None
    except (ValueError, TypeError):
        return None


def _transform_bbox(transform):
    if not isinstance(transform, (list, tuple)) or len(transform) != 6:
        return None
    values = [_number(value) for value in transform]
    if any(value is None for value in values):
        return None
    a, b, c, d, e, f = values
    xs, ys = (e, a + e, c + e, a + c + e), (f, b + f, d + f, b + d + f)
    return [min(xs), min(ys), max(xs), max(ys)]


def _legacy_details(finding):
    message = str(finding.get("message") or "")
    title = str(finding.get("title") or "")
    text = title + " " + message
    details = {}
    match = re.search(r"(?:imagen|colocaci[oó]n)\s+(\d+)", message, re.I)
    if match:
        details["image_index"] = int(match[1])
    match = re.search(r"p[aá]g(?:ina)?\.?\s*(\d+)", message, re.I)
    if match:
        details["page"] = int(match[1])
    match = re.search(r"resoluci[oó]n efectiva(?: de)?\s*(\d+(?:[.,]\d+)?)\s*(?:ppp|ppi|dpi)", message, re.I)
    if not match and not re.search(r"no verificable|N/D", title, re.I):
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ppp|ppi|dpi)", title, re.I)
    if match:
        details["effective_dpi"] = _number(match[1])
    match = re.search(r"m[ií]nimo\s+(?:de\s+)?(\d+(?:[.,]\d+)?)\s*(?:ppp|ppi|dpi)", message, re.I)
    if match:
        details["target_dpi"] = _number(match[1])
    if re.search(r"escala de grises|gray|gris", text, re.I):
        details["colorspace"] = "Escala de grises"
    else:
        match = re.search(r"(?:espacio(?: de color)?|modo)\s+(CMYK|RGB)\b", message, re.I)
        if not match:
            match = re.search(r"(?:modo\s+|[·(]\s*)(CMYK|RGB)\b", text, re.I)
        if match:
            details["colorspace"] = match[1].upper()
    match = re.search(r"(\d+)\s*[×x]\s*(\d+)\s*px", message, re.I)
    if match:
        details["width_px"], details["height_px"] = map(int, match.groups())
    match = re.search(r"tama[ñn]o colocado:\s*([\d.,]+\s*[×x]\s*[\d.,]+\s*mm)", message, re.I)
    if match:
        details["placed_mm"] = match[1]
    return details


def collect_report_image_issues(job_data):
    """Return affected placements, keeping color and resolution on the same row.

    Image identity is page/index, because one XObject can be painted repeatedly
    at different sizes. Unknown placements remain explicit rather than guessed.
    Historical has_* correction flags never suppress current image findings.
    """
    summary = job_data.get("job_summary") or {}
    inventory = [dict(image, bbox=image.get("bbox") or _transform_bbox(image.get("transform")))
                 for image in summary.get("images_inventory", []) if isinstance(image, dict)]
    target = _number(summary.get("target_dpi", 300))
    family = str(summary.get("required_color_family", "CMYK")).upper()
    indexed = {(_positive_int(image.get("page")), _positive_int(image.get("index"))): image
               for image in inventory if _positive_int(image.get("page")) and _positive_int(image.get("index"))}
    rows = {}
    findings = [finding for finding in job_data.get("findings") or [] if isinstance(finding, dict)]
    current_rules = {finding.get("rule_id") for finding in findings}
    low_count = _number(summary.get("low_res_images"))
    color_count = _number(summary.get("non_cmyk_images"))
    fallback_resolution = (low_count or 0) > 0 or (low_count is None and _RESOLUTION in current_rules)
    fallback_color = ((color_count or 0) > 0
                      or (color_count is None and _COLOR in current_rules)
                      or (family == "RGB" and _COLOR in current_rules))

    def row_for(page, index, key, details=None):
        if key not in rows:
            row = {field: None for field in _FIELDS}
            row.update(page=page, index=index, target_dpi=target, issues=[], severity="WARNING", _rules=set())
            rows[key] = row
        row = rows[key]
        for field in _FIELDS:
            if details and details.get(field) is not None:
                row[field] = details[field]
        return row

    def add(row, rule, label, severity="WARNING"):
        if rule not in row["_rules"]:
            row["issues"].append(label)
            row["_rules"].add(rule)
        if severity in ("ERROR", "CRITICAL"):
            row["severity"] = "ERROR"

    for position, finding in enumerate(findings):
        rule = finding.get("rule_id")
        if rule not in (_RESOLUTION, _COLOR):
            continue
        legacy = _legacy_details(finding)
        page = _positive_int(finding.get("page")) or _positive_int(legacy.get("page"))
        index = (_positive_int(finding.get("image_index")) or _positive_int(finding.get("index"))
                 or _positive_int(legacy.get("image_index")))
        key = (page, index) if page and index else ("finding", position)
        details = dict(legacy)
        details.update(indexed.get((page, index), {}))
        details.update({field: finding[field] for field in _FIELDS if finding.get(field) is not None})
        row = row_for(page, index, key, details)
        label = finding.get("title") or ("Resolución de imagen por revisar" if rule == _RESOLUTION else "Color de imagen por revisar")
        add(row, rule, label, finding.get("severity"))

    for position, image in enumerate(inventory):
        page, index = _positive_int(image.get("page")), _positive_int(image.get("index"))
        key = (page, index) if page and index else ("inventory", position)
        dpi = _number(image.get("effective_dpi"))
        image_target = (_number(rows.get(key, {}).get("target_dpi"))
                        or _number(image.get("target_dpi")) or target)
        low = fallback_resolution and dpi is not None and image_target is not None and 0 < dpi < image_target
        colorspace = str(image.get("colorspace") or "").upper()
        cmyk = image.get("is_cmyk") is True or "CMYK" in colorspace
        gray = image.get("is_gray") is True or any(label in colorspace for label in ("GRAY", "GRIS"))
        rgb = image.get("is_rgb") is True or "RGB" in colorspace
        wrong_color = fallback_color and ((family == "CMYK" and rgb) or (family == "RGB" and cmyk))
        if not low and not wrong_color:
            continue
        if key in rows:
            row = rows[key]
            for field in _FIELDS:
                if row.get(field) is None and image.get(field) is not None:
                    row[field] = image[field]
        else:
            row = row_for(page, index, key, image)
        if row["target_dpi"] is None:
            row["target_dpi"] = image_target
        if low:
            severity = "ERROR" if (_number(summary.get("min_bleed_req_mm")) or 0) > 0.5 and dpi < 150 else "WARNING"
            add(row, _RESOLUTION, f"Resolución insuficiente ({dpi:g} ppp; mínimo {image_target:g} ppp)", severity)
        if wrong_color and not gray:
            add(row, _COLOR, f"Imagen en modo {image.get('colorspace') or 'desconocido'} (se requiere {family})")

    for rule, count, label in (
        (_RESOLUTION, summary.get("low_res_images"), "Resolución insuficiente"),
        (_COLOR, summary.get("non_cmyk_images"), "Color de imagen por revisar"),
    ):
        if (_number(count) or 0) > 0 and not any(rule in row["_rules"] for row in rows.values()):
            row = row_for(None, None, ("unidentified", rule))
            add(row, rule, f"{label}: {count} imágenes sin identificar")

    result = list(rows.values())
    for row in result:
        row.pop("_rules")
    return sorted(result, key=lambda row: (row["page"] is None, row["page"] or 0,
                                           row["index"] is None, row["index"] or 0))
