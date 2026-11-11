"""Image issue rows identify each placed image and include previews when possible."""

import copy
import io
import tempfile
import unittest
from pathlib import Path

import pymupdf
from PIL import Image

from client_report_generator import generate_client_educational_report_pdf


class ClientReportImageIdentificationTests(unittest.TestCase):
    def report(self, indices=(2,)):
        inventory = []
        findings = []
        for index in indices:
            inventory.append({
                "page": 1, "index": index, "xref": 7,
                "bbox": [10, 10, 110, 60],
                "effective_dpi": 121, "colorspace": "RGB",
                "width_px": 169, "height_px": 85,
                "placed_mm": "35.3 × 17.6 mm",
                "is_rgb": True, "is_cmyk": False, "is_gray": False,
            })
            findings.extend([
                {
                    "rule_id": "PRINT_IMAGE_EFFECTIVE_PPI", "severity": "ERROR", "page": 1,
                    "title": "Resolución insuficiente (121 ppp · RGB)",
                    "message": f"Imagen {index} en pág 1: resolución efectiva de 121 ppp. El perfil exige 300 ppp.",
                },
                {
                    "rule_id": "SOURCE_COLOR_DIAGNOSTIC", "severity": "WARNING", "page": 1,
                    "title": "Imagen en modo RGB · 121 ppp (requiere CMYK)",
                    "message": f"Imagen {index} en pág 1: espacio de color RGB. El perfil exige imágenes CMYK.",
                },
            ])
        return {
            "job_meta": {"job_id": "image-issue-test", "filename": "prueba.pdf"},
            "job_summary": {
                "pages": 1, "bleed_detected_mm": 3, "bleed_status": "PASS",
                "target_dpi": 300, "low_res_images": len(indices),
                "non_cmyk_images": len(indices), "images_inventory": inventory,
            },
            "findings": findings,
        }

    def render_pages(self, report, output):
        generate_client_educational_report_pdf(report, output)
        with pymupdf.open(output) as document:
            return [
                {"text": " ".join(page.get_text().split()), "images": len(page.get_images(full=True))}
                for page in document
            ]

    def detail_page(self, pages, index=2):
        title = f"Pág. 1 · Imagen {index}"
        matches = [page for page in pages if title in page["text"]]
        self.assertEqual(len(matches), 1, f"Missing or duplicated image identification: {title}")
        return matches[0]

    def test_resolution_and_color_issues_identify_the_same_placed_image(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            pages = self.render_pages(self.report(), Path(temporary_dir) / "guia.pdf")
        text = " ".join(page["text"] for page in pages)
        self.assertIn("Resolución de Imágenes", text)
        self.assertIn("Imágenes en Modo de Color RGB", text)
        self.assertIn("IMÁGENES QUE REQUIEREN AJUSTES", text)
        detail = self.detail_page(pages)["text"]
        self.assertIn("121 ppp", detail)
        self.assertIn("300 ppp", detail)
        self.assertIn("RGB", detail)
        self.assertIn("CMYK", detail)

    def test_reused_image_is_identified_for_each_placement(self):
        report = self.report(indices=(2, 3))
        self.assertEqual({image["xref"] for image in report["job_summary"]["images_inventory"]}, {7})
        with tempfile.TemporaryDirectory() as temporary_dir:
            pages = self.render_pages(report, Path(temporary_dir) / "guia.pdf")
        for index in (2, 3):
            with self.subTest(index=index):
                detail = self.detail_page(pages, index)["text"]
                self.assertIn(f"Pág. 1 · Imagen {index}", detail)

    def test_available_source_adds_an_image_thumbnail_to_the_identified_row(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            directory = Path(temporary_dir)
            report = self.report()
            without_source = self.render_pages(report, directory / "sin_fuente.pdf")
            source = directory / "source.pdf"
            image = io.BytesIO()
            Image.new("RGB", (169, 85), (220, 50, 40)).save(image, format="PNG")
            with pymupdf.open() as document:
                page = document.new_page(width=200, height=200)
                page.insert_image(pymupdf.Rect(150, 150, 170, 170), stream=image.getvalue())
                xref = page.insert_image(pymupdf.Rect(10, 10, 110, 60), stream=image.getvalue())
                document.save(source)
            with_source_report = copy.deepcopy(report)
            with_source_report["job_meta"]["pdf_path"] = str(source)
            with_source_report["job_summary"]["images_inventory"][0]["xref"] = xref
            with_source = self.render_pages(with_source_report, directory / "con_fuente.pdf")
        self.assertGreater(self.detail_page(with_source)["images"], self.detail_page(without_source)["images"])

    def test_missing_source_still_lists_the_identified_image(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            directory = Path(temporary_dir)
            report = self.report()
            report["job_meta"]["pdf_path"] = str(directory / "missing-source.pdf")
            pages = self.render_pages(report, directory / "guia.pdf")
        detail = self.detail_page(pages)["text"]
        self.assertIn("121 ppp", detail)
        self.assertIn("RGB", detail)


if __name__ == "__main__":
    unittest.main()
