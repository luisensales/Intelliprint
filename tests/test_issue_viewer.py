"""Issue navigation always points to the current PDF and its visible coordinates."""

import io
import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pikepdf
import pymupdf
from PIL import Image

import app
from document_identity import sha256_file
from issue_viewer import normalized_regions
import test_regressions as base


class IssueViewerTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp

    def fixture(self, rotation=0, crop=False, unit=1):
        job_id = "viewer_job"
        folder = self.uploads / job_id
        folder.mkdir(exist_ok=True)
        source = folder / "source.pdf"
        image = io.BytesIO()
        Image.new("RGB", (120, 60), (240, 20, 40)).save(image, format="PNG")
        with pymupdf.open() as doc:
            page = doc.new_page(width=400, height=300)
            xref = page.insert_image(pymupdf.Rect(40, 80, 100, 110), stream=image.getvalue())
            page.insert_image(pymupdf.Rect(160, 100, 280, 160), xref=xref)
            doc.save(source)
        with pikepdf.open(source, allow_overwriting_input=True) as doc:
            doc.pages[0].Rotate = rotation
            doc.pages[0].UserUnit = unit
            if crop:
                doc.pages[0].CropBox = [20, 30, 320, 230]
            doc.save(source)
        with pymupdf.open(source) as doc:
            images = doc[0].get_image_info(xrefs=True)
            inventory = [dict(page=1, index=i + 1, bbox=list(im["bbox"]),
                              transform=list(im["transform"]), xref=im["xref"],
                              effective_dpi=72, colorspace="RGB") for i, im in enumerate(images)]
        findings = [{"rule_id": "PRINT_IMAGE_EFFECTIVE_PPI", "severity": "ERROR", "page": 1,
                     "image_index": 2, "bbox": inventory[1]["bbox"],
                     "title": "Resolución insuficiente (72 ppp · RGB)",
                     "message": "Imagen 2 en pág 1: resolución insuficiente."},
                    {"rule_id": "DOCUMENT_OUTPUT_ICC", "severity": "ERROR", "page": 1,
                     "title": "Perfil de salida no declarado", "message": "Revisar el perfil documental."}]
        report = {"job_meta": {"job_id": job_id, "pdf_path": str(source), "filename": "source.pdf",
                                "current_sha256": sha256_file(source)},
                  "job_summary": {"pages": 1, "images_inventory": inventory, "target_dpi": 300},
                  "findings": findings}
        self.save(report)
        return report, source

    def save(self, report):
        (self.jobs / (report["job_meta"]["job_id"] + ".json")).write_text(
            json.dumps(report), encoding="utf-8")

    def inspect(self, report, **params):
        return self.client.get("/api/issue-viewer/" + report["job_meta"]["job_id"], params=params)

    def test_image_occurrence_and_render_are_bound_to_current_pdf(self):
        report, source = self.fixture()
        response = self.inspect(report, finding_index=0, sha256=sha256_file(source))
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["location_status"], "exact")
        self.assertEqual(data["finding"]["image_index"], 2)
        self.assertEqual(data["regions"], [{"x": .4, "y": 1/3, "width": .3, "height": .2}])
        self.assertEqual(data["sha256"], sha256_file(source))
        self.assertEqual(data["page"], 1)
        rendered = self.client.get(data["render_url"])
        self.assertEqual(rendered.status_code, 200, rendered.text[:100] if rendered.status_code != 200 else "")
        self.assertEqual(rendered.headers["content-type"], "image/png")
        self.assertEqual(rendered.headers["x-pdf-sha256"], data["sha256"])
        self.assertIn("no-store", rendered.headers["cache-control"])
        with Image.open(io.BytesIO(rendered.content)) as image:
            self.assertAlmostEqual(image.width / image.height, 4/3, delta=.01)

    def test_document_level_finding_never_invents_an_object_region(self):
        report, _ = self.fixture()
        response = self.inspect(report, finding_index=1)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["location_status"], "page")
        self.assertEqual(response.json()["regions"], [])

    def test_rotation_crop_and_userunit_match_physical_display(self):
        report, source = self.fixture(rotation=270, crop=True, unit=2)
        response = self.inspect(report, finding_index=0)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual((data["width"], data["height"]), (400, 600))
        # CropBox starts at x=20,y=70 in the unrotated MuPDF page.
        region = data["regions"][0]
        for key, expected in {"x": .15, "y": 2/15, "width": .3, "height": .4}.items():
            self.assertAlmostEqual(region[key], expected, places=5)
        rendered = self.client.get(data["render_url"])
        with Image.open(io.BytesIO(rendered.content)) as image:
            self.assertAlmostEqual(image.width / image.height, 2/3, delta=.01)
            point = (int((region["x"] + region["width"] / 2) * image.width),
                     int((region["y"] + region["height"] / 2) * image.height))
            red, green, blue = image.convert("RGB").getpixel(point)
            self.assertGreater(red, 200)
            self.assertLess(green, 60)

    def test_legacy_placement_index_is_located_without_structured_bbox(self):
        report, _ = self.fixture()
        del report["findings"][0]["bbox"]
        del report["findings"][0]["image_index"]
        self.save(report)
        response = self.inspect(report)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["regions"][0]["x"], .4)

    def test_changed_or_mismatched_pdf_does_not_receive_old_overlays(self):
        report, source = self.fixture()
        data = self.inspect(report).json()
        self.assertEqual(self.inspect(report, sha256="0" * 64).status_code, 409)
        source.write_bytes(base.sample_pdf(False))
        self.assertEqual(self.inspect(report).status_code, 409)
        self.assertEqual(self.client.get(data["render_url"]).status_code, 409)

    def test_new_cumulative_pdf_is_used_instead_of_original(self):
        report, _ = self.fixture()
        fixed = self.jobs / "viewer_job_fixed.pdf"
        with pymupdf.open() as doc:
            doc.new_page(width=600, height=450)
            doc.save(fixed)
        report["job_meta"].update(last_fixed_pdf_path=str(fixed), current_sha256=sha256_file(fixed))
        report["findings"] = [report["findings"][1]]
        self.save(report)
        data = self.inspect(report).json()
        self.assertEqual((data["width"], data["height"]), (600, 450))
        self.assertEqual(data["sha256"], sha256_file(fixed))

    def test_invalid_indices_pages_dpi_hashes_and_paths_are_rejected(self):
        report, _ = self.fixture()
        self.assertEqual(self.inspect(report, finding_index=-1).status_code, 422)
        self.assertEqual(self.inspect(report, finding_index=20).status_code, 404)
        self.assertEqual(self.inspect(report, sha256="../../private").status_code, 422)
        url = "/api/issue-viewer/viewer_job/render"
        digest = report["job_meta"]["current_sha256"]
        for params in ({"page": 0, "sha256": digest}, {"page": 2, "sha256": digest},
                       {"sha256": digest, "dpi": 1000}, {"sha256": digest, "dpi": "nan"},
                       {"page": 1}, {"sha256": "bad"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(url, params=params).status_code, 422)
        report["job_meta"]["pdf_path"] = str(self.root / "outside.pdf")
        Path(report["job_meta"]["pdf_path"]).write_bytes(base.sample_pdf(False))
        self.save(report)
        self.assertEqual(self.inspect(report).status_code, 422)

    def test_normalization_clips_and_ignores_nonfinite_locations(self):
        with pymupdf.open(stream=base.sample_pdf(False), filetype="pdf") as doc:
            regions = normalized_regions(doc[0], [[-20, -20, 40, 50], [0, 0, float("inf"), 30], [400, 400, 420, 420]])
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["x"], 0)
        self.assertEqual(regions[0]["y"], 0)


if __name__ == "__main__":
    unittest.main()
