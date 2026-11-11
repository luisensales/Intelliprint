"""Unit tests for version_history.py."""

import copy
from pathlib import Path
import tempfile
import unittest

import pikepdf
import pymupdf

from version_history import (
    capture_version,
    select_version,
    public_history,
    version_path,
    compare_versions,
    render_version_page_image,
    render_version_diff_image,
    VersionHistoryError,
    VersionQuotaError,
)


class VersionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.jobs_dir = Path(self.temp_dir.name)
        self.pdf1 = self.jobs_dir / "v1.pdf"
        self.pdf2 = self.jobs_dir / "v2.pdf"
        self.pdf3 = self.jobs_dir / "v3.pdf"

        # PDF 1
        with pikepdf.new() as p:
            p.add_blank_page(page_size=(200, 200))
            p.save(self.pdf1)

        # PDF 2 (diferente)
        with pikepdf.new() as p:
            page = p.add_blank_page(page_size=(200, 200))
            page.Contents = p.make_stream(b"1 0 0 rg 10 10 50 50 re f\n")
            p.save(self.pdf2)

        # PDF 3 (diferente)
        with pikepdf.new() as p:
            page = p.add_blank_page(page_size=(210, 297))
            page.Contents = p.make_stream(b"0 1 0 rg 20 20 100 100 re f\n")
            p.save(self.pdf3)

        self.job_data = {
            "job_meta": {"job_id": "testjob1"},
            "findings": [],
            "triple_result": {"technical": {"status": "PASS"}},
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_capture_and_navigation(self):
        # 1. Capturar versión original
        ok1 = capture_version(self.job_data, self.pdf1, self.jobs_dir, label="Original recibido")
        self.assertTrue(ok1)
        history = public_history(self.job_data, self.jobs_dir)
        self.assertEqual(len(history["versions"]), 1)
        self.assertEqual(history["active_id"], "v0001")
        self.assertFalse(history["can_undo"])
        self.assertFalse(history["can_redo"])

        # 2. Capturar segunda versión
        ok2 = capture_version(self.job_data, self.pdf2, self.jobs_dir, label="Conversión a CMYK")
        self.assertTrue(ok2)
        history = public_history(self.job_data, self.jobs_dir)
        self.assertEqual(len(history["versions"]), 2)
        self.assertEqual(history["active_id"], "v0002")
        self.assertTrue(history["can_undo"])
        self.assertFalse(history["can_redo"])

        # 3. Deduplicar: intentar capturar el mismo PDF de nuevo devuelve False
        ok_dup = capture_version(self.job_data, self.pdf2, self.jobs_dir, label="Conversión repetida")
        self.assertFalse(ok_dup)

        # 4. Deshacer (Undo)
        undone = select_version(self.job_data, self.jobs_dir, operation="undo")
        self.assertEqual(undone["id"], "v0001")
        history = public_history(self.job_data, self.jobs_dir)
        self.assertEqual(history["active_id"], "v0001")
        self.assertFalse(history["can_undo"])
        self.assertTrue(history["can_redo"])

        # 5. Rehacer (Redo)
        redone = select_version(self.job_data, self.jobs_dir, operation="redo")
        self.assertEqual(redone["id"], "v0002")
        history = public_history(self.job_data, self.jobs_dir)
        self.assertEqual(history["active_id"], "v0002")
        self.assertTrue(history["can_undo"])
        self.assertFalse(history["can_redo"])

        # 6. Capturar tercera versión y restaurar a v0001 directamente
        capture_version(self.job_data, self.pdf3, self.jobs_dir, label="Versión 3")
        restored = select_version(self.job_data, self.jobs_dir, version_id="v0001", operation="restore")
        self.assertEqual(restored["id"], "v0001")
        history = public_history(self.job_data, self.jobs_dir)
        self.assertEqual(history["active_id"], "v0001")

    def test_approved_version_protection(self):
        capture_version(self.job_data, self.pdf1, self.jobs_dir, label="Original recibido")
        capture_version(self.job_data, self.pdf2, self.jobs_dir, label="Aprobada por cliente", is_approved=True)

        history = public_history(self.job_data, self.jobs_dir)
        self.assertEqual(history["approved_version_id"], "v0002")
        v2_entry = next(v for v in history["versions"] if v["id"] == "v0002")
        self.assertTrue(v2_entry["is_approved"])

        # Modificación posterior: no sobreescribe ni desprotege v0002
        capture_version(self.job_data, self.pdf3, self.jobs_dir, label="Cambio posterior")
        history_after = public_history(self.job_data, self.jobs_dir)
        self.assertEqual(history_after["active_id"], "v0003")
        self.assertEqual(history_after["approved_version_id"], "v0002")

        v2_after = next(v for v in history_after["versions"] if v["id"] == "v0002")
        self.assertTrue(v2_after["is_approved"])
        v3_after = next(v for v in history_after["versions"] if v["id"] == "v0003")
        self.assertFalse(v3_after["is_approved"])

        # La versión aprobada sigue existiendo y su blob es idéntico
        path_v2 = version_path(self.job_data, self.jobs_dir, "v0002")
        self.assertTrue(path_v2.exists())

    def test_compare_versions_and_diff(self):
        capture_version(self.job_data, self.pdf1, self.jobs_dir, label="Original")
        capture_version(self.job_data, self.pdf2, self.jobs_dir, label="Corregido")

        comp = compare_versions(self.job_data, self.jobs_dir, "v0001", "v0002", page_num=1)
        self.assertEqual(comp["version_a"]["id"], "v0001")
        self.assertEqual(comp["version_b"]["id"], "v0002")
        self.assertFalse(comp["identical"])

        # Render preview de página
        img_a = render_version_page_image(self.job_data, self.jobs_dir, "v0001", page_num=1)
        self.assertGreater(len(img_a), 100)

        # Render visual diff
        diff_img = render_version_diff_image(self.job_data, self.jobs_dir, "v0001", "v0002", page_num=1)
        self.assertGreater(len(diff_img), 100)

    def test_api_endpoints_integration(self):
        import json
        from fastapi.testclient import TestClient
        import app

        client = TestClient(app.app)
        job_id = "vtestjob"
        job_json = app.JOBS_DIR / f"{job_id}.json"

        # Preparamos un trabajo inicial
        job_data = {
            "job_meta": {"job_id": job_id, "filename": "prueba.pdf", "profile_id": "OFFSET_300"},
            "findings": [],
            "job_summary": {"pages": 1},
            "triple_result": {"technical": {"status": "PASS", "errors_count": 0, "warnings_count": 0}, "release": {"status": "PENDING"}}
        }
        capture_version(job_data, self.pdf1, app.JOBS_DIR, label="Original")
        capture_version(job_data, self.pdf2, app.JOBS_DIR, label="CMYK")
        with open(job_json, "w", encoding="utf-8") as f:
            json.dump(job_data, f)

        try:
            # 1. GET /api/history/{job_id}
            resp = client.get(f"/api/history/{job_id}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(len(data["versions"]), 2)
            self.assertEqual(data["active_id"], "v0002")
            self.assertTrue(data["can_undo"])

            # 2. POST /api/history/{job_id}/undo
            resp_undo = client.post(f"/api/history/{job_id}/undo")
            self.assertEqual(resp_undo.status_code, 200)
            undo_data = resp_undo.json()
            self.assertEqual(undo_data["active_version"]["id"], "v0001")

            # 3. POST /api/history/{job_id}/redo
            resp_redo = client.post(f"/api/history/{job_id}/redo")
            self.assertEqual(resp_redo.status_code, 200)
            redo_data = resp_redo.json()
            self.assertEqual(redo_data["active_version"]["id"], "v0002")

            # 4. POST /api/history/{job_id}/restore/v0001
            resp_restore = client.post(f"/api/history/{job_id}/restore/v0001")
            self.assertEqual(resp_restore.status_code, 200)

            # 5. GET /api/history/{job_id}/compare?version_a=v0001&version_b=v0002
            resp_comp = client.get(f"/api/history/{job_id}/compare?version_a=v0001&version_b=v0002&page=1")
            self.assertEqual(resp_comp.status_code, 200)
            self.assertIn("version_a", resp_comp.json())

            # 6. GET /api/history/{job_id}/preview/v0001
            resp_prev = client.get(f"/api/history/{job_id}/preview/v0001?page=1")
            self.assertEqual(resp_prev.status_code, 200)
            self.assertEqual(resp_prev.headers["content-type"], "image/jpeg")

            # 7. GET /api/history/{job_id}/diff?version_a=v0001&version_b=v0002
            resp_diff = client.get(f"/api/history/{job_id}/diff?version_a=v0001&version_b=v0002&page=1")
            self.assertEqual(resp_diff.status_code, 200)
            self.assertEqual(resp_diff.headers["content-type"], "image/jpeg")

            # 8. GET /api/history/{job_id}/download/v0001
            resp_dl = client.get(f"/api/history/{job_id}/download/v0001")
            self.assertEqual(resp_dl.status_code, 200)
            self.assertEqual(resp_dl.headers["content-type"], "application/pdf")

        finally:
            job_json.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
