"""Affected image identification stays consistent across current and old jobs."""

from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pikepdf
import pymupdf

from preflight_engine import IntelliPrintEngine
from report_images import collect_report_image_issues


RESOLUTION = "PRINT_IMAGE_EFFECTIVE_PPI"
COLOR = "SOURCE_COLOR_DIAGNOSTIC"


def image(page=1, index=1, dpi=121, colorspace="CMYK", xref=7):
    return {"page": page, "index": index, "effective_dpi": dpi, "colorspace": colorspace,
            "width_px": 200, "height_px": 100, "placed_mm": "42 × 21 mm", "xref": xref,
            "transform": [120, 0, 0, 60, 40, 40]}


def finding(rule=RESOLUTION, page=1, index=1, severity="ERROR", **extra):
    return {"rule_id": rule, "page": page, "image_index": index, "severity": severity,
            "title": "Resolución insuficiente" if rule == RESOLUTION else "Imagen en modo RGB",
            **extra}


def report(findings=(), inventory=(), low=0, color=0, **summary):
    return {"job_meta": {"has_cmyk_converted": True}, "findings": list(findings),
            "job_summary": {"target_dpi": 300, "required_color_family": "CMYK",
                            "min_bleed_req_mm": 3, "low_res_images": low,
                            "non_cmyk_images": color, "images_inventory": list(inventory), **summary}}


class ReportImageIdentificationTests(unittest.TestCase):
    def test_color_and_resolution_on_one_placement_make_one_row(self):
        data = report([
            finding(effective_dpi=121, target_dpi=300, colorspace="RGB"),
            finding(COLOR, severity="WARNING", colorspace="RGB"),
        ], [image(colorspace="RGB")], low=1, color=1)
        rows = collect_report_image_issues(data)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["page"], row["index"], row["effective_dpi"], row["target_dpi"]), (1, 1, 121, 300))
        self.assertEqual(row["severity"], "ERROR")
        self.assertEqual(len(row["issues"]), 2)
        self.assertEqual(row["bbox"], [40, 40, 160, 100])
        self.assertEqual((row["width_px"], row["height_px"], row["xref"]), (200, 100, 7))

    def test_legacy_image_number_joins_inventory_and_keeps_thumbnail_location(self):
        data = report([{"page": 2, "rule_id": RESOLUTION, "severity": "ERROR",
                        "title": "Resolución insuficiente (128 ppp · Escala de grises)",
                        "message": "Imagen 3 en pág 2: resolución efectiva de 128 ppp. El perfil exige un mínimo de 200 ppp."}],
                      [image(page=2, index=3, dpi=128, colorspace="Escala de grises")], low=1, target_dpi=200)
        row, = collect_report_image_issues(data)
        self.assertEqual((row["page"], row["index"], row["effective_dpi"], row["target_dpi"]), (2, 3, 128, 200))
        self.assertEqual(row["colorspace"], "Escala de grises")
        self.assertEqual(row["bbox"], [40, 40, 160, 100])

    def test_reused_xobject_is_identified_by_each_placement_not_xref(self):
        data = report(inventory=[image(index=1, dpi=600), image(index=2, dpi=120)], low=1)
        rows = collect_report_image_issues(data)
        self.assertEqual([(row["page"], row["index"]) for row in rows], [(1, 2)])
        self.assertEqual(rows[0]["effective_dpi"], 120)
        self.assertEqual(rows[0]["severity"], "ERROR")

    def test_inventory_fallback_combines_rgb_and_low_resolution_without_flags_hiding_them(self):
        data = report(inventory=[image(colorspace="RGB")], low=1, color=1)
        row, = collect_report_image_issues(data)
        self.assertEqual(len(row["issues"]), 2)
        self.assertEqual(row["colorspace"], "RGB")
        self.assertEqual(row["index"], 1)

    def test_unknown_index_is_retained_without_guessing_an_inventory_identity(self):
        data = report([{"rule_id": RESOLUTION, "page": 1, "severity": "WARNING",
                        "title": "Resolución de imagen no verificable",
                        "message": "No se pudo verificar; mínimo de 300 ppp."}],
                      [image(index=1, dpi=300), image(index=2, dpi=300)])
        row, = collect_report_image_issues(data)
        self.assertEqual(row["page"], 1)
        self.assertIsNone(row["index"])
        self.assertIsNone(row["effective_dpi"])
        self.assertIsNone(row["bbox"])
        self.assertEqual(row["severity"], "WARNING")

    def test_legacy_message_can_supply_details_without_inventory(self):
        data = report([{"rule_id": RESOLUTION, "severity": "ERROR",
                        "title": "Resolución insuficiente (121 ppp · CMYK)",
                        "message": "Imagen 2 en pág 4: espacio CMYK, resolución efectiva de 121 ppp (1908 × 1080 px, tamaño colocado: 400.5 × 226.7 mm). El perfil exige un mínimo de 300 ppp."}])
        row, = collect_report_image_issues(data)
        self.assertEqual((row["page"], row["index"]), (4, 2))
        self.assertEqual((row["width_px"], row["height_px"]), (1908, 1080))
        self.assertEqual(row["placed_mm"], "400.5 × 226.7 mm")
        self.assertEqual(row["colorspace"], "CMYK")
        self.assertEqual(row["effective_dpi"], 121)

    def test_all_four_transform_corners_determine_a_rotated_thumbnail_bbox(self):
        placed = image()
        placed["transform"] = [0, 72, -144, 0, 200, 10]
        row, = collect_report_image_issues(report([finding()], [placed]))
        self.assertEqual(row["bbox"], [56, 10, 200, 82])

    def test_affected_rows_are_sorted_by_page_and_placement(self):
        rows = collect_report_image_issues(report([
            finding(page=3, index=2), finding(page=1, index=4), finding(page=1, index=2),
        ]))
        self.assertEqual([(row["page"], row["index"]) for row in rows], [(1, 2), (1, 4), (3, 2)])

    def test_unaffected_images_and_obsolete_inventory_are_not_reported(self):
        self.assertEqual(collect_report_image_issues(report(inventory=[image(dpi=300), image(index=2, dpi=400, colorspace="Escala de grises")])), [])
        # A verified zero count must not revive stale RGB/low-resolution inventory.
        self.assertEqual(collect_report_image_issues(report(inventory=[image(dpi=121, colorspace="RGB")])), [])

    def test_summary_only_issue_is_visible_but_has_no_invented_page_or_index(self):
        rows = collect_report_image_issues(report(low=2))
        row, = rows
        self.assertIsNone(row["page"])
        self.assertIsNone(row["index"])
        self.assertIn("2 imágenes sin identificar", row["issues"][0])

    def test_collecting_rows_does_not_mutate_persisted_analysis(self):
        data = report([finding()], [image()], low=1)
        before = deepcopy(data)
        collect_report_image_issues(data)
        self.assertEqual(data, before)


class PreflightImageIdentityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.source = Path(temp.name) / "source.pdf"

    def test_preflight_emits_structured_identity_for_color_and_resolution(self):
        with pikepdf.new() as pdf:
            page = pdf.add_blank_page(page_size=(700, 700))
            raster = pdf.make_stream(b'\x80' * (200 * 100 * 3))
            raster.Type, raster.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
            raster.Width, raster.Height, raster.BitsPerComponent = 200, 100, 8
            raster.ColorSpace = pikepdf.Name.DeviceRGB
            page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im=raster))
            page.Contents = pdf.make_stream(b'q 48 0 0 24 40 40 cm /Im Do Q q 120 0 0 60 100 100 cm /Im Do Q')
            pdf.save(self.source)
        result = IntelliPrintEngine().run_preflight(self.source)
        inventory = result["job_summary"]["images_inventory"]
        resolution, = [f for f in result["findings"] if f["rule_id"] == RESOLUTION]
        self.assertEqual(resolution["image_index"], 2)
        self.assertEqual(resolution["effective_dpi"], 120)
        self.assertEqual(resolution["target_dpi"], 300)
        self.assertEqual(resolution["colorspace"], "RGB")
        self.assertEqual(resolution["bbox"], inventory[1]["bbox"])
        rows = collect_report_image_issues(result)
        self.assertEqual([(row["index"], len(row["issues"])) for row in rows], [(1, 1), (2, 2)])
        self.assertEqual(rows[0]["xref"], rows[1]["xref"])

    def test_unverifiable_placement_also_has_structured_identity(self):
        with pymupdf.open() as pdf:
            pdf.new_page(width=200, height=200)
            pdf.save(self.source)
        fake_image = {"xref": 0, "colorspace": 3, "width": 20, "height": 10,
                      "transform": [0, 0, 0, 0, 30, 30], "bbox": [30, 30, 30, 30]}
        with patch.object(pymupdf.Page, "get_image_info", return_value=[fake_image]):
            result = IntelliPrintEngine().run_preflight(self.source)
        resolution, = [f for f in result["findings"] if f["rule_id"] == RESOLUTION]
        self.assertEqual(resolution["image_index"], 1)
        self.assertEqual(resolution["colorspace"], "RGB")
        self.assertEqual(resolution["bbox"], [30, 30, 30, 30])
        row, = collect_report_image_issues(result)
        self.assertEqual(row["index"], 1)
        self.assertEqual(len(row["issues"]), 2)


if __name__ == "__main__":
    unittest.main()
