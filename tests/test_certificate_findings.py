"""Current certificate findings must survive historical correction flags."""

import copy
import tempfile
import unittest
from pathlib import Path

import pymupdf

from report_generator import generate_preflight_certificate_pdf


class CertificateFindingsTests(unittest.TestCase):
    def report(self, findings):
        return {
            "job_meta": {
                "job_id": "certificate-findings-test",
                "filename": "prueba.pdf",
                "current_sha256": "a" * 64,
                "has_cmyk_converted": True,
                "has_fonts_outlined": True,
                "has_overprint_fixed": True,
                "has_varnish_overprint_fixed": True,
                "has_hairline_fixed": True,
                "has_icc_fixed": True,
                "has_bleed_fixed": True,
            },
            "job_summary": {"pages": 2, "target_dpi": 300},
            "findings": findings,
            "triple_result": {
                "technical": {"status": "PASS", "errors_count": 0, "warnings_count": 0},
                "content": {"status": "RESOLVED", "suggestions_count": 0},
                "release": {"status": "PENDING_AUTHORIZATION"},
            },
        }

    def render_text(self, report):
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "certificado.pdf"
            generate_preflight_certificate_pdf(report, output)
            with pymupdf.open(output) as document:
                return "\n".join(page.get_text() for page in document)

    def test_pending_errors_are_not_hidden_by_prior_cmyk_fonts_or_overprint_actions(self):
        findings = [
            {
                "page": 1, "rule_id": "PRINT_IMAGE_EFFECTIVE_PPI", "severity": "ERROR",
                "title": "Resolución insuficiente (121 ppp · RGB)",
                "message": "Imagen RGB con resolución efectiva de 121 ppp; el perfil exige 300 ppp.",
            },
            {
                "page": 2, "rule_id": "USED_FONTS_EMBEDDED", "severity": "ERROR",
                "title": "Fuente no incrustada: Helvetica",
                "message": "La fuente Helvetica sigue sin incrustar en la página 2.",
            },
            {
                "page": 2, "rule_id": "BLACK_TEXT_KNOCKOUT", "severity": "ERROR",
                "title": "Texto negro en calado",
                "message": "El texto negro de la página 2 sigue sin sobreimprimir.",
            },
        ]
        report = self.report(copy.deepcopy(findings))
        text = self.render_text(report)
        self.assertIn("NO CUMPLE", text)
        self.assertIn("3 errores, 0 avisos", text)
        self.assertEqual(text.count("[ERROR] Pág"), 3)
        for finding in findings:
            with self.subTest(rule=finding["rule_id"]):
                self.assertIn(finding["title"], text)
        self.assertNotIn("Documento totalmente limpio", text)
        self.assertEqual(report["findings"], findings)
        self.assertEqual(report["job_meta"]["certificate_identity_version"], 3)
        self.assertEqual(report["job_meta"]["certificate_sha256"], "a" * 64)

    def test_prior_corrections_without_current_findings_remain_clean(self):
        report = self.report([])
        text = self.render_text(report)
        self.assertIn("CUMPLE", text)
        self.assertIn("0 errores, 0 avisos", text)
        self.assertIn("Documento totalmente limpio", text)
        self.assertNotIn("NO CUMPLE", text)
        self.assertNotIn("[ERROR]", text)
        self.assertEqual(report["findings"], [])


if __name__ == "__main__":
    unittest.main()
