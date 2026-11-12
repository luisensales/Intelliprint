"""Tests for Option 3 FP Pedagogical Evolution: 12-question bank, topics, exam_mode, custom rubrics & competencies."""

import json
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app
import auth_manager
import didactic_engine
import fp_classroom


class FPPedagogyEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.test_db = Path(self.tmp.name) / "fp_pedagogy.db"
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

    def _make_job_json(self, job_id: str, used_batch: bool) -> None:
        meta = {
            "job_id": job_id,
            "filename": f"{job_id}.pdf",
            "profile_id": "OFFSET_300",
            "applied_fixes_history": (
                []
                if used_batch
                else [
                    {"action": "Convertir imágenes a CMYK", "detail": "ISOcoated_v2"},
                    {"action": "Extensión espejo de sangrado 3 mm", "detail": "Página 1"},
                ]
            ),
            "batch_steps_applied": ["cmyk_images", "mirror_bleed"] if used_batch else [],
        }
        payload = {
            "job_id": job_id,
            "job_meta": meta,
            "original_analysis": {
                "job_summary": {"page_count": 2, "max_tac": 345, "color_spaces": ["RGB", "CMYK"]},
                "findings": [
                    {"rule_id": "INK_COLORSPACE_RGB", "severity": "ERROR", "title": "Imagen RGB"},
                    {"rule_id": "BLEED_MISSING", "severity": "ERROR", "title": "Sin sangrado"},
                    {"rule_id": "HAIRLINE_THIN_STROKE", "severity": "WARNING", "title": "Filete fino"},
                ],
            },
            "job_summary": {"page_count": 2, "max_tac": 288, "color_spaces": ["CMYK"]},
            "findings": [],
            "triple_result": {"technical": {"status": "PASS"}},
        }
        (self.jobs_dir / f"{job_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_didactic_quiz_12_questions_topic_filter_and_competencies(self):
        self.assertEqual(len(didactic_engine.QUESTIONS_FP), 12)
        client = TestClient(app.app)

        all_resp = client.get("/api/didactic/quiz/questions")
        self.assertEqual(all_resp.status_code, 200)
        all_data = all_resp.json()
        self.assertEqual(len(all_data["questions"]), 12)
        for topic_key in ("color", "geometria", "tipografia", "normativa"):
            self.assertIn(topic_key, all_data["topics"])

        color_resp = client.get("/api/didactic/quiz/questions?topic=color")
        self.assertEqual(color_resp.status_code, 200)
        color_qs = color_resp.json()["questions"]
        self.assertEqual(len(color_qs), 3)
        self.assertTrue(all(q["topic"] == "color" for q in color_qs))

        answers = {}
        for idx, q in enumerate(didactic_engine.QUESTIONS_FP):
            if q["topic"] == "color":
                answers[q["id"]] = q["correct_index"] if idx % 2 == 0 else (q["correct_index"] + 1) % 4

        eval_resp = client.post("/api/didactic/quiz/evaluate", json={"answers": answers, "topic": "color"})
        self.assertEqual(eval_resp.status_code, 200)
        ev = eval_resp.json()
        self.assertEqual(ev["total_questions"], 3)
        self.assertEqual(len(ev["competency_breakdown"]), 1)
        self.assertEqual(ev["competency_breakdown"][0]["topic"], "color")

    def test_exam_mode_custom_rubric_and_competency_tracking(self):
        teacher_client = TestClient(app.app)
        with patch.dict(os.environ, {"INTELLIPRINT_DOCENTE_CODE": "SALESIANOS-FP"}, clear=False):
            r_doc = teacher_client.post(
                "/api/auth/register",
                json={
                    "full_name": "Docente FP",
                    "email": "docente_evo@fp.edu",
                    "password": "Password123!",
                    "role": "docente",
                    "invite_code": "SALESIANOS-FP",
                },
            )
            self.assertEqual(r_doc.status_code, 200, r_doc.text)
            self.assertEqual(r_doc.json()["status"], "ok")

        grp = teacher_client.post(
            "/api/fp/teacher/groups",
            json={"name": "2GS Preimpresion", "center": "CIFP Graficas", "module_name": "Tratamiento"},
        ).json()["group"]

        rubric_resp = teacher_client.post(
            "/api/fp/teacher/rubrics",
            json={
                "title": "Rúbrica Examen Offset",
                "description": "Evaluación sin 1-Clic",
                "criteria": [
                    {"id": "c_color", "name": "Color CMYK / TAC", "weight": 60, "max_score": 10},
                    {"id": "c_geom", "name": "Sangrado y geometría", "weight": 40, "max_score": 10},
                ],
            },
        )
        self.assertEqual(rubric_resp.status_code, 200)
        rubric_id = rubric_resp.json()["rubric"]["id"]

        assign_resp = teacher_client.post(
            "/api/fp/teacher/assignments",
            json={
                "group_id": grp["id"],
                "title": "Examen Triptico CMYK",
                "description": "Corregir paso a paso sin Taller en 1 Clic",
                "assignment_type": "reto",
                "scenario_id": "reto_cartel_sangrado",
                "target_profile": "OFFSET_300",
                "rubric_id": rubric_id,
                "exam_mode": True,
            },
        )
        self.assertEqual(assign_resp.status_code, 200)
        assignment = assign_resp.json()["assignment"]
        self.assertTrue(assignment["exam_mode"])

        student_client = TestClient(app.app)
        r_stu = student_client.post(
            "/api/auth/register",
            json={
                "full_name": "Ane Alumno",
                "email": "ane_evo@fp.edu",
                "password": "Password123!",
                "role": "alumno",
                "class_code": grp["join_code"],
            },
        )
        self.assertEqual(r_stu.status_code, 200)
        self.assertEqual(r_stu.json()["status"], "ok")

        quiz_ans = {q["id"]: q["correct_index"] for q in didactic_engine.QUESTIONS_FP[:4]}
        q_eval = student_client.post("/api/didactic/quiz/evaluate", json={"answers": quiz_ans, "topic": "all"})
        self.assertEqual(q_eval.status_code, 200)

        # Job A: step-by-step (no batch_fix)
        self._make_job_json("job_manual", used_batch=False)
        sub_manual = student_client.post(
            "/api/fp/student/submit",
            json={"assignment_id": assignment["id"], "job_id": "job_manual"},
        )
        self.assertEqual(sub_manual.status_code, 200)
        comp_manual = sub_manual.json()["submission"]["comparison"]
        self.assertFalse(comp_manual["decisions"]["used_batch_fix"])
        self.assertTrue(any("Modo Examen cumplido" in o for o in comp_manual["observations"]))

        # Job B: used batch_fix on exam assignment
        self._make_job_json("job_batch", used_batch=True)
        sub_batch = student_client.post(
            "/api/fp/student/submit",
            json={"assignment_id": assignment["id"], "job_id": "job_batch"},
        )
        self.assertEqual(sub_batch.status_code, 200)
        comp_batch = sub_batch.json()["submission"]["comparison"]
        self.assertTrue(comp_batch["decisions"]["used_batch_fix"])
        self.assertTrue(any("Aviso Modo Examen" in o for o in comp_batch["observations"]))

        # Verify student dashboard & teacher overview expose exam_mode and 4 competencies
        dash = student_client.get("/api/fp/student/dashboard").json()["dashboard"]
        self.assertTrue(dash["assignments"][0]["exam_mode"])
        self.assertEqual(len(dash["competencies"]), 4)
        self.assertTrue(all(k in {c["id"] for c in dash["competencies"]} for k in ("color", "geometria", "tipografia", "normativa")))
        self.assertTrue(any((c.get("evidences") or 0) > 0 for c in dash["competencies"]))

        overview = teacher_client.get(f"/api/fp/teacher/overview?group_id={grp['id']}").json()
        self.assertTrue(any(r["title"] == "Rúbrica Examen Offset" for r in overview["rubrics"]))
        evo_students = overview["evolution"]["students"]
        ane_evo = next((s for s in evo_students if s["email"] == "ane_evo@fp.edu"), None)
        self.assertIsNotNone(ane_evo)
        self.assertEqual(len(ane_evo["competencies"]), 4)

    def test_sqlite_migration_adds_exam_mode_to_legacy_table(self):
        legacy_db = Path(self.tmp.name) / "legacy_fp.db"
        conn = sqlite3.connect(legacy_db)
        conn.execute(
            """
            CREATE TABLE fp_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                assignment_type TEXT DEFAULT 'pdf_real',
                scenario_id TEXT DEFAULT '',
                target_profile TEXT DEFAULT 'OFFSET_300',
                rubric_id INTEGER,
                due_at TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

        fp_classroom.init_fp_db(legacy_db)
        conn2 = sqlite3.connect(legacy_db)
        cols = {row[1] for row in conn2.execute("PRAGMA table_info(fp_assignments)").fetchall()}
        conn2.close()
        self.assertIn("exam_mode", cols)

    def test_teacher_custom_challenge_upload_catalog_load_and_delete(self):
        import pymupdf

        custom_dir = Path(self.tmp.name) / "custom_challenges"
        custom_dir.mkdir(parents=True, exist_ok=True)
        uploads_dir = Path(self.tmp.name) / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        doc = pymupdf.open()
        page = doc.new_page(width=200, height=200)
        page.insert_text((20, 40), "Cartel Prueba RGB", color=(0, 0, 0), fontsize=14)
        pdf_bytes = doc.tobytes()
        doc.close()

        with patch.object(app, "CUSTOM_CHALLENGES_DIR", custom_dir), patch.object(app, "UPLOAD_DIR", uploads_dir):
            teacher_client = TestClient(app.app)
            with patch.dict(os.environ, {"INTELLIPRINT_DOCENTE_CODE": "SALESIANOS-FP"}, clear=False):
                r_doc = teacher_client.post(
                    "/api/auth/register",
                    json={
                        "full_name": "Profesor Reto",
                        "email": "prof_reto@fp.edu",
                        "password": "Password123!",
                        "role": "docente",
                        "invite_code": "SALESIANOS-FP",
                    },
                )
                self.assertEqual(r_doc.status_code, 200, r_doc.text)

            student_client = TestClient(app.app)
            r_stu = student_client.post(
                "/api/auth/register",
                json={
                    "full_name": "Alumno Reto",
                    "email": "alum_reto@fp.edu",
                    "password": "Password123!",
                    "role": "alumno",
                },
            )
            self.assertEqual(r_stu.status_code, 200, r_stu.text)

            # Students cannot upload teacher templates
            forbidden = student_client.post(
                "/api/fp/teacher/challenges",
                data={"title": "Intento Alumno"},
                files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            )
            self.assertEqual(forbidden.status_code, 403)

            # Teacher uploads PDF template without explicit errors -> preflight auto-populates errors
            upload = teacher_client.post(
                "/api/fp/teacher/challenges",
                data={
                    "title": "Reto Propio Cartel Museo",
                    "description": "Revisar sangrado y negro RGB",
                    "target_profile": "OFFSET_300",
                },
                files={"file": ("cartel_museo.pdf", pdf_bytes, "application/pdf")},
            )
            self.assertEqual(upload.status_code, 200)
            challenge = upload.json()["challenge"]
            cid = challenge["id"]
            self.assertTrue(challenge["is_custom"])
            self.assertEqual(challenge["category"], "docente")
            self.assertTrue(len(challenge["target_errors"]) >= 1)
            self.assertTrue((custom_dir / f"{cid}.pdf").exists())

            # Appears in didactic catalog and teacher overview
            catalog = student_client.get("/api/didactic/scenarios").json()["scenarios"]
            self.assertTrue(any(s["id"] == cid and s.get("is_custom") for s in catalog))
            overview = teacher_client.get("/api/fp/teacher/overview").json()
            self.assertTrue(any(c["id"] == cid for c in overview["custom_challenges"]))

            # Can be loaded as a playable preflight challenge & downloaded
            loaded = student_client.post(f"/api/didactic/load-scenario/{cid}")
            self.assertEqual(loaded.status_code, 200)
            payload = loaded.json()
            self.assertEqual(payload["job_id"], f"fp_{cid}")
            self.assertTrue(payload["report"]["job_meta"]["is_custom_challenge"])

            dl = student_client.get(f"/api/didactic/scenario/{cid}/download")
            self.assertEqual(dl.status_code, 200)
            self.assertTrue(dl.content.startswith(b"%PDF-"))

            # Teacher can delete own template
            deleted = teacher_client.delete(f"/api/fp/teacher/challenges/{cid}")
            self.assertEqual(deleted.status_code, 200)
            self.assertFalse((custom_dir / f"{cid}.pdf").exists())
            catalog_after = student_client.get("/api/didactic/scenarios").json()["scenarios"]
            self.assertFalse(any(s["id"] == cid for s in catalog_after))


if __name__ == "__main__":
    unittest.main()
