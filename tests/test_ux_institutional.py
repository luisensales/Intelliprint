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


if __name__ == "__main__":
    unittest.main()

