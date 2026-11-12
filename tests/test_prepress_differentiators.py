import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pikepdf
import pymupdf
from fastapi.testclient import TestClient
from PIL import Image

import app as app_module
from color_converter import convert_rgb_vectors_to_cmyk
from preflight_engine import IntelliPrintEngine
from separations_viewer import render_page_separation_with_meta


ICC_CMYK = Path(__file__).resolve().parent.parent / "icc_profiles" / "ISOcoated_v2_300_bas.icc"


def _make_tac_test_pdf(path: Path, fill_cmyk=(0.95, 0.90, 0.90, 0.90), include_boxes=True) -> None:
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(200, 200))
    if include_boxes:
        page.BleedBox = pikepdf.Array([10, 10, 190, 190])
        page.TrimBox = pikepdf.Array([20, 20, 180, 180])
    c, m, y, k = fill_cmyk
    stream = f"q {c} {m} {y} {k} k 40 40 120 120 re f Q\n".encode("ascii")
    page.Contents = pdf.make_stream(stream)
    pdf.save(str(path))
    pdf.close()


def _make_rgb_vector_and_text_pdf(path: Path) -> None:
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(300, 300))
    page.Resources = pikepdf.Dictionary(
        Font=pikepdf.Dictionary(
            F1=pikepdf.Dictionary(
                Type=pikepdf.Name.Font,
                Subtype=pikepdf.Name.Type1,
                BaseFont=pikepdf.Name.Helvetica,
            )
        )
    )
    stream = (
        b"q\n"
        b"0 0 0 rg\n"
        b"BT /F1 12 Tf 40 240 Td (Texto negro RGB Canva/Word) Tj ET\n"
        b"0.502 0.502 0.502 rg\n"
        b"BT /F1 10 Tf 40 210 Td (Gris neutro RGB) Tj ET\n"
        b"0.9 0.1 0.1 rg 0.1 0.2 0.8 RG 2 w\n"
        b"40 60 120 80 re B\n"
        b"Q\n"
    )
    page.Contents = pdf.make_stream(stream)
    pdf.save(str(path))
    pdf.close()


