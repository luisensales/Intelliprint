"""Initial preflight history survives corrections and legacy report downloads."""

from copy import deepcopy
from contextlib import ExitStack
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app
import hotfolder_engine as hotfolder
from analysis_history import capture_original_analysis, ensure_original_analysis
from document_identity import sha256_file
import test_regressions as base


def analysis(rule="USED_FONTS_EMBEDDED"):
    findings = ([{"rule_id": rule, "severity": "ERROR", "page": 1,
                  "title": "Fuente no incrustada", "message": "Falta Helvetica."}]
                if rule else [])
    return {"job_summary": {"pages": 1, "bleed_detected_mm": 3,
                            "images_inventory": [{"effective_dpi": 121}]},
            "findings": findings,
            "triple_result": {"technical": {"status": "FAIL" if rule else "PASS",
                                             "errors_count": len(findings), "warnings_count": 0}}}


class AnalysisHistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_snapshot_is_deeply_copied_and_is_never_replaced(self):
        report = analysis()
        expected = deepcopy(report)
        self.assertTrue(capture_original_analysis(report))
        report["findings"][0]["title"] = "changed"
        report["job_summary"]["images_inventory"][0]["effective_dpi"] = 300
        report["triple_result"]["technical"]["status"] = "PASS"
        self.assertFalse(capture_original_analysis(report, analysis(None)))
        self.assertEqual(report["original_analysis"], expected)

    def test_legacy_recovery_analyzes_only_the_original_source(self):
        source, fixed = self.root / "source.pdf", self.root / "fixed.pdf"
        source.write_bytes(b"%PDF original")
        fixed.write_bytes(b"%PDF corrected")
        report = analysis(None)
        current = deepcopy(report)
        report["job_meta"] = {"pdf_path": str(source), "last_fixed_pdf_path": str(fixed),
                              "original_sha256": sha256_file(source), "profile_id": "DIGITAL_200"}
        run = Mock(return_value=analysis())
        self.assertTrue(ensure_original_analysis(report, run, (self.root,)))
        run.assert_called_once_with(str(source.resolve()), profile_id="DIGITAL_200", icc_choice="preserve")
        self.assertEqual(report["original_analysis"], analysis())
        self.assertEqual(report["findings"], current["findings"])
        self.assertEqual(report["job_summary"], current["job_summary"])
        self.assertEqual(report["triple_result"], current["triple_result"])

    def test_corrected_output_cannot_be_recorded_as_original(self):
        fixed = self.root / "fixed.pdf"
        fixed.write_bytes(b"%PDF corrected")
        report = analysis(None)
        report["job_meta"] = {"pdf_path": str(fixed), "last_fixed_pdf_path": str(fixed)}
        run = Mock()
        self.assertTrue(ensure_original_analysis(report, run, (self.root,)))
        run.assert_not_called()
        self.assertNotIn("original_analysis", report)
        self.assertIn("original_analysis_unavailable", report)

    def test_missing_original_with_fixes_does_not_invent_history(self):
        report = analysis(None)
        report["job_meta"] = {"pdf_path": str(self.root / "missing.pdf"), "has_fonts_outlined": True}
        run = Mock()
        self.assertTrue(ensure_original_analysis(report, run, (self.root,)))
        run.assert_not_called()
        self.assertNotIn("original_analysis", report)
        self.assertIn("original_analysis_unavailable", report)
        self.assertFalse(ensure_original_analysis(report, run, (self.root,)))

    def test_no_fixes_allows_current_analysis_when_source_is_missing(self):
        report = analysis()
        expected = deepcopy(report)
        report["job_meta"] = {"pdf_path": str(self.root / "missing.pdf")}
        self.assertTrue(ensure_original_analysis(report, Mock(), (self.root,)))
        self.assertEqual(report["original_analysis"], expected)

    def test_history_failure_does_not_raise_or_replace_current_findings(self):
        source = self.root / "source.pdf"
        source.write_bytes(b"%PDF original")
        report = analysis(None)
        report["job_meta"] = {"pdf_path": str(source), "has_fonts_outlined": True}
        self.assertTrue(ensure_original_analysis(report, Mock(side_effect=ValueError("broken PDF")), (self.root,)))
        self.assertEqual(report["findings"], [])
        self.assertNotIn("original_analysis", report)
        self.assertIn("original_analysis_unavailable", report)

    def test_legacy_source_outside_managed_roots_is_not_read(self):
        source = self.root / "outside.pdf"
        source.write_bytes(b"%PDF outside")
        managed = self.root / "managed"
        managed.mkdir()
        report = analysis(None)
        report["job_meta"] = {"pdf_path": str(source), "has_fonts_outlined": True}
        run = Mock()
        ensure_original_analysis(report, run, (managed,))
        run.assert_not_called()
        self.assertNotIn("original_analysis", report)


class AnalysisHistoryEndpointTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp
    upload = base.RegressionTests.upload

    def saved(self, job_id):
        return json.loads((self.jobs / (job_id + ".json")).read_text(encoding="utf-8"))

    def test_initial_upload_persists_a_separate_original_analysis(self):
        report = self.upload()
        original = report["original_analysis"]
        self.assertEqual(original["findings"], report["findings"])
        self.assertEqual(original["job_summary"], report["job_summary"])
        self.assertEqual(original["triple_result"]["technical"], report["triple_result"]["technical"])
        self.assertEqual(self.saved(report["job_meta"]["job_id"])["original_analysis"], original)

    def test_cmyk_correction_keeps_original_color_error_and_current_resolution_error(self):
        initial = self.upload()
        job_id = initial["job_meta"]["job_id"]
        response = self.client.post("/api/convert-to-cmyk/" + job_id)
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()["report"]
        self.assertEqual(report["original_analysis"], initial["original_analysis"])
        original_rules = {finding["rule_id"] for finding in report["original_analysis"]["findings"]}
        current_rules = {finding["rule_id"] for finding in report["findings"]}
        self.assertIn("SOURCE_COLOR_DIAGNOSTIC", original_rules)
        self.assertNotIn("SOURCE_COLOR_DIAGNOSTIC", current_rules)
        self.assertIn("PRINT_IMAGE_EFFECTIVE_PPI", current_rules)

    def test_legacy_guide_download_recovers_and_persists_history_without_changing_current_analysis(self):
        initial = self.upload()
        job_id = initial["job_meta"]["job_id"]
        response = self.client.post("/api/convert-to-cmyk/" + job_id)
        self.assertEqual(response.status_code, 200, response.text)
        current = response.json()["report"]
        del current["original_analysis"]
        (self.jobs / (job_id + ".json")).write_text(json.dumps(current), encoding="utf-8")
        response = self.client.get("/api/download-client-report/" + job_id)
        self.assertEqual(response.status_code, 200, response.text)
        saved = self.saved(job_id)
        self.assertEqual(saved["original_analysis"], initial["original_analysis"])
        self.assertEqual(saved["findings"], current["findings"])
        self.assertEqual(saved["job_summary"], current["job_summary"])
        self.assertEqual(saved["triple_result"], current["triple_result"])
        self.assertEqual(saved["job_meta"]["current_sha256"], current["job_meta"]["current_sha256"])
        # Once recovered, another download must not re-analyze or rewrite history.
        with patch.object(app.engine, "run_preflight", side_effect=AssertionError("must reuse snapshot")):
            self.assertEqual(self.client.get("/api/download-client-report/" + job_id).status_code, 200)

    def test_batch_upload_captures_initial_analysis(self):
        with patch.object(hotfolder, "run_pdf_task", return_value=analysis()):
            result = hotfolder.process_batch_upload([("batch.pdf", base.sample_pdf(False))])[0]
        self.assertNotEqual(result["status"], "ERROR", result)
        report = self.saved(result["job_id"])
        self.assertEqual(report["original_analysis"]["findings"], report["findings"])

    def test_refresh_recovers_legacy_history_before_replacing_current_analysis(self):
        source = self.uploads / "legacy" / "source.pdf"
        source.parent.mkdir()
        source.write_bytes(base.sample_pdf(False))
        report = analysis()
        report["job_meta"] = {"pdf_path": str(source), "has_fonts_outlined": True}
        with patch.object(app.engine, "run_preflight", side_effect=[analysis(None), analysis()]):
            app.refresh_job_analysis(report, self.root / "corrected.pdf")
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["original_analysis"]["findings"], analysis()["findings"])

    def test_refresh_continues_when_missing_original_prevents_history_recovery(self):
        report = analysis()
        report["job_meta"] = {"pdf_path": str(self.uploads / "missing.pdf"), "has_fonts_outlined": True}
        with patch.object(app.engine, "run_preflight", return_value=analysis(None)):
            app.refresh_job_analysis(report, self.root / "corrected.pdf")
        self.assertEqual(report["findings"], [])
        self.assertNotIn("original_analysis", report)
        self.assertIn("original_analysis_unavailable", report)

    def test_hotfolder_keeps_initial_findings_after_automatic_correction(self):
        with ExitStack() as stack:
            for name in ("IN_DIR", "PROCESSING_DIR", "APPROVED_DIR", "REJECTED_DIR"):
                path = self.root / name
                path.mkdir()
                stack.enter_context(patch.object(hotfolder, name, path))
            stack.enter_context(patch.object(hotfolder, "LOGS_FILE", self.root / "events.json"))
            engine = Mock()
            engine.run_preflight.side_effect = [analysis(), analysis(None)]
            stack.enter_context(patch("preflight_engine.IntelliPrintEngine", return_value=engine))

            def fix(source, output, **options):
                shutil.copyfile(source, output)
                return {"status": "success"}

            stack.enter_context(patch.object(hotfolder, "apply_full_batch_fix", fix))
            source = hotfolder.IN_DIR / "original.pdf"
            source.write_bytes(base.sample_pdf(False))
            service = hotfolder.HotFolderService()
            service.auto_fix, service.generate_reports = True, False
            event = service._process_file_in_worker(source, "history_test")
        self.assertEqual(event["status"], "APPROVED", event)
        report = self.saved("history_test")
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["original_analysis"]["findings"], analysis()["findings"])


if __name__ == "__main__":
    unittest.main()
