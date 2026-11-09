"""Run with: python -m unittest discover -s tests -v"""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from PIL import Image
from fastapi.testclient import TestClient

import app
import color_converter
import hotfolder_engine
import profile_manager
from upload_security import validate_pdf_filename


def sample_pdf(with_image=True):
    with pymupdf.open() as doc:
        page = doc.new_page(width=300, height=300)
        page.insert_text((40, 40), "Prueba de conversion")
        if with_image:
            image = io.BytesIO()
            Image.new("RGB", (20, 20), (255, 0, 0)).save(image, format="PNG")
            page.insert_image(pymupdf.Rect(50, 50, 200, 200), stream=image.getvalue())
        return doc.tobytes()


class RegressionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.uploads = self.root / "uploads"
        self.jobs = self.root / "jobs"
        self.uploads.mkdir()
        self.jobs.mkdir()
        for module in (app, hotfolder_engine):
            for name, value in (("UPLOAD_DIR", self.uploads), ("JOBS_DIR", self.jobs)):
                patcher = patch.object(module, name, value)
                patcher.start()
                self.addCleanup(patcher.stop)
        patcher = patch.object(profile_manager, "CUSTOM_PROFILES_FILE", self.root / "profiles.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)

    def upload(self, with_image=True):
        response = self.client.post(
            "/api/check", files={"file": ("documento.pdf", sample_pdf(with_image), "application/pdf")}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_rejects_paths_for_both_operating_systems(self):
        for name in ("../escape.pdf", "..\\escape.pdf", "/escape.pdf", "C:\\escape.pdf", "a\x00.pdf", None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_pdf_filename(name)
        self.assertEqual(validate_pdf_filename("Trabajo final.PDF"), "Trabajo final.PDF")

    def test_all_upload_routes_reject_traversal_before_writing(self):
        for route, field in (("/api/check", "file"), ("/api/inspect-pdf", "file"), ("/api/batch/upload", "files")):
            with self.subTest(route=route):
                response = self.client.post(route, files={field: ("../escape.pdf", b"%PDF", "application/pdf")})
                self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(list(self.uploads.iterdir()), [])
        self.assertFalse((self.root / "escape.pdf").exists())
        with self.assertRaises(ValueError):
            hotfolder_engine.process_batch_upload([("..\\escape.pdf", b"%PDF")])

    def test_valid_upload_retains_display_name_and_uses_internal_name(self):
        report = self.upload()
        meta = report["job_meta"]
        self.assertEqual(meta["filename"], "documento.pdf")
        self.assertEqual(Path(meta["pdf_path"]).name, "source.pdf")
        self.assertTrue(Path(meta["pdf_path"]).is_relative_to(self.uploads))

    def test_batch_upload_uses_internal_name(self):
        response = self.client.post("/api/batch/upload", files={"files": ("lote.pdf", sample_pdf(), "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        job_id = response.json()["jobs"][0]["job_id"]
        saved = json.loads((self.jobs / f"{job_id}.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["job_meta"]["filename"], "lote.pdf")
        self.assertEqual(Path(saved["job_meta"]["pdf_path"]).name, "source.pdf")

    def test_zero_margins_survive_create_update_and_reload(self):
        created = self.client.post("/api/profiles/custom", json={"name": "Pantalla", "min_bleed_mm": 0, "safety_margin_mm": 0})
        self.assertEqual(created.status_code, 200)
        profile = created.json()["profile"]
        self.assertEqual(profile["min_bleed_mm"], 0)
        self.assertEqual(profile["safety_margin_mm"], 0)
        url = f'/api/profiles/custom/{profile["id"]}'
        self.client.put(url, json={"min_bleed_mm": 5, "safety_margin_mm": 5})
        self.client.put(url, json={"min_bleed_mm": 0, "safety_margin_mm": 0})
        loaded = profile_manager.get_profile_by_id(profile["id"])
        self.assertEqual(loaded["min_bleed_mm"], 0)
        self.assertEqual(loaded["safety_margin_mm"], 0)

    def test_image_conversion_preserves_unresolved_errors(self):
        original = self.upload()
        job_id = original["job_meta"]["job_id"]
        response = self.client.post(f"/api/convert-to-cmyk/{job_id}")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["images_converted"], 1)
        self.assertEqual(result["triple_result"]["technical"]["status"], "FAIL")
        self.assertIn("PRINT_IMAGE_EFFECTIVE_PPI", {f["rule_id"] for f in result["findings"]})
        self.assertNotIn("SOURCE_COLOR_DIAGNOSTIC", {f["rule_id"] for f in result["findings"]})
        verified = app.engine.run_preflight(str(self.jobs / f"{job_id}_cmyk_converted.pdf"))
        self.assertEqual(result["findings"], verified["findings"])
        self.assertEqual(result["report"]["job_summary"], verified["job_summary"])

    def test_failed_conversion_does_not_change_persisted_verdict(self):
        report = self.upload()
        job_id = report["job_meta"]["job_id"]
        before = (self.jobs / f"{job_id}.json").read_bytes()
        with patch.object(color_converter, "_image_to_cmyk_bytes", side_effect=ValueError("conversion failed")):
            response = self.client.post(f"/api/convert-to-cmyk/{job_id}")
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual((self.jobs / f"{job_id}.json").read_bytes(), before)

    def test_batch_rechecks_findings_instead_of_erasing_them(self):
        report = self.upload()
        job_id = report["job_meta"]["job_id"]
        # Isolate CMYK in the batch so other fixes cannot hide a failed conversion.
        options = {name: "false" for name in ("trapping", "hairlines", "icc", "geometry", "fonts", "tac")}
        with patch.object(app, "convert_rgb_images_to_cmyk", return_value={"success": False, "errors": ["conversion failed"]}):
            response = self.client.post(f"/api/batch-fix/{job_id}", params=options)
        self.assertEqual(response.status_code, 200, response.text)
        saved = json.loads((self.jobs / f"{job_id}.json").read_text(encoding="utf-8"))
        self.assertIn("SOURCE_COLOR_DIAGNOSTIC", {f["rule_id"] for f in saved["findings"]})
        self.assertEqual(saved["triple_result"]["technical"]["status"], "FAIL")
        self.assertGreater(response.json()["errors_count"], 0)

    def test_unverifiable_result_cannot_replace_analysis(self):
        report = self.upload()
        previous = json.dumps(report, sort_keys=True)
        with patch.object(app.engine, "run_preflight", return_value={"error": "invalid PDF", "findings": []}):
            with self.assertRaises(app.HTTPException):
                app.refresh_job_analysis(report, "invalid.pdf")
        self.assertEqual(json.dumps(report, sort_keys=True), previous)


if __name__ == "__main__":
    unittest.main()
