"""Finding regions refer to actual MuPDF objects, not inferred page contents."""

import io
import tempfile
import unittest
from pathlib import Path

import pikepdf
import pymupdf
from PIL import Image

from issue_locations import locate_finding


class FindingLocationsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "source.pdf"

    def image_pdf(self, rotation=0, unit=1, crop=False):
        image = io.BytesIO()
        Image.new("RGB", (40, 20), (220, 40, 20)).save(image, format="PNG")
        with pymupdf.open() as doc:
            page = doc.new_page(width=300, height=200)
            xref = page.insert_image(pymupdf.Rect(70, 50, 170, 100), stream=image.getvalue())
            page.insert_image(pymupdf.Rect(180, 110, 240, 140), xref=xref)
            doc.new_page(width=300, height=200)
            doc.save(self.path)
        with pikepdf.open(self.path, allow_overwriting_input=True) as doc:
            page = doc.pages[0]
            if crop:
                page.CropBox = [50, 20, 250, 180]
                page.TrimBox = [60, 30, 240, 170]
            page.Rotate, page.UserUnit = rotation, unit
            doc.save(self.path)

    def font_pdf(self):
        with pymupdf.open() as doc:
            page = doc.new_page(width=300, height=240)
            page.insert_text((30, 40), "First regular line", fontname="helv")
            page.insert_text((30, 80), "Second regular line", fontname="helv")
            page.insert_text((30, 120), "Bold sibling must stay out", fontname="hebo")
            page.insert_text((30, 160), "Other family", fontname="cour")
            doc.save(self.path)

    def test_reused_image_selects_only_its_requested_occurrence(self):
        self.image_pdf()
        with pymupdf.open(self.path) as doc:
            page = doc[0]
            images = page.get_image_info(xrefs=True)
            self.assertEqual(images[0]["xref"], images[1]["xref"])
            finding = {"rule_id": "PRINT_IMAGE_EFFECTIVE_PPI", "page": 1, "image_index": 2}
            self.assertEqual(locate_finding(page, finding, {}), [list(images[1]["bbox"])])

    def test_old_message_and_transform_inventory_use_the_placement_ordinal(self):
        self.image_pdf()
        with pymupdf.open(self.path) as doc:
            page = doc[0]
            image = page.get_image_info()[1]
            inventory = {"images_inventory": [{"page": 1, "index": 2, "transform": list(image["transform"])}]}
            finding = {"rule_id": "SOURCE_COLOR_DIAGNOSTIC", "page": 1, "message": "Imagen 2 en pág 1: espacio RGB."}
            self.assertEqual(locate_finding(page, finding, inventory), [list(image["bbox"])])

    def test_inline_image_is_located_without_an_xref(self):
        with pikepdf.new() as doc:
            page = doc.add_blank_page(page_size=(200, 200))
            page.Contents = doc.make_stream(b'q 72 0 0 36 10 20 cm BI /W 1 /H 1 /BPC 8 /CS /G ID \x80 EI Q')
            doc.save(self.path)
        with pymupdf.open(self.path) as doc:
            finding = {"rule_id": "PRINT_IMAGE_EFFECTIVE_PPI", "message": "No se pudo medir la colocación 1 de la página 1."}
            self.assertEqual(locate_finding(doc[0], finding, {}), [list(doc[0].get_image_info()[0]["bbox"])])

    def test_bbox_remains_unrotated_crop_relative_and_physically_scaled(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                self.image_pdf(rotation=rotation, unit=2, crop=True)
                with pymupdf.open(self.path) as doc:
                    page = doc[0]
                    finding = {"rule_id": "PRINT_IMAGE_EFFECTIVE_PPI", "page": 1, "image_index": 1}
                    expected = [40, 60, 240, 160]
                    self.assertEqual(locate_finding(page, finding, {}), [expected])
                    finding["bbox"] = expected
                    self.assertEqual(locate_finding(page, finding, {}), [expected])

    def test_font_finding_returns_all_spans_of_only_the_named_font(self):
        self.font_pdf()
        with pymupdf.open(self.path) as doc:
            page = doc[0]
            finding = {"rule_id": "USED_FONTS_EMBEDDED", "page": 1, "title": "Fuente no incrustada: Helvetica"}
            regions = locate_finding(page, finding, {})
            self.assertEqual(len(regions), 2)
            blocks = page.get_text("dict")["blocks"]
            expected = [list(span["bbox"]) for block in blocks for line in block.get("lines", [])
                        for span in line["spans"] if span["font"] == "Helvetica"]
            self.assertEqual(regions, expected)

    def test_font_subset_and_resource_aliases_match_without_matching_bold(self):
        self.font_pdf()
        with pymupdf.open(self.path) as doc:
            page = doc[0]
            alias = next(font[4] for font in page.get_fonts() if font[3] == "Helvetica")
            for name in ("ABCDEF+Helvetica", alias):
                with self.subTest(name=name):
                    self.assertEqual(len(locate_finding(page, {"rule_id": "USED_FONTS_EMBEDDED", "font_name": name}, {})), 2)
            self.assertEqual(locate_finding(page, {"rule_id": "USED_FONTS_EMBEDDED", "font_name": "Helvet"}, {}), [])

    def test_unknown_and_ambiguous_findings_do_not_guess_an_object(self):
        self.image_pdf()
        with pymupdf.open(self.path) as doc:
            page = doc[0]
            self.assertEqual(locate_finding(page, {"rule_id": "RICH_BLACK_SMALL_TEXT", "page": 1}, {}), [])
            self.assertEqual(locate_finding(page, {"rule_id": "PRINT_IMAGE_EFFECTIVE_PPI", "xref": 5}, {}), [])
            self.assertEqual(locate_finding(page, {"rule_id": "PRINT_IMAGE_EFFECTIVE_PPI", "image_index": 99}, {}), [])
            self.assertEqual(locate_finding(doc[1], {"rule_id": "OTHER", "page": 1, "bbox": [1, 2, 3, 4]}, {}), [])

    def test_structured_graphics_box_is_used_and_invalid_values_are_ignored(self):
        self.image_pdf()
        with pymupdf.open(self.path) as doc:
            finding = {"rule_id": "RICH_BLACK_SMALL_TEXT", "bbox": [12, 20, 90, 40]}
            self.assertEqual(locate_finding(doc[0], finding, {}), [[12, 20, 90, 40]])
            for bad in ([0, 0, float("nan"), 5], [0, 0, float("inf"), 5], [4, 4, 2, 2], [0, 0, 0, 4], "1,2,3,4"):
                finding["bbox"] = bad
                self.assertEqual(locate_finding(doc[0], finding, {}), [])

    def test_bleed_highlights_cut_boundaries_with_crop_rotation_and_userunit(self):
        self.image_pdf(rotation=270, unit=2, crop=True)
        with pymupdf.open(self.path) as doc:
            finding = {"rule_id": "BLEED_GEOMETRY_3MM", "page": 1}
            regions = locate_finding(doc[0], finding, {})
            self.assertEqual(len(regions), 4)
            self.assertEqual(regions[0][0], 20)
            self.assertEqual(regions[0][1], 20)
            self.assertEqual(regions[0][3], 300)
            finding["message"] = "Sangrado insuficiente en borde: izquierdo (0 mm), inferior (1 mm)."
            selected = locate_finding(doc[0], finding, {})
            self.assertEqual(selected, [regions[0], regions[3]])


if __name__ == "__main__":
    unittest.main()
