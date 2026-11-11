"""Unit tests for Job Conservation, Search, Filters, Expiration, Recovery and Production Package."""

import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import zipfile

from fastapi.testclient import TestClient

import app
import job_manager


class JobManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.jobs_dir = Path(self.tmp.name) / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _create_sample_job(self, job_id, filename="documento.pdf", status="AUTHORIZED", operator="Luisen", age_hours=2):
        mtime = time.time() - (age_hours * 3600)
        data = {
            "job_meta": {
                "job_id": job_id,
                "filename": filename,
                "profile_id": "OFFSET_300",
                "profile_name": "Offset Comercial FOGRA51",
                "current_sha256": "a" * 64,
                "authorized_sha256": "a" * 64 if status == "AUTHORIZED" else None,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime)),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime)),
            },
            "perfil_seleccionado": {
                "id": "OFFSET_300",
                "nombre": "Offset Comercial FOGRA51",
            },
            "paginas": {"total_paginas": 4},
            "triple_result": {
                "technical": {"status": "CORRECTO", "summary": {"errors": 0, "warnings": 0}},
                "production": {"status": "APTO"},
                "release": {
                    "status": status,
                    "operator_name": operator,
                    "label": "Aprobado para tirada" if status == "AUTHORIZED" else "Pendiente",
                    "notes": "Producción estándar",
                },
            },
            "version_history": {
                "active_id": "v0001",
                "approved_version_id": "v0001" if status == "AUTHORIZED" else None,
                "versions": [
                    {
                        "id": "v0001",
                        "label": "PDF original recibido",
                        "size_bytes": 1024,
                        "sha256": "a" * 64,
                        "is_approved": status == "AUTHORIZED",
                        "timestamp": "2026-11-11T12:00:00Z",
                    }
                ],
            },
        }
        manifest_path = self.jobs_dir / f"{job_id}.json"
        pdf_file = self.jobs_dir / f"{job_id}_sample.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")
        data["job_meta"]["last_fixed_pdf_path"] = str(pdf_file)
        manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.utime(manifest_path, (mtime, mtime))
        os.utime(pdf_file, (mtime, mtime))
        return data, manifest_path

    def test_job_expiration_calculation(self):
        data, manifest = self._create_sample_job("job_exp1", age_hours=4)
        exp = job_manager.calculate_job_expiration(data, manifest_path=manifest, ttl_hours=24)
        self.assertEqual(exp["ttl_hours"], 24)
        self.assertTrue(exp["persistent_storage"])
        self.assertFalse(exp["is_expired"])
        # Con 4 horas de antigüedad, deberían quedar ~20 horas
        self.assertAlmostEqual(exp["remaining_seconds"] / 3600, 20, delta=0.5)
        self.assertIn("h", exp["remaining_human"])
        self.assertFalse(exp["is_expiring_soon"])

        # Trabajo a punto de caducar (23 horas de antigüedad, 1h restante)
        data2, manifest2 = self._create_sample_job("job_exp2", age_hours=23)
        exp2 = job_manager.calculate_job_expiration(data2, manifest_path=manifest2, ttl_hours=24)
        self.assertTrue(exp2["is_expiring_soon"])
        self.assertFalse(exp2["is_expired"])

    def test_list_managed_jobs_search_and_filters(self):
        self._create_sample_job("job_alpha", filename="Catalogo_Primavera.pdf", status="AUTHORIZED", operator="Maria")
        self._create_sample_job("job_beta", filename="Folleto_Ofertas.pdf", status="REJECTED", operator="Juan")
        self._create_sample_job("job_gamma", filename="Revista_Mensual.pdf", status="PENDING", operator="")

        # Listar todos
        res_all = job_manager.list_managed_jobs(self.jobs_dir)
        self.assertEqual(res_all["total"], 3)
        self.assertEqual(len(res_all["jobs"]), 3)

        # Búsqueda por texto (query)
        res_q = job_manager.list_managed_jobs(self.jobs_dir, query="primavera")
        self.assertEqual(res_q["total"], 1)
        self.assertEqual(res_q["jobs"][0]["job_id"], "job_alpha")

        res_q_op = job_manager.list_managed_jobs(self.jobs_dir, query="juan")
        self.assertEqual(res_q_op["total"], 1)
        self.assertEqual(res_q_op["jobs"][0]["job_id"], "job_beta")

        # Filtro de estado
        res_approved = job_manager.list_managed_jobs(self.jobs_dir, status_filter="approved")
        self.assertEqual(res_approved["total"], 1)
        self.assertEqual(res_approved["jobs"][0]["job_id"], "job_alpha")

        res_rejected = job_manager.list_managed_jobs(self.jobs_dir, status_filter="rejected")
        self.assertEqual(res_rejected["total"], 1)
        self.assertEqual(res_rejected["jobs"][0]["job_id"], "job_beta")

        res_pending = job_manager.list_managed_jobs(self.jobs_dir, status_filter="pending")
        self.assertEqual(res_pending["total"], 1)
        self.assertEqual(res_pending["jobs"][0]["job_id"], "job_gamma")

    def test_job_recovery_rehydration(self):
        self._create_sample_job("job_rec", filename="Etiqueta.pdf", status="AUTHORIZED")
        job_data = job_manager.get_job_data_for_recovery("job_rec", self.jobs_dir)
        self.assertEqual(job_data["job_meta"]["job_id"], "job_rec")
        self.assertIn("expiration_info", job_data)
        self.assertEqual(job_data["expiration_info"]["ttl_hours"], 24)
        self.assertFalse(job_data["expiration_info"]["is_expired"])

        # Trabajo inexistente
        with self.assertRaises(job_manager.JobManagerError):
            job_manager.get_job_data_for_recovery("inexistente", self.jobs_dir)

    def test_build_production_package(self):
        self._create_sample_job("job_pkg", filename="Manual_Taller.pdf", status="AUTHORIZED")
        zip_bytes, zip_name = job_manager.build_production_package("job_pkg", self.jobs_dir)
        self.assertTrue(zip_name.startswith("Paquete_Produccion_IntelliPrint_Manual_Taller_"))
        self.assertTrue(zip_name.endswith(".zip"))

        # Inspeccionar contenidos del ZIP
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            namelist = zf.namelist()
            self.assertIn("MANIFIESTO_PRODUCCION.txt", namelist)
            self.assertIn("01_Arte_Final_Impresion/IntelliPrint_Manual_Taller_FINAL.pdf", namelist)
            self.assertIn("02_Documentacion_Tecnica/Informe_Auditoria.json", namelist)

            manifest_content = zf.read("MANIFIESTO_PRODUCCION.txt").decode("utf-8")
            self.assertIn("PAQUETE COMPLETO DE PRODUCCIÓN", manifest_content)
            self.assertIn("job_pkg", manifest_content)
            self.assertIn("Retención garantizada de 24 horas", manifest_content)

    def test_api_endpoints_integration(self):
        # Configurar JOBS_DIR en app para usar self.jobs_dir
        orig_jobs = app.JOBS_DIR
        app.JOBS_DIR = self.jobs_dir
        try:
            self._create_sample_job("api_job_01", filename="Packaging_Caja.pdf", status="AUTHORIZED")
            client = TestClient(app.app)

            # 1. GET /api/jobs
            resp_list = client.get("/api/jobs?q=caja")
            self.assertEqual(resp_list.status_code, 200)
            data_list = resp_list.json()
            self.assertEqual(data_list["total"], 1)
            self.assertEqual(data_list["jobs"][0]["job_id"], "api_job_01")

            # 2. GET /api/jobs/{job_id}/expiration
            resp_exp = client.get("/api/jobs/api_job_01/expiration")
            self.assertEqual(resp_exp.status_code, 200)
            self.assertEqual(resp_exp.json()["ttl_hours"], 24)

            # 3. GET /api/jobs/{job_id}/load
            resp_load = client.get("/api/jobs/api_job_01/load")
            self.assertEqual(resp_load.status_code, 200)
            self.assertEqual(resp_load.json()["job_meta"]["job_id"], "api_job_01")
            self.assertIn("expiration_info", resp_load.json())

            # 4. GET /api/production-package/{job_id}
            resp_pkg = client.get("/api/production-package/api_job_01")
            self.assertEqual(resp_pkg.status_code, 200)
            self.assertEqual(resp_pkg.headers["content-type"], "application/zip")
            self.assertGreater(len(resp_pkg.content), 100)
        finally:
            app.JOBS_DIR = orig_jobs


if __name__ == "__main__":
    unittest.main()
