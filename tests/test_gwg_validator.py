"""Unit tests for GWG 2015 and ISO 15930 (PDF/X) Production Validation Engine."""

import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
import pymupdf

import app
import gwg_validator


class GwgValidatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.jobs_dir = Path(self.tmp.name) / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

        # Crear un PDF de prueba de 2 páginas con cajas y trazos
        self.test_pdf = self.jobs_dir / "test_doc.pdf"
        doc = pymupdf.open()
        p1 = doc.new_page(width=595.3, height=841.9)
        # Añadir un trazo fino
        shape = p1.new_shape()
        shape.draw_line(pymupdf.Point(50, 50), pymupdf.Point(200, 50))
        shape.finish(width=0.10, color=(0, 0, 0))
        shape.commit()

        p2 = doc.new_page(width=595.3, height=841.9)
        p2.insert_text(pymupdf.Point(72, 72), "Texto de prueba GWG", fontsize=12)
        doc.save(str(self.test_pdf))
        doc.close()

    def test_available_standards_catalog(self):
        stds = gwg_validator.get_available_standards()
        self.assertGreaterEqual(len(stds), 5)
        std_ids = [s["id"] for s in stds]
        self.assertIn("gwg_2015_sheetfed", std_ids)
        self.assertIn("pdfx_4_2010", std_ids)
        self.assertIn("pdfx_1a_2001", std_ids)
        self.assertIn("gwg_newspaper", std_ids)
        self.assertIn("gwg_packaging", std_ids)

    def test_validate_pdf_gwg_sheetfed(self):
        report = gwg_validator.validate_pdf_gwg(
            pdf_path=self.test_pdf,
            standard_id="gwg_2015_sheetfed",
            job_data={"analisis_tac": {"tac_maximo": 280}},
        )

        self.assertIn("overall_verdict", report)
        self.assertIn("score_percent", report)
        self.assertIn("stats", report)
        self.assertIn("checks", report)
        self.assertGreaterEqual(len(report["checks"]), 8)

        # Verificar estructura de evidencias de cada check
        for chk in report["checks"]:
            self.assertIn("id", chk)
            self.assertIn("category", chk)
            self.assertIn("title", chk)
            self.assertIn("status", chk)
            self.assertIn(chk["status"], ("PASS", "WARNING", "FAIL"))
            self.assertIn("standard_criterion", chk)
            self.assertIn("evidence", chk)
            self.assertIn("workshop_impact", chk)
            self.assertIn("action_required", chk)

        # Verificar que detectó el trazo fino (< 0.14 pt)
        hairline_chk = next((c for c in report["checks"] if c["id"] == "CHK_HAIRLINES"), None)
        self.assertIsNotNone(hairline_chk)
        self.assertEqual(hairline_chk["status"], "WARNING")

    def test_validate_pdf_gwg_pdfx_1a(self):
        report = gwg_validator.validate_pdf_gwg(
            pdf_path=self.test_pdf,
            standard_id="pdfx_1a_2001",
        )
        self.assertEqual(report["standard"]["id"], "pdfx_1a_2001")
        self.assertIn("overall_status", report)

    def test_generate_gwg_certificate_pdf(self):
        report = gwg_validator.validate_pdf_gwg(
            pdf_path=self.test_pdf,
            standard_id="gwg_2015_sheetfed",
        )
        job_data = {
            "job_meta": {
                "job_id": "test_gwg_01",
                "filename": "Catalogo_Oficial.pdf",
                "current_sha256": "e" * 64,
            }
        }
        cert_pdf = self.jobs_dir / "certificado.pdf"
        gwg_validator.generate_gwg_certificate_pdf(job_data, report, cert_pdf)

        self.assertTrue(cert_pdf.exists())
        self.assertGreater(cert_pdf.stat().st_size, 2000)

        with pymupdf.open(str(cert_pdf)) as doc:
            self.assertGreaterEqual(len(doc), 1)
            text = doc[0].get_text()
            self.assertIn("CERTIFICADO OFICIAL DE CONFORMIDAD", text)
            self.assertIn("test_gwg_01", text)
            self.assertIn("MATRIZ DE COMPROBACIONES PERICIALES", text)
            self.assertIn("VISTO BUENO DE PRODUCCIÓN", text)

    def test_api_endpoints_integration(self):
        orig_jobs = app.JOBS_DIR
        app.JOBS_DIR = self.jobs_dir
        try:
            client = TestClient(app.app)

            # 1. GET /api/validation/standards
            resp_stds = client.get("/api/validation/standards")
            self.assertEqual(resp_stds.status_code, 200)
            self.assertIn("standards", resp_stds.json())

            # 2. Setup job
            job_id = "test_val_job"
            job_manifest = {
                "job_meta": {
                    "job_id": job_id,
                    "filename": "Doc_Validacion.pdf",
                    "file_path": str(self.test_pdf),
                    "page_count": 2,
                    "current_sha256": "f" * 64,
                },
                "paginas": {"total_paginas": 2},
            }
            (self.jobs_dir / f"{job_id}.json").write_text(json.dumps(job_manifest), encoding="utf-8")

            # 3. POST /api/validation/verify/{job_id}
            resp_verify = client.post(
                f"/api/validation/verify/{job_id}",
                json={"standard_id": "gwg_2015_sheetfed"},
            )
            self.assertEqual(resp_verify.status_code, 200)
            data = resp_verify.json()
            self.assertIn("overall_verdict", data)
            self.assertIn("certificate_url", data)

            # 4. GET /api/validation/certificate/{job_id}
            resp_cert = client.get(f"/api/validation/certificate/{job_id}")
            self.assertEqual(resp_cert.status_code, 200)
            self.assertEqual(resp_cert.headers["content-type"], "application/pdf")
            self.assertGreater(len(resp_cert.content), 1000)
        finally:
            app.JOBS_DIR = orig_jobs

    def test_white_background_document_does_not_require_bleed(self):
        """Verifica que documentos con fondo blanco y sin elementos a ras de corte no exigen sangrado."""
        from preflight_engine import IntelliPrintEngine

        white_pdf = self.jobs_dir / "white_doc.pdf"
        doc = pymupdf.open()
        p = doc.new_page(width=595.3, height=841.9)
        # Añadir texto centrado con márgenes amplios (fondo blanco puro)
        p.insert_text(pymupdf.Point(100, 100), "Documento comercial con fondo blanco", fontsize=14)
        doc.save(str(white_pdf))
        doc.close()

        # 1. Preflight técnico
        engine = IntelliPrintEngine()
        preflight_report = engine.run_preflight(str(white_pdf), "OFFSET_300")
        bleed_findings = [f for f in preflight_report.get("findings", []) if "BLEED" in f.get("rule_id", "")]
        self.assertEqual(len(bleed_findings), 0, "No debe generar incidencias de sangrado en fondo blanco")
        self.assertEqual(preflight_report.get("job_summary", {}).get("bleed_status"), "NOT_REQUIRED")

        # 2. Validación GWG
        gwg_report = gwg_validator.validate_pdf_gwg(
            pdf_path=white_pdf,
            standard_id="gwg_2015_sheetfed",
            job_data=preflight_report
        )
        bleed_chk = next((c for c in gwg_report["checks"] if c["id"] == "CHK_BLEED"), None)
        self.assertIsNotNone(bleed_chk)
        self.assertEqual(bleed_chk["status"], "PASS")
        self.assertIn("no requerido", bleed_chk["evidence"]["summary"].lower())


if __name__ == "__main__":
    unittest.main()

