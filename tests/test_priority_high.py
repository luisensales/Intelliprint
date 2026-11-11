import asyncio
import json
import tempfile
import unittest
import zlib
import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pikepdf
import app
import security_limits as limits
from pdf_graphics import resolve_color_space, color_is_white
import test_regressions as base


class PdfGuards(unittest.TestCase):
    def test_screen_guide_recommends_rgb_instead_of_cmyk(self):
        from client_report_generator import _extract_pedagogical_items
        items = _extract_pedagogical_items({
            'job_summary': {'required_color_family': 'RGB'},
            'findings': [{'rule_id': 'SOURCE_COLOR_DIAGNOSTIC', 'severity': 'WARNING'}]})
        self.assertIn('CMYK', items[0]['title'])
        self.assertIn('sRGB', ' '.join(items[0]['solution']))
        self.assertNotIn('Color CMYK', ' '.join(items[0]['solution']))

    def test_icc_white_overprint_is_reported_by_the_real_preflight(self):
        import icc_manager
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'white.pdf'
            with pikepdf.new() as pdf:
                page = pdf.add_blank_page(page_size=(200, 200))
                profile = pdf.make_stream((icc_manager.ICC_DIR / 'ISOcoated_v2_eci.icc').read_bytes())
                profile.N = 4
                page.Resources = pikepdf.Dictionary(
                    ColorSpace=pikepdf.Dictionary(CS=pikepdf.Array([pikepdf.Name.ICCBased, profile])),
                    ExtGState=pikepdf.Dictionary(GS=pikepdf.Dictionary(op=True, OP=True)))
                page.Contents = pdf.make_stream(b'/GS gs /CS cs 0 0 0 0 scn 20 20 80 80 re f')
                pdf.save(path)
            icc_manager.apply_icc_to_pdf(path, 'ISOcoated_v2_eci.icc')
            report = app.engine.run_preflight(str(path))
            self.assertIn('WHITE_OVERPRINT', {f['rule_id'] for f in report['findings']})
            self.assertEqual(report['triple_result']['technical']['status'], 'FAIL')

    def test_inline_limits_include_nested_forms(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'inline.pdf'
            for nested in (False, True):
                with self.subTest(nested=nested), pikepdf.new() as pdf:
                    page = pdf.add_blank_page()
                    content = b'BI /W 5000 /H 5000 /BPC 1 /CS /G /F /Fl ID ' + zlib.compress(b'\0' * 3125000) + b' EI'
                    if nested:
                        form = pdf.make_stream(content)
                        form.Type, form.Subtype = pikepdf.Name.XObject, pikepdf.Name.Form
                        form.BBox = [0, 0, 100, 100]
                        form.Resources = pikepdf.Dictionary()
                        page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Fm=form))
                        content = b'/Fm Do'
                    page.Contents = pdf.make_stream(content)
                    pdf.save(path)
                with self.assertRaises(limits.ResourceLimitError):
                    limits.validate_pdf_resources(path)

    def test_icc_channels_are_examined_as_colors_not_unknown(self):
        with pikepdf.new() as pdf:
            for channels, white in ((1, (1,)), (3, (1, 1, 1)), (4, (0, 0, 0, 0))):
                profile = pdf.make_stream(b'profile')
                profile.N = channels
                family = {1: 'GRAY', 3: 'RGB', 4: 'CMYK'}[channels]
                with patch('icc_manager.validate_icc_bytes', return_value=(family, 'Test')):
                    space = resolve_color_space(pikepdf.Array([pikepdf.Name.ICCBased, profile]), {})
                self.assertTrue(color_is_white(space, white))
            profile.N = 2
            with self.assertRaises(ValueError):
                resolve_color_space(pikepdf.Array([pikepdf.Name.ICCBased, profile]), {})


class SlowUploads(unittest.IsolatedAsyncioTestCase):
    async def test_upload_does_not_hold_processing_and_expires(self):
        messages = []
        entered = asyncio.Event()
        async def downstream(*args):
            self.fail('Incomplete request reached processing')
        async def receive():
            entered.set()
            await asyncio.Event().wait()
        async def send(message):
            messages.append(message)
        middleware = limits.RequestLimitsMiddleware(downstream)
        with patch.object(limits, 'UPLOAD_TIMEOUT_SEC', .05):
            task = asyncio.create_task(middleware(
                {'type': 'http', 'method': 'POST', 'path': '/api/check', 'headers': []}, receive, send))
            await entered.wait()
            self.assertTrue(middleware.active.acquire(blocking=False))
            middleware.active.release()
            await asyncio.wait_for(task, 2)
        self.assertEqual(messages[0]['status'], 408)
        self.assertTrue(middleware.admitted.acquire(blocking=False))
        middleware.admitted.release()


class DerivedArtifacts(unittest.TestCase):
    setUp = base.RegressionTests.setUp
    upload = base.RegressionTests.upload

    def test_zip_preserves_jobs_with_identical_display_names(self):
        ids = [self.upload(False)['job_meta']['job_id'] for _ in range(2)]
        response = self.client.post('/api/batch/download-zip', json={'job_ids': ids})
        self.assertEqual(response.status_code, 200, response.text[:100])
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), len(set(names)))
            pdfs = [name for name in names if name.startswith('PDFs_Listos_Impresion/')]
            self.assertEqual(len(pdfs), 2)
            for job_id in ids:
                self.assertTrue(any(job_id in name for name in pdfs))

    def test_pdf_change_invalidates_imposition_and_ppf_parameters_are_honored(self):
        initial = self.upload()
        job_id = initial['job_meta']['job_id']
        result = self.client.post('/api/imposition/generate/' + job_id, json={
            'add_marks': False, 'add_reg_crosses': False, 'add_color_bar': False, 'add_slug': False})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.client.get('/api/imposition/download/' + job_id).status_code, 200)
        for volume in (1000, 2500):
            response = self.client.get(f'/api/cip3/download/ppf/{job_id}?num_zones=16&run_length={volume}')
            self.assertEqual(response.status_code, 200, response.text[:100])
            self.assertIn(f'/CIP3AdmPrintVolume {volume} def'.encode(), response.content)
        result = self.client.post('/api/convert-to-cmyk/' + job_id)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.client.get('/api/imposition/download/' + job_id).status_code, 404)
        saved = json.loads((self.jobs / (job_id + '.json')).read_text(encoding='utf-8'))
        self.assertNotIn('imposed_pdf_path', saved['job_meta'])
        self.assertNotIn('last_cip3_calculation', saved['job_meta'])
