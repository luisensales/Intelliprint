"""Tests for Neon/SQLite dual DB adapter, individual email registration, single session and FP Classroom Panel."""

import ast
import inspect
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app
import auth_manager
import db_store
import fp_classroom


class FPClassroomAndRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.test_db = Path(self.tmp.name) / "fp_test.db"
        self.jobs_dir = Path(self.tmp.name) / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

        self.orig_db_path = auth_manager.DB_PATH
        self.orig_jobs_dir = app.JOBS_DIR
        auth_manager.DB_PATH = self.test_db
        app.JOBS_DIR = self.jobs_dir
        self.addCleanup(self._restore_globals)

        fp_classroom.init_fp_db(self.test_db)

    def _restore_globals(self):
        auth_manager.DB_PATH = self.orig_db_path
        app.JOBS_DIR = self.orig_jobs_dir

    def test_python311_compatibility_and_annotations(self):
        for rel in ("db_store.py", "auth_manager.py", "fp_classroom.py", "app.py"):
            src = Path(rel).read_text(encoding="utf-8")
            ast.parse(src, filename=rel, feature_version=(3, 11))

        for mod in (db_store, auth_manager, fp_classroom, app):
            for _, obj in inspect.getmembers(mod):
                if getattr(obj, "__module__", None) == mod.__name__ and callable(obj):
                    inspect.get_annotations(obj, eval_str=True)

    def test_db_store_sql_translation_preserves_literals(self):
        sql = "SELECT * FROM users WHERE role = '?' AND email = ? AND id = ?"
        translated = db_store._translate_sql(sql, postgres=True)
        self.assertEqual(
            translated,
            "SELECT * FROM users WHERE role = '?' AND email = %s AND id = %s",
        )
        ddl = "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)"
        self.assertIn("SERIAL PRIMARY KEY", db_store._translate_sql(ddl, postgres=True))

    def test_db_status_local_sqlite_fallback(self):
        with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
            self.assertFalse(db_store.is_postgres_configured())
            status = db_store.get_db_status(self.test_db)
            self.assertEqual(status["backend"], "sqlite")
            self.assertFalse(status["persistent"])

    def test_forensic_comparison_recognizes_app_flags_and_production_validation(self):
        comp = fp_classroom.build_submission_comparison({
            "job_meta": {
                "filename": "practica_real.pdf",
                "has_cmyk_converted": True,
                "has_bleed_fixed": True,
                "has_icc_fixed": True,
            },
            "original_analysis": {
                "job_summary": {"page_count": 2},
                "findings": [{"severity": "error", "category": "Color", "message": "RGB detectado"}],
            },
            "job_summary": {"page_count": 2},
            "findings": [],
            "production_validation": {"overall_verdict": "CERTIFICADO PARA PRODUCCIÓN"},
        })
        self.assertEqual(comp["decisions"]["fixes_count"], 3)
        self.assertTrue(comp["decisions"]["used_gwg_validation"])
        self.assertEqual(comp["decisions"]["gwg_status"], "CERTIFICADO PARA PRODUCCIÓN")

    def test_email_registration_roles_invite_codes_and_single_session(self):
        with patch.dict(os.environ, {"INTELLIPRINT_DOCENTE_CODE": "DOC-2026"}, clear=False):
            # 1. Estudiante se activa al instante
            student = auth_manager.register_user(
                email="ane@fp.eus",
                password="password123",
                full_name="Ane Alumno",
                requested_role="alumno",
                db_path=self.test_db,
            )
            self.assertEqual(student["role"], "alumno")
            self.assertEqual(student["approval_status"], "ACTIVE")
            self.assertTrue(student["is_active"])

            # 2. Docente sin código queda PENDIENTE de aprobación
            pending_doc = auth_manager.register_user(
                email="profe.pendiente@fp.eus",
                password="password123",
                full_name="Profe SinCodigo",
                requested_role="docente",
                db_path=self.test_db,
            )
            self.assertEqual(pending_doc["approval_status"], "PENDING")
            self.assertFalse(pending_doc["is_active"])

            # Login pendiente bloqueado
            auth_user, reason = auth_manager.authenticate_user_detailed(
                "profe.pendiente@fp.eus", "password123", db_path=self.test_db
            )
            self.assertIsNone(auth_user)
            self.assertEqual(reason, "pending_approval")

            # 3. Docente con código de invitación se activa al instante
            active_doc = auth_manager.register_user(
                email="profe.ok@fp.eus",
                password="password123",
                full_name="Profe Validado",
                requested_role="docente",
                invite_code="DOC-2026",
                db_path=self.test_db,
            )
            self.assertEqual(active_doc["role"], "docente")
            self.assertEqual(active_doc["approval_status"], "ACTIVE")
            self.assertTrue(active_doc["is_active"])

            # 4. Login con email y sesión única activa
            logged_in, _ = auth_manager.authenticate_user_detailed(
                "ANE@FP.EUS", "password123", db_path=self.test_db
            )
            self.assertIsNotNone(logged_in)
            self.assertEqual(logged_in["id"], student["id"])

            sess1 = auth_manager.create_user_session(student["id"], db_path=self.test_db, single_session=True)
            sess2 = auth_manager.create_user_session(student["id"], db_path=self.test_db, single_session=True)
            self.assertIsNone(auth_manager.get_user_from_session(sess1, db_path=self.test_db))
            self.assertIsNotNone(auth_manager.get_user_from_session(sess2, db_path=self.test_db))

    def test_full_fp_classroom_api_workflow(self):
        teacher_client = TestClient(app.app)
        student_client = TestClient(app.app)
        admin_client = TestClient(app.app)

        # Registro e inicio de sesión docente mediante código
        with patch.dict(os.environ, {"INTELLIPRINT_DOCENTE_CODE": "SALESIANOS-FP"}, clear=False):
            r_doc = teacher_client.post("/api/auth/register", json={
                "email": "carlos.docente@fp.eus",
                "password": "claveDocente2026",
                "full_name": "Carlos Docente FP",
                "role": "docente",
                "invite_code": "SALESIANOS-FP",
            })
            self.assertEqual(r_doc.status_code, 200)
            self.assertEqual(r_doc.json()["status"], "ok")

        # Crear grupo FP
        r_grp = teacher_client.post("/api/fp/teacher/groups", json={
            "name": "2º GS Preimpresión",
            "center": "CIFP Salesianos",
            "module_name": "Tratamiento de Textos e Imágenes",
        })
        self.assertEqual(r_grp.status_code, 200)
        group = r_grp.json()["group"]
        join_code = group["join_code"]

        # Publicar práctica
        r_asg = teacher_client.post("/api/fp/teacher/assignments", json={
            "group_id": group["id"],
            "title": "Folleto Offset FOGRA39",
            "description": "Corregir imágenes RGB, fuentes sin incrustar y sangrado 3 mm.",
            "assignment_type": "pdf_real",
            "target_profile": "OFFSET_300",
        })
        self.assertEqual(r_asg.status_code, 200)
        assignment = r_asg.json()["assignment"]

        # Registro de alumno con código de grupo (inscripción automática)
        r_stu = student_client.post("/api/auth/register", json={
            "email": "miren.alumna@fp.eus",
            "password": "claveAlumno2026",
            "full_name": "Miren Alumna FP",
            "role": "alumno",
            "class_code": join_code,
        })
        self.assertEqual(r_stu.status_code, 200)
        stu_payload = r_stu.json()
        self.assertEqual(stu_payload["status"], "ok")
        self.assertEqual(stu_payload["joined_group"]["id"], group["id"])

        # Alumno intenta acceder a gestión de usuarios admin -> 403
        self.assertEqual(student_client.get("/api/admin/users").status_code, 403)
        self.assertEqual(student_client.get("/api/fp/teacher/overview").status_code, 403)

        # Crear job real simulado con diagnóstico inicial -> correcciones -> resultado final
        job_id = "fp_job_001"
        job_file = self.jobs_dir / f"{job_id}.json"
        job_file.write_text(json.dumps({
            "job_id": job_id,
            "job_meta": {"filename": "folleto_miren.pdf", "profile": "OFFSET_300"},
            "original_analysis": {
                "job_summary": {"page_count": 4, "max_tac": 345, "color_spaces": ["RGB", "CMYK"]},
                "findings": [
                    {"severity": "error", "category": "Color", "message": "Imagen en RGB"},
                    {"severity": "error", "category": "Sangrado", "message": "Sin sangrado 3mm"},
                    {"severity": "warning", "category": "TAC", "message": "TAC 345% > 300%"},
                ],
            },
            "job_summary": {"page_count": 4, "max_tac": 288, "color_spaces": ["CMYK"]},
            "findings": [
                {"severity": "warning", "category": "Sobreimpresión", "message": "Revisar reserva"},
            ],
            "fixes_applied": [
                {"action": "Conversión imágenes RGB a CMYK FOGRA39", "detail": "Reemplazo automático"},
                {"action": "Extensión espejo de sangrado 3 mm + marcas de corte", "detail": "Página 1-4"},
            ],
            "gwg_validation_report": {"overall_status": "PASS"},
        }), encoding="utf-8")

        # Alumno entrega su PDF
        r_sub = student_client.post("/api/fp/student/submit", json={
            "assignment_id": assignment["id"],
            "job_id": job_id,
        })
        self.assertEqual(r_sub.status_code, 200)
        submission = r_sub.json()["submission"]
        self.assertEqual(submission["comparison"]["initial"]["critical_count"], 2)
        self.assertEqual(submission["comparison"]["final"]["critical_count"], 0)
        self.assertEqual(submission["comparison"]["delta"]["critical_resolution_pct"], 100.0)

        # Alumno completa cuestionario didáctico y se registra en su evolución
        r_quiz = student_client.post("/api/didactic/quiz/evaluate", json={
            "profile": "OFFSET_300",
            "answers": {0: "a", 1: "b"},
        })
        self.assertEqual(r_quiz.status_code, 200)

        # Docente consulta detalle y califica con rúbrica
        r_det = teacher_client.get(f"/api/fp/teacher/submissions/{submission['id']}")
        self.assertEqual(r_det.status_code, 200)
        detail = r_det.json()["submission"]
        self.assertGreaterEqual(detail["comparison"]["suggested_final_grade"], 8.0)

        r_grade = teacher_client.post(f"/api/fp/teacher/submissions/{submission['id']}/grade", json={
            "rubric_scores": {"diagnostico": 9.0, "decisiones": 9.5, "resultado_final": 10.0, "taller_teoria": 8.5},
            "teacher_feedback": "Excelente resolución de sangrado y conversión CMYK.",
            "status": "REVIEWED",
        })
        self.assertEqual(r_grade.status_code, 200)
        reviewed = r_grade.json()["submission"]
        self.assertEqual(reviewed["status"], "REVIEWED")

        r_grade = teacher_client.post(f"/api/fp/teacher/submissions/{submission['id']}/grade", json={
            "rubric_scores": {"diagnostico": 9.0, "decisiones": 9.5, "resultado_final": 10.0, "taller_teoria": 8.5},
            "teacher_feedback": "Excelente resolución de sangrado y conversión CMYK.",
            "status": "GRADED",
        })
        self.assertEqual(r_grade.status_code, 200)
        graded = r_grade.json()["submission"]
        self.assertEqual(graded["status"], "GRADED")
        self.assertAlmostEqual(graded["final_grade"], 9.35, places=2)

        # Dashboard alumno devuelve cuestionarios enriquecidos con profile y level
        r_dash = student_client.get("/api/fp/student/dashboard")
        self.assertEqual(r_dash.status_code, 200)
        quiz_attempts = r_dash.json()["dashboard"]["quiz_attempts"]
        self.assertEqual(len(quiz_attempts), 1)
        self.assertEqual(quiz_attempts[0]["profile"], "OFFSET_300")
        self.assertTrue(bool(quiz_attempts[0]["level"]))

        # Evolución, CSV y Acta PDF A4
        r_ov = teacher_client.get(f"/api/fp/teacher/overview?group_id={group['id']}")
        self.assertEqual(r_ov.status_code, 200)
        students_evo = r_ov.json()["evolution"]["students"]
        self.assertEqual(len(students_evo), 1)
        self.assertEqual(students_evo[0]["avg_error_resolution_pct"], 100.0)

        r_csv = teacher_client.get(f"/api/fp/teacher/export-csv?group_id={group['id']}")
        self.assertEqual(r_csv.status_code, 200)
        self.assertIn("Miren Alumna FP", r_csv.text)

        r_pdf = teacher_client.get(f"/api/fp/teacher/submissions/{submission['id']}/report-pdf")
        self.assertEqual(r_pdf.status_code, 200)
        self.assertTrue(r_pdf.content.startswith(b"%PDF-1."))

        # Responsable puede aprobar cuentas pendientes desde /api/admin/users
        r_pend = admin_client.post("/api/auth/register", json={
            "email": "otro.profe@fp.eus",
            "password": "clavePendiente1",
            "full_name": "Otro Profe",
            "role": "docente",
        })
        self.assertEqual(r_pend.status_code, 200)
        self.assertEqual(r_pend.json()["status"], "pending")
        pending_id = r_pend.json()["user"]["id"]

        admin_login = admin_client.post("/api/auth/login", json={"username": "responsable", "password": "taller123"})
        self.assertEqual(admin_login.status_code, 200)

        r_users = admin_client.get("/api/admin/users")
        self.assertEqual(r_users.status_code, 200)
        self.assertTrue(any(u["id"] == pending_id for u in r_users.json()["users"]))

        r_appr = admin_client.post(f"/api/admin/users/{pending_id}/access", json={
            "role": "docente",
            "is_active": True,
            "approval_status": "ACTIVE",
        })
        self.assertEqual(r_appr.status_code, 200)
        self.assertTrue(r_appr.json()["user"]["is_active"])
