"""Unit tests for Production Orders, Recipes, Job Ticket generation and Tool orchestration."""

import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
import pymupdf

import app
import production_order


class ProductionOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.jobs_dir = Path(self.tmp.name) / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def test_catalogs_structure(self):
        catalogs = production_order.get_production_catalogs()
        self.assertIn("products", catalogs)
        self.assertIn("machines", catalogs)
        self.assertIn("papers", catalogs)
        self.assertIn("finishings", catalogs)
        self.assertGreaterEqual(len(catalogs["products"]), 5)
        self.assertGreaterEqual(len(catalogs["machines"]), 4)

    def test_propose_booklet_recipe(self):
        recipe = production_order.propose_production_recipe(
            product_id="catalogo_grapado",
            machine_id="digital_sra3",
            paper_id="estucado_mate",
            quantity=500,
            finishings=["grapado"],
            page_count=16,
        )
        self.assertEqual(recipe["imposition"]["mode"], "booklet")
        self.assertEqual(recipe["imposition"]["sheet_size"], "SRA3")
        self.assertEqual(recipe["imposition"]["orientation"], "landscape")
        # 16 páginas = 4 pliegos por ejemplar -> 500 ejemplares = 2000 pliegos netos
        self.assertEqual(recipe["material_calculation"]["net_sheets"], 2000)
        self.assertGreater(recipe["material_calculation"]["gross_sheets"], 2000)
        self.assertEqual(len(recipe["warnings"]), 0)

    def test_propose_cards_recipe(self):
        recipe = production_order.propose_production_recipe(
            product_id="tarjetas_visita",
            machine_id="digital_sra3",
            paper_id="estucado_brillo",
            quantity=1000,
            finishings=["plastificado_mate"],
            page_count=2,
            trim_width_mm=85.0,
            trim_height_mm=55.0,
        )
        self.assertEqual(recipe["imposition"]["mode"], "step_and_repeat")
        self.assertEqual(recipe["imposition"]["gutter_x_mm"], 4.0)
        self.assertEqual(recipe["imposition"]["gutter_y_mm"], 4.0)
        self.assertGreater(recipe["material_calculation"]["net_sheets"], 0)

    def test_validation_against_order(self):
        recipe = production_order.propose_production_recipe(
            product_id="catalogo_grapado",
            machine_id="offset_b2",
            paper_id="periodico_prensa",
            quantity=1000,
            finishings=["barniz_uvi"],
            page_count=15,
        )
        job_data = {
            "job_meta": {"page_count": 15},
            "paginas": {"total_paginas": 15},
            "analisis_tac": {"tac_maximo": 290},
            "separaciones": {"tintas_directas": []},
        }
        findings = production_order.validate_pdf_against_order(job_data, recipe)
        finding_codes = [f["code"] for f in findings]
        # Debe fallar por no ser múltiplo de 4
        self.assertIn("PO_BOOKLET_PAGES_NOT_MULTIPLE_OF_4", finding_codes)
        # Debe avisar por falta de tinta directa de Barniz_UVI
        self.assertIn("PO_MISSING_TECHNICAL_SPOT", finding_codes)
        # Debe avisar porque TAC (290%) excede el límite del papel prensa (240%)
        self.assertIn("PO_TAC_EXCEEDS_PAPER_LIMIT", finding_codes)

    def test_generate_job_ticket_pdf(self):
        recipe = production_order.propose_production_recipe(
            product_id="catalogo_grapado",
            machine_id="digital_sra3",
            paper_id="estucado_mate",
            quantity=250,
            finishings=["grapado"],
            page_count=16,
        )
        job_data = {
            "job_meta": {"job_id": "test_ticket_01", "filename": "Catalogo_2026.pdf"},
        }
        output_pdf = self.jobs_dir / "job_ticket.pdf"
        production_order.generate_job_ticket_pdf(recipe, job_data, output_pdf)

        self.assertTrue(output_pdf.exists())
        self.assertGreater(output_pdf.stat().st_size, 1000)

        with pymupdf.open(str(output_pdf)) as doc:
            self.assertEqual(len(doc), 1)
            text = doc[0].get_text()
            self.assertIn("HOJA DE RUTA DE TALLER", text)
            self.assertIn("test_ticket_01", text)
            self.assertIn("Catálogo o Revista Grapada", text)
            self.assertIn("PREIMPRESIÓN", text)
            self.assertIn("IMPRESIÓN (PRENSA)", text)
            self.assertIn("ACABADOS", text)

    def test_api_endpoints_integration(self):
        orig_jobs = app.JOBS_DIR
        app.JOBS_DIR = self.jobs_dir
        try:
            client = TestClient(app.app)

            # 1. GET catalogs
            resp_cat = client.get("/api/production-orders/catalogs")
            self.assertEqual(resp_cat.status_code, 200)
            self.assertIn("products", resp_cat.json())

            # 2. POST calculate
            payload = {
                "product_id": "catalogo_grapado",
                "machine_id": "digital_sra3",
                "paper_id": "estucado_mate",
                "quantity": 500,
                "finishings": ["grapado"],
                "page_count": 16,
            }
            resp_calc = client.post("/api/production-orders/calculate", json=payload)
            self.assertEqual(resp_calc.status_code, 200)
            data_calc = resp_calc.json()
            self.assertEqual(data_calc["imposition"]["mode"], "booklet")

            # 3. Create dummy job for apply
            job_id = "test_po_job"
            dummy_pdf = self.jobs_dir / f"{job_id}_sample.pdf"
            dummy_doc = pymupdf.open()
            for _ in range(16):
                dummy_doc.new_page(width=595.3, height=841.9)
            dummy_doc.save(str(dummy_pdf))
            dummy_doc.close()

            job_manifest = {
                "job_meta": {
                    "job_id": job_id,
                    "filename": "Revista.pdf",
                    "file_path": str(dummy_pdf),
                    "page_count": 16,
                    "current_sha256": "c" * 64,
                },
                "paginas": {"total_paginas": 16},
                "triple_result": {"technical": {"status": "PASS"}},
            }
            (self.jobs_dir / f"{job_id}.json").write_text(json.dumps(job_manifest), encoding="utf-8")

            # POST apply
            resp_apply = client.post(f"/api/production-orders/apply/{job_id}", json=payload)
            self.assertEqual(resp_apply.status_code, 200)
            apply_data = resp_apply.json()
            self.assertEqual(apply_data["status"], "ok")
            self.assertIn("job_ticket_url", apply_data)

            # 4. GET job ticket download
            resp_ticket = client.get(f"/api/production-orders/job-ticket/{job_id}")
            self.assertEqual(resp_ticket.status_code, 200)
            self.assertEqual(resp_ticket.headers["content-type"], "application/pdf")
            self.assertGreater(len(resp_ticket.content), 500)
        finally:
            app.JOBS_DIR = orig_jobs


if __name__ == "__main__":
    unittest.main()
