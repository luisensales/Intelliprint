"""Tests for Option 4 UX & Institutional polish (/api/health and institutional UI markers)."""

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

import app


class UXAndInstitutionalTests(unittest.TestCase):
    def test_health_endpoint_returns_service_version_and_db_status(self):
        client = TestClient(app.app)
        resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "IntelliPrint")
        self.assertIn("version", data)
        self.assertIsInstance(data["db_status"], dict)
        self.assertIn("backend", data["db_status"])

    def test_index_contains_institutional_modal_and_toast_container(self):
        html = Path("static/index.html").read_text(encoding="utf-8")
        self.assertIn('id="shortcutsModal"', html)
        self.assertIn('id="toastContainer"', html)
        self.assertIn("Probar con Reto de Muestra", html)
        self.assertIn("@media print", html)
        self.assertIn('id="langSwitcherPill"', html)
        self.assertIn('data-lang-btn="eu"', html)
        self.assertIn('data-lang-btn="en"', html)

    def test_manual_supports_instant_search_and_trilingual_views(self):
        client = TestClient(app.app)
        resp_es = client.get("/manual")
        self.assertEqual(resp_es.status_code, 200)
        self.assertIn('id="manualSearchInput"', resp_es.text)
        self.assertIn("Buscador rápido:", resp_es.text)

        resp_eu = client.get("/manual?lang=eu")
        self.assertEqual(resp_eu.status_code, 200)
        self.assertIn("Bilatzaile azkarra:", resp_eu.text)

        resp_en = client.get("/manual?lang=en")
        self.assertEqual(resp_en.status_code, 200)
        self.assertIn("Quick search:", resp_en.text)

    def test_client_report_pdf_supports_es_eu_en_languages(self):
        import tempfile
        import pymupdf
        from client_report_generator import generate_client_educational_report_pdf

        sample_job = {
            "job_meta": {"job_id": "test-i18n-01", "filename": "folleto.pdf", "profile_id": "OFFSET_300"},
            "job_summary": {"pages": 2, "required_color_family": "CMYK", "target_dpi": 300},
            "findings": [
                {"rule_id": "BLEED_GEOMETRY_3MM", "severity": "ERROR", "page": 1, "message": "Sin sangrado"}
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            out_eu = Path(tmp) / "guide_eu.pdf"
            generate_client_educational_report_pdf(sample_job, out_eu, lang="eu")
            with pymupdf.open(out_eu) as doc_eu:
                txt_eu = "\n".join(p.get_text() for p in doc_eu)
            self.assertIn("AZKEN ARTEAREN GIDA", txt_eu)
            self.assertIn("Perimetroko odoldura falta da", txt_eu)

            out_en = Path(tmp) / "guide_en.pdf"
            generate_client_educational_report_pdf(sample_job, out_en, lang="en")
            with pymupdf.open(out_en) as doc_en:
                txt_en = "\n".join(p.get_text() for p in doc_en)
            self.assertIn("FINAL ARTWORK GUIDE", txt_en)
            self.assertIn("Missing Perimeter Bleed", txt_en)


if __name__ == "__main__":
    unittest.main()