class TestPrepressDifferentiators(unittest.TestCase):
    def test_tac_heatmap_detects_over_inked_pixels_and_clean_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            heavy_pdf = tmp_dir / "heavy_365.pdf"
            clean_pdf = tmp_dir / "clean_180.pdf"
            _make_tac_test_pdf(heavy_pdf, fill_cmyk=(0.95, 0.90, 0.90, 0.90), include_boxes=False)
            _make_tac_test_pdf(clean_pdf, fill_cmyk=(0.60, 0.40, 0.20, 0.0), include_boxes=False)

            heavy_bytes, heavy_meta = render_page_separation_with_meta(
                heavy_pdf, page_index=0, dpi=72, show_tac_heatmap=True, tac_limit=300
            )
            with Image.open(io.BytesIO(heavy_bytes)) as img:
                arr = np.asarray(img)
            self.assertGreater(heavy_meta["tac_max_pct"], 340.0)
            self.assertGreater(heavy_meta["tac_over_area_pct"], 20.0)
            # Severe excess area must show strong red highlight (high R, low G/B).
            red_pixels = np.sum((arr[:, :, 0] > 200) & (arr[:, :, 1] < 80) & (arr[:, :, 2] < 100))
            self.assertGreater(red_pixels, 100)

            _clean_bytes, clean_meta = render_page_separation_with_meta(
                clean_pdf, page_index=0, dpi=72, show_tac_heatmap=True, tac_limit=300
            )
            self.assertLessEqual(clean_meta["tac_max_pct"], 130.0)
            self.assertEqual(clean_meta["tac_over_area_pct"], 0.0)

    def test_pdf_box_guides_overlay_draws_trim_bleed_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "boxes.pdf"
            _make_tac_test_pdf(pdf_path, fill_cmyk=(0.0, 0.0, 0.0, 0.0), include_boxes=True)

            base_bytes, _ = render_page_separation_with_meta(pdf_path, dpi=100, show_boxes=False)
            guided_bytes, guided_meta = render_page_separation_with_meta(pdf_path, dpi=100, show_boxes=True)

            self.assertEqual([b["label"] for b in guided_meta["boxes"]], ["MediaBox", "BleedBox", "TrimBox"])
            with Image.open(io.BytesIO(base_bytes)) as b_img, Image.open(io.BytesIO(guided_bytes)) as g_img:
                diff = np.abs(np.asarray(g_img, dtype=np.int16) - np.asarray(b_img, dtype=np.int16)).sum()
            self.assertGreater(diff, 10000)

    def test_convert_rgb_vectors_and_text_to_cmyk_and_pure_k(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            src_pdf = tmp_dir / "rgb_vec.pdf"
            dst_pdf = tmp_dir / "cmyk_vec.pdf"
            _make_rgb_vector_and_text_pdf(src_pdf)

            engine = IntelliPrintEngine()
            pre_report = engine.run_preflight(str(src_pdf), profile_id="OFFSET_300")
            self.assertGreater(pre_report["job_summary"]["rgb_vector_stats"]["rgb_text_ops"], 0)
            self.assertGreater(pre_report["job_summary"]["rgb_vector_stats"]["rgb_black_text_ops"], 0)
            self.assertGreater(pre_report["job_summary"]["rgb_vector_stats"]["rgb_vector_ops"], 0)

            res = convert_rgb_vectors_to_cmyk(src_pdf, ICC_CMYK, output_path=dst_pdf)
            self.assertTrue(res["success"])
            self.assertEqual(res["text_ops_converted"], 2)
            self.assertEqual(res["vector_ops_converted"], 1)
            self.assertGreaterEqual(res["pure_k_ops"], 1)
            self.assertGreaterEqual(res["neutral_k_ops"], 1)
            self.assertGreaterEqual(res["chromatic_cmyk_ops"], 2)
            self.assertEqual(res["black_text_overprinted"], 1)

            post_report = engine.run_preflight(str(dst_pdf), profile_id="OFFSET_300")
            post_rgb = post_report["job_summary"]["rgb_vector_stats"]
            self.assertEqual(post_rgb["rgb_text_ops"], 0)
            self.assertEqual(post_rgb["rgb_black_text_ops"], 0)
            self.assertEqual(post_rgb["rgb_vector_ops"], 0)

            # Black RGB text must be 100% K only -> zero ink on CMY channels when K is disabled.
            cmy_only_bytes, cmy_meta = render_page_separation_with_meta(
                dst_pdf, page_index=0, show_c=True, show_m=True, show_y=True, show_k=False, dpi=72
            )
            self.assertIsInstance(cmy_only_bytes, bytes)
            self.assertIsNotNone(cmy_meta)

            with pikepdf.open(str(dst_pdf)) as check_pdf:
                cmds = list(pikepdf.parse_content_stream(check_pdf.pages[0]))
                k_ops = [[float(v) for v in op[0]] for op in cmds if str(op[1]) == "k"]
                self.assertIn([0.0, 0.0, 0.0, 1.0], k_ops)

    def test_endpoints_separations_headers_and_vector_conversion_api(self):
        client = TestClient(app_module.app)
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "api_vec.pdf"
            _make_rgb_vector_and_text_pdf(pdf_path)
            with open(pdf_path, "rb") as f:
                up_resp = client.post(
                    "/api/check",
                    files={"file": ("api_vec.pdf", f, "application/pdf")},
                    data={"profile": "OFFSET_300"},
                )
            self.assertEqual(up_resp.status_code, 200)
            job_id = up_resp.json()["job_meta"]["job_id"]

            try:
                sep_resp = client.get(
                    f"/api/separations/{job_id}",
                    params={"page": 1, "tac_heatmap": "true", "tac_limit": 280, "show_boxes": "true"},
                )
                self.assertEqual(sep_resp.status_code, 200)
                self.assertIn("x-tac-max-pct", {k.lower() for k in sep_resp.headers})
                self.assertIn("x-tac-over-area-pct", {k.lower() for k in sep_resp.headers})
                self.assertEqual(sep_resp.headers.get("X-Tac-Limit"), "280")

                conv_resp = client.post(
                    f"/api/convert-vectors-cmyk/{job_id}",
                    data={"use_embedded_icc": "true"},
                )
                self.assertEqual(conv_resp.status_code, 200)
                body = conv_resp.json()
                self.assertEqual(body["status"], "success")
                self.assertGreaterEqual(body["text_ops_converted"], 2)
                self.assertGreaterEqual(body["pure_k_ops"], 1)
                self.assertEqual(body["report"]["job_summary"]["rgb_vector_stats"]["rgb_text_ops"], 0)
            finally:
                for p in (
                    app_module.JOBS_DIR.glob(f"{job_id}*")
                ):
                    try:
                        p.unlink(missing_ok=True)
                    except OSError:
                        pass
                up_dir = app_module.UPLOAD_DIR / job_id
                if up_dir.exists():
                    for child in up_dir.glob("*"):
                        child.unlink(missing_ok=True)
                    try:
                        up_dir.rmdir()
                    except OSError:
                        pass


if __name__ == "__main__":
    unittest.main()
