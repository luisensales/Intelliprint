"""Unit tests for Authentication, RBAC and Client Approval Engine."""

import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
import pymupdf

import app
import auth_manager


class AuthManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.test_db = Path(self.tmp.name) / "test_auth.db"
        auth_manager.init_auth_db(self.test_db)

        self.jobs_dir = Path(self.tmp.name) / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

        # Crear un PDF de prueba
        self.dummy_pdf = self.jobs_dir / "doc.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(self.dummy_pdf))
        doc.close()

    def test_password_hashing(self):
        salt, h = auth_manager.hash_password("secreto123")
        self.assertTrue(auth_manager.verify_password("secreto123", salt, h))
        self.assertFalse(auth_manager.verify_password("erronea", salt, h))

    def test_user_authentication(self):
        # Responsable
        user = auth_manager.authenticate_user("responsable", "taller123", db_path=self.test_db)
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "responsable")
        self.assertIn("release_production", user["permissions"])

        # Credencial incorrecta
        wrong = auth_manager.authenticate_user("responsable", "password_falsa", db_path=self.test_db)
        self.assertIsNone(wrong)

    def test_session_lifecycle(self):
        user = auth_manager.authenticate_user("preimpresion", "preim123", db_path=self.test_db)
        self.assertIsNotNone(user)

        sess_id = auth_manager.create_user_session(user["id"], db_path=self.test_db)
        self.assertGreater(len(sess_id), 20)

        # Recuperar de sesión
        sess_user = auth_manager.get_user_from_session(sess_id, db_path=self.test_db)
        self.assertIsNotNone(sess_user)
        self.assertEqual(sess_user["username"], "preimpresion")
        self.assertEqual(sess_user["role"], "preimpresion")

        # Cerrar sesión
        auth_manager.delete_session(sess_id, db_path=self.test_db)
        deleted = auth_manager.get_user_from_session(sess_id, db_path=self.test_db)
        self.assertIsNone(deleted)

    def test_client_approval_workflow(self):
        link_data = auth_manager.generate_client_approval_link("job_abc123", db_path=self.test_db)
        token = link_data["token"]
        self.assertIn("/api/client-approval/view/", link_data["approval_url"])

        # Consultar por token
        info = auth_manager.get_client_approval_by_token(token, db_path=self.test_db)
        self.assertIsNotNone(info)
        self.assertEqual(info["status"], "PENDING")

        # Decisión del cliente
        res = auth_manager.submit_client_decision(
            token=token,
            decision="approved",
            client_name="Cliente Gráfico S.L.",
            client_email="cliente@grafico.com",
            notes="Color y textos revisados. Todo conforme.",
            db_path=self.test_db,
        )
        self.assertEqual(res["status"], "APPROVED")

        # Verificar actualización
        info2 = auth_manager.get_client_approval_by_token(token, db_path=self.test_db)
        self.assertEqual(info2["status"], "APPROVED")
        self.assertEqual(info2["client_name"], "Cliente Gráfico S.L.")

    def test_api_auth_and_release_integration(self):
        orig_jobs = app.JOBS_DIR
        app.JOBS_DIR = self.jobs_dir
        orig_db = auth_manager.DB_PATH
        auth_manager.DB_PATH = self.test_db
        try:
            client = TestClient(app.app)

            # 1. Login exitoso
            resp_login = client.post("/api/auth/login", json={"username": "responsable", "password": "taller123"})
            self.assertEqual(resp_login.status_code, 200)
            data_login = resp_login.json()
            self.assertEqual(data_login["status"], "ok")
            self.assertEqual(data_login["user"]["username"], "responsable")

            # 2. GET /api/auth/me con la cookie de sesión
            resp_me = client.get("/api/auth/me")
            self.assertEqual(resp_me.status_code, 200)
            self.assertTrue(resp_me.json()["authenticated"])
            self.assertEqual(resp_me.json()["user"]["username"], "responsable")

            # 3. Setup de un trabajo para /api/release
            job_id = "test_release_auth_job"
            job_manifest = {
                "job_meta": {
                    "job_id": job_id,
                    "filename": "Revista_Final.pdf",
                    "file_path": str(self.dummy_pdf),
                    "pdf_path": str(self.dummy_pdf),
                    "page_count": 1,
                    "current_sha256": "1" * 64,
                },
                "triple_result": {},
            }
            (self.jobs_dir / f"{job_id}.json").write_text(json.dumps(job_manifest), encoding="utf-8")

            # 4. Autorizar producción (debe tomar la identidad y firma certificada del usuario autenticado)
            resp_rel = client.post(
                "/api/release",
                data={
                    "job_id": job_id,
                    "operator_name": "Nombre Inventado Falso",
                    "decision": "approved",
                    "notes": "Revisado en cabina D50",
                },
            )
            self.assertEqual(resp_rel.status_code, 200)
            rel_res = resp_rel.json()["release_result"]
            # Debe firmar el operador real autenticado ("Mikel Arregi (Jefe de Taller)"), no el texto libre
            self.assertIn("Mikel Arregi", rel_res["operator"])
            self.assertTrue(rel_res["is_certified_signature"])
            self.assertEqual(rel_res["operator_role"], "responsable")

            # 5. Generar enlace de aprobación de cliente
            resp_link = client.post(f"/api/client-approval/create/{job_id}")
            self.assertEqual(resp_link.status_code, 200)
            token = resp_link.json()["token"]

            # 6. Consultar info del token
            resp_info = client.get(f"/api/client-approval/info/{token}")
            self.assertEqual(resp_info.status_code, 200)
            self.assertEqual(resp_info.json()["filename"], "Revista_Final.pdf")

            # 6b. Abrir vista web pública de aprobación de cliente
            resp_view = client.get(f"/api/client-approval/view/{token}")
            self.assertEqual(resp_view.status_code, 200)
            self.assertIn("Revista_Final.pdf", resp_view.text)
            self.assertIn("no-cache", resp_view.headers.get("cache-control", ""))

            # 7. Cliente envía su visto bueno
            resp_decide = client.post(
                f"/api/client-approval/submit/{token}",
                json={
                    "client_name": "Agencia Publicitaria",
                    "decision": "approved",
                    "notes": "Aprobado para tirar 5000 ejemplares",
                },
            )
            self.assertEqual(resp_decide.status_code, 200)
            self.assertEqual(resp_decide.json()["status"], "ok")

            # 8. Logout
            resp_out = client.post("/api/auth/logout")
            self.assertEqual(resp_out.status_code, 200)
            me_after = client.get("/api/auth/me").json()
            self.assertFalse(me_after["authenticated"])
        finally:
            app.JOBS_DIR = orig_jobs
            auth_manager.DB_PATH = orig_db

    def test_client_approval_view_shows_corrected_pdf_and_page_count(self):
        orig_jobs = app.JOBS_DIR
        app.JOBS_DIR = self.jobs_dir
        orig_db = auth_manager.DB_PATH
        auth_manager.DB_PATH = self.test_db
        try:
            # Crear un PDF de prueba de 2 páginas
            two_page_pdf = self.jobs_dir / "diptico_corregido.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595.3, height=841.9)
            doc.new_page(width=595.3, height=841.9)
            doc.save(str(two_page_pdf))
            doc.close()

            job_id = "test_job_approval_corr"
            job_manifest = {
                "job_meta": {
                    "job_id": job_id,
                    "filename": "Diptico-SS.pdf",
                    "file_path": str(two_page_pdf),
                    "pdf_path": str(two_page_pdf),
                    "last_fixed_pdf_path": str(two_page_pdf),
                    "current_sha256": "abcdef1234567890" * 4,
                    "applied_fixes_history": [
                        {"fix": "mirror_bleed", "path": str(two_page_pdf)},
                        {"fix": "cmyk_converted", "path": str(two_page_pdf)},
                    ]
                },
                "job_summary": {
                    "pages": 2,
                    "bleed_status": "PASS",
                },
                "triple_result": {},
            }
            (self.jobs_dir / f"{job_id}.json").write_text(json.dumps(job_manifest), encoding="utf-8")

            client = TestClient(app.app)
            # Generar token
            resp_create = client.post(f"/api/client-approval/create/{job_id}")
            self.assertEqual(resp_create.status_code, 200)
            token = resp_create.json()["token"]

            # Comprobar info
            resp_info = client.get(f"/api/client-approval/info/{token}")
            self.assertEqual(resp_info.status_code, 200)
            data_info = resp_info.json()
            self.assertEqual(data_info["page_count"], 2)
            self.assertTrue(data_info["has_fixes"])
            self.assertIn("mirror_bleed", data_info["applied_fixes"])

            # Comprobar vista HTML
            resp_view = client.get(f"/api/client-approval/view/{token}")
            self.assertEqual(resp_view.status_code, 200)
            view_text = resp_view.text
            self.assertIn("Diptico-SS.pdf", view_text)
            self.assertIn("2", view_text)
            self.assertIn("página(s)", view_text)
            self.assertIn("Versión Corregida para Imprenta", view_text)
            self.assertIn("Sangrado Sintético (Mirror Bleed)", view_text)
            self.assertIn("Conversión CMYK", view_text)
            self.assertIn("?v=", view_text)

            # Comprobar descarga
            resp_dl = client.get(f"/api/download-pdf/{job_id}")
            self.assertEqual(resp_dl.status_code, 200)
            disp = resp_dl.headers.get("content-disposition", "")
            self.assertIn("Diptico-SS_produccion_corregido.pdf", disp)
            self.assertIn("no-cache", resp_dl.headers.get("cache-control", ""))
        finally:
            app.JOBS_DIR = orig_jobs
            auth_manager.DB_PATH = orig_db


if __name__ == "__main__":
    unittest.main()
