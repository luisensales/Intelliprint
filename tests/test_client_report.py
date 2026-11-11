"""Regression coverage for resolution findings in the designer's PDF guide."""

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import pymupdf

import test_regressions as base
from client_report_generator import (
    _extract_pedagogical_items,
    _resolved_pedagogical_items,
    generate_client_educational_report_pdf,
)


class ClientReportResolutionTests(unittest.TestCase):
    def report(self, findings=(), target_dpi=300, low_res_images=0):
        return {
            "job_meta": {"job_id": "resolution-guide-test", "filename": "prueba.pdf"},
            "job_summary": {
                "pages": 3,
                "bleed_detected_mm": 3,
                "target_dpi": target_dpi,
                "low_res_images": low_res_images,
            },
            "findings": list(findings),
        }

    def finding(self, severity="ERROR", page=1, title=None):
        return {
            "rule_id": "PRINT_IMAGE_EFFECTIVE_PPI",
            "severity": severity,
            "page": page,
            "category": "Imágenes",
            "title": title or "Resolución insuficiente (121 ppp · CMYK)",
            "message": f"Imagen 2 en pág {page}: resolución efectiva de 121 ppp.",
        }

    def resolution_item(self, report):
        matches = [
            item for item in _extract_pedagogical_items(report)
            if item["category"] == "resolution"
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def render_pages(self, report):
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "guia.pdf"
            generate_client_educational_report_pdf(report, output)
            with pymupdf.open(output) as document:
                self.assertGreaterEqual(len(document), 1)
                return [page.get_text() for page in document]

    def render_text(self, report):
        return "\n".join(self.render_pages(report))

    def test_resolution_errors_make_the_guide_require_adjustments(self):
        report = self.report([self.finding()], low_res_images=1)
        item = self.resolution_item(report)
        self.assertEqual(item["severity"], "CRÍTICO")
        text = self.render_text(report)
        self.assertIn("Resolución de Imágenes", text)
        self.assertIn("CRÍTICO", text)
        self.assertIn("REQUIERE AJUSTES PREVIOS", text)
        self.assertNotIn("LISTO PARA IMPRESIÓN", text)

    def test_resolution_warnings_produce_an_amber_recommendation(self):
        report = self.report([self.finding("WARNING")], low_res_images=1)
        item = self.resolution_item(report)
        self.assertEqual(item["severity"], "AVISO")
        text = self.render_text(report)
        self.assertIn("Resolución de Imágenes", text)
        self.assertIn("AVISO", text)
        self.assertIn("RECOMENDACIONES DE MEJORA", text)
        self.assertNotIn("REQUIERE AJUSTES PREVIOS", text)
        self.assertNotIn("LISTO PARA IMPRESIÓN", text)

    def test_unverifiable_resolution_is_included_even_without_low_res_count(self):
        report = self.report([
            self.finding("WARNING", page=3, title="Resolución de imagen no verificable")
        ])
        item = self.resolution_item(report)
        self.assertEqual(item["severity"], "AVISO")
        self.assertIn("3", item["problem"])
        text = self.render_text(report)
        self.assertIn("No Verificable", text)
        self.assertNotIn("LISTO PARA IMPRESIÓN", text)

    def test_mixed_resolution_findings_are_grouped_and_keep_error_severity(self):
        report = self.report([
            self.finding("ERROR", page=1),
            self.finding("WARNING", page=3),
            self.finding("ERROR", page=3),
        ], low_res_images=3)
        item = self.resolution_item(report)
        self.assertEqual(item["severity"], "CRÍTICO")
        self.assertIn("2 errores y 1 aviso", item["problem"])
        self.assertIn("Págs.: 1, 3", item["problem"])
        text = self.render_text(report)
        self.assertIn("2 errores y 1 aviso", text)
        self.assertIn("Págs.: 1, 3", text)

    def test_resolution_stays_visible_when_more_than_four_categories_exist(self):
        findings = [
            {"rule_id": rule, "severity": "WARNING", "page": 1}
            for rule in (
                "BLEED_GEOMETRY_3MM", "SOURCE_COLOR_DIAGNOSTIC",
                "USED_FONTS_EMBEDDED", "RICH_BLACK_SMALL_TEXT",
                "HAIRLINE_DETECTED", "SPOT_COLOR_FOUND", "MAX_INK_COVERAGE",
            )
        ]
        findings.append(self.finding("WARNING", page=2))
        report = self.report(findings, low_res_images=1)
        items = _extract_pedagogical_items(report)
        self.assertGreater(len(items), 4)
        pages = self.render_pages(report)
        self.assertGreaterEqual(len(pages), 2)
        text = " ".join("\n".join(pages).split())
        self.assertIn("Resolución de Imágenes", text)
        for item in items:
            with self.subTest(category=item["category"]):
                self.assertIn(item["title"], text)
        for page in pages:
            page_text = " ".join(page.split())
            self.assertLessEqual(sum(item["title"] in page_text for item in items), 4)

    def test_current_findings_remain_visible_despite_historical_correction_flags(self):
        report = self.report([
            self.finding(),
            {"rule_id": "SOURCE_COLOR_DIAGNOSTIC", "severity": "WARNING", "page": 1},
            {"rule_id": "USED_FONTS_EMBEDDED", "severity": "ERROR", "page": 2},
            {"rule_id": "RICH_BLACK_SMALL_TEXT", "severity": "WARNING", "page": 2},
        ], low_res_images=1)
        report["job_summary"]["non_cmyk_images"] = 10
        report["job_meta"].update({
            "has_cmyk_converted": True,
            "has_fonts_outlined": True,
            "has_overprint_fixed": True,
            "has_batch_fixed": True,
        })
        items = _extract_pedagogical_items(report)
        self.assertEqual({item["category"] for item in items}, {"resolution", "rgb", "fonts", "black"})
        pages = self.render_pages(report)
        self.assertGreaterEqual(len(pages), 1)
        text = " ".join(pages[0].split())
        for item in items:
            with self.subTest(category=item["category"]):
                self.assertIn(item["title"], text)

    def test_unknown_error_uses_current_title_and_full_message(self):
        title = "Perfil ICC de salida ausente: comprobar la condición de impresión acordada con el taller"
        message = (
            "No se ha encontrado un perfil ICC de salida válido para el documento. "
            "Solicita al taller la condición de impresión y vuelve a exportar el PDF "
            "con ese perfil como destino antes de autorizar la producción."
        )
        report = self.report([{
            "rule_id": "UNTRANSLATED_OUTPUT_CONDITION",
            "severity": "ERROR",
            "page": 2,
            "title": title,
            "message": message,
        }])
        text = " ".join(self.render_text(report).split())
        self.assertIn(title, text)
        self.assertIn(message, text)
        self.assertIn("REQUIERE AJUSTES PREVIOS", text)
        self.assertNotIn("LISTO PARA IMPRESIÓN", text)

    def test_correction_flags_without_current_findings_do_not_restore_resolved_errors(self):
        report = self.report()
        report["job_summary"]["non_cmyk_images"] = 0
        report["job_meta"].update({
            "has_cmyk_converted": True,
            "has_fonts_outlined": True,
            "has_overprint_fixed": True,
            "has_hairline_fixed": True,
            "has_spot_converted": True,
            "has_tac_limited": True,
            "has_mirror_bleed": True,
        })
        self.assertEqual(_extract_pedagogical_items(report), [])
        text = self.render_text(report)
        self.assertIn("LISTO PARA IMPRESIÓN", text)
        self.assertNotIn("REQUIERE AJUSTES PREVIOS", text)

    def test_summary_low_resolution_count_is_visible_without_detailed_findings(self):
        report = self.report(low_res_images=2)
        item = self.resolution_item(report)
        self.assertEqual(item["severity"], "AVISO")
        self.assertIn("2", item["problem"])
        text = self.render_text(report)
        self.assertIn("Resolución de Imágenes", text)
        self.assertNotIn("LISTO PARA IMPRESIÓN", text)

    def test_bleed_report_includes_the_complete_third_export_instruction(self):
        report = self.report([{
            "rule_id": "BLEED_GEOMETRY_3MM", "severity": "ERROR", "page": 1,
        }])
        item = next(item for item in _extract_pedagogical_items(report) if item["category"] == "bleed")
        self.assertGreaterEqual(len(item["solution"]), 3)
        text = " ".join(self.render_text(report).split())
        for step in item["solution"]:
            self.assertIn(step, text)

    def test_solution_uses_profile_resolution_and_explains_resampling_limit(self):
        report = self.report([self.finding()], target_dpi=200, low_res_images=1)
        item = self.resolution_item(report)
        solutions = " ".join(item["solution"])
        self.assertIn("200", solutions)
        self.assertNotIn("300", solutions)
        self.assertIn("remuestre", solutions.lower())
        self.assertIn("detalle", solutions.lower())
        text = self.render_text(report)
        self.assertIn("200", text)

    def test_no_resolution_issue_does_not_add_a_resolution_card(self):
        report = self.report()
        items = _extract_pedagogical_items(report)
        self.assertFalse(any(item["category"] == "resolution" for item in items))
        text = self.render_text(report)
        self.assertNotIn("Resolución de Imágenes", text)
        self.assertIn("LISTO PARA IMPRESIÓN", text)

    def test_corrected_and_pending_issues_have_separate_sections(self):
        original = self.report([
            self.finding(),
            {"rule_id": "USED_FONTS_EMBEDDED", "severity": "ERROR", "page": 2},
            {"rule_id": "RICH_BLACK_SMALL_TEXT", "severity": "WARNING", "page": 2},
        ], low_res_images=1)
        report = self.report([self.finding(title="Resolución insuficiente (121 ppp · RGB)")], low_res_images=1)
        report["original_analysis"] = deepcopy(original)
        report["job_meta"]["has_fonts_outlined"] = True
        resolved = _resolved_pedagogical_items(report)
        self.assertEqual({item["category"] for item in resolved}, {"fonts", "black"})
        pages = self.render_pages(report)
        self.assertGreaterEqual(len(pages), 2)
        self.assertIn("INCIDENCIAS PENDIENTES", pages[0])
        text = " ".join("\n".join(pages).split())
        self.assertIn("CORREGIDOS / YA NO DETECTADOS", text)
        self.assertIn("Tipografías No Incrustadas", text)
        self.assertIn("Textos Pequeños en Negro Compuesto", text)
        self.assertIn("pasar a curvas no corrige por sí solo el negro compuesto", text)
        self.assertEqual(text.count("Resolución de Imágenes Insuficiente o No Verificable"), 1)
        self.assertIn("REQUIERE AJUSTES PREVIOS", text)

    def test_partial_correction_preserves_pending_and_initial_page_locations(self):
        first = {"rule_id": "USED_FONTS_EMBEDDED", "severity": "ERROR", "page": 1}
        second = dict(first, page=2)
        report = self.report([second])
        report["original_analysis"] = self.report([first, second])
        report["job_meta"]["has_fonts_outlined"] = True
        self.assertEqual(len(_resolved_pedagogical_items(report)), 1)
        pages = self.render_pages(report)
        self.assertIn("Páginas: 2", pages[0])
        self.assertIn("Páginas: 1", pages[-1])
        self.assertIn("CRÍTICO", pages[0])

    def test_resolved_history_does_not_change_the_current_verdict(self):
        report = self.report()
        report["original_analysis"] = self.report([
            {"rule_id": "USED_FONTS_EMBEDDED", "severity": "ERROR", "page": 1}
        ])
        text = self.render_text(report)
        self.assertIn("LISTO PARA IMPRESIÓN", text)
        self.assertIn("CORREGIDOS / YA NO DETECTADOS", text)
        self.assertIn("Tipografías No Incrustadas", text)
        self.assertNotIn("REQUIERE AJUSTES PREVIOS", text)

    def test_unavailable_initial_analysis_is_explicit_instead_of_invented(self):
        report = self.report([self.finding()], low_res_images=1)
        report["original_analysis_unavailable"] = "No se conserva el PDF original."
        text = self.render_text(report)
        self.assertIn("Historial inicial no disponible", text)
        self.assertNotIn("CORREGIDOS / YA NO DETECTADOS", text)

    def test_long_findings_continue_without_losing_text(self):
        messages = [f"Revisión específica número {i}: comprobar este objeto en el original." for i in range(95)]
        report = self.report([{
            "rule_id": "CUSTOM_REVIEW", "severity": "WARNING", "page": 1,
            "title": "Revisión extensa del documento", "message": "\n".join(messages),
        }])
        pages = self.render_pages(report)
        self.assertGreaterEqual(len(pages), 2)
        text = " ".join("\n".join(pages).split())
        for message in messages:
            self.assertIn(message, text)


class ClientReportEndpointTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp
    upload = base.RegressionTests.upload

    def test_downloaded_designer_guide_preserves_uploaded_resolution_errors(self):
        report = self.upload(with_image=True)
        self.assertTrue(any(
            finding["rule_id"] == "PRINT_IMAGE_EFFECTIVE_PPI"
            and finding["severity"] == "ERROR"
            for finding in report["findings"]
        ))
        job_id = report["job_meta"]["job_id"]
        response = self.client.get(f"/api/download-client-report/{job_id}")
        self.assertEqual(response.status_code, 200, response.text)
        with pymupdf.open(stream=response.content, filetype="pdf") as document:
            self.assertGreaterEqual(len(document), 1)
            text = "\n".join(page.get_text() for page in document)
        self.assertIn("Resolución de Imágenes", text)
        self.assertIn("REQUIERE AJUSTES PREVIOS", text)
        self.assertNotIn("LISTO PARA IMPRESIÓN", text)


if __name__ == "__main__":
    unittest.main()
