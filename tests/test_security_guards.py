"""Security regressions: reject attacks before writing, parsing or rendering."""

import asyncio
import io
import math
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pikepdf
import pymupdf
from fastapi.testclient import TestClient

import app
import security_limits as limits
import upload_security
import test_regressions as base


class SecurityGuardTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp
    upload = base.RegressionTests.upload

    def test_imposition_rejects_traversal_before_generating_output(self):
        job_id = self.upload(False)['job_meta']['job_id']
        attacks = ('x/../../didactic_scenarios/reto_tarjeta_richblack',
                   '..\\..\\escape', '/tmp/escape', 'C:\\escape', 'UNKNOWN')
        for size in attacks:
            with self.subTest(size=size), patch.object(app, 'generate_imposed_pdf') as generate:
                response = self.client.post('/api/imposition/generate/' + job_id, json={'sheet_size': size})
                self.assertEqual(response.status_code, 422, response.text)
                generate.assert_not_called()
        self.assertEqual(list(self.jobs.glob('*imposicion*')), [])

    def test_release_rejects_paths_without_creating_a_certificate(self):
        job_id = self.upload(False)['job_meta']['job_id']
        for value in ('../' + job_id, '..\\' + job_id, str(self.root / job_id)):
            with self.subTest(value=value), patch.object(app, 'generate_preflight_certificate_pdf') as generate:
                response = self.client.post('/api/release', data={
                    'job_id': value, 'operator_name': 'Test', 'decision': 'approved'})
                self.assertEqual(response.status_code, 422, response.text)
                generate.assert_not_called()
        self.assertEqual(list(self.root.glob('*ficha_tecnica.pdf')), [])

    def test_containment_rejects_escape_and_accepts_a_normal_job(self):
        with self.assertRaises(ValueError):
            limits.contained_job_path(self.jobs, '../outside.pdf')
        self.assertEqual(limits.contained_job_path(self.jobs, 'test.pdf'), (self.jobs / 'test.pdf').resolve())

    def test_valid_imposition_still_creates_a_downloadable_pdf(self):
        job_id = self.upload(False)['job_meta']['job_id']
        response = self.client.post('/api/imposition/generate/' + job_id,
                                    json={'sheet_size': 'sra3', 'add_color_bar': False, 'add_slug': False})
        self.assertEqual(response.status_code, 200, response.text)
        output = Path(response.json()['output_pdf_path'])
        self.assertTrue(output.resolve().is_relative_to(self.jobs.resolve()))
        self.assertTrue(output.is_file())
        self.assertEqual(self.client.get(response.json()['download_url']).status_code, 200)

    def test_all_preview_routes_reject_unbounded_dpi_before_rendering(self):
        job_id = self.upload(False)['job_meta']['job_id']
        for route, renderer in (
                ('imposition/preview', 'render_imposition_preview_image'),
                ('barcodes/preview', 'render_barcode_preview_image'),
                ('safety-margin/preview', 'render_safety_margin_preview'),
                ('separations', 'render_page_separation'),
                ('render-comparison', None)):
            for dpi in (0, -1, 1000, 'nan'):
                with self.subTest(route=route, dpi=dpi):
                    response = self.client.get(f'/api/{route}/{job_id}?dpi={dpi}')
                    self.assertEqual(response.status_code, 422, response.text)
        with patch.object(app, 'render_imposition_preview_image') as render:
            response = self.client.get(f'/api/imposition/preview/{job_id}?sheet_size=../escape')
            self.assertEqual(response.status_code, 422)
            render.assert_not_called()

    def test_oversized_uploads_leave_no_partial_files(self):
        content = base.sample_pdf(False)
        with patch.object(upload_security, 'MAX_FILE_BYTES', len(content) - 1):
            for route in ('check', 'inspect-pdf'):
                with self.subTest(route=route):
                    response = self.client.post('/api/' + route, files={'file': ('large.pdf', content)})
                    self.assertEqual(response.status_code, 413, response.text)
                    self.assertEqual(list(self.uploads.iterdir()), [])
                    self.assertEqual(list(self.jobs.iterdir()), [])

    def test_batch_limits_are_checked_before_processing_any_file(self):
        content = base.sample_pdf(False)
        files = [('files', ('one.pdf', content)), ('files', ('two.pdf', content))]
        for setting, value in (('MAX_BATCH_BYTES', len(content) * 2 - 1),
                               ('MAX_FILE_BYTES', len(content) - 1), ('MAX_BATCH_FILES', 1)):
            with self.subTest(setting=setting), patch.object(app, setting, value), \
                    patch.object(app, 'process_batch_upload') as process:
                response = self.client.post('/api/batch/upload', files=files)
                self.assertEqual(response.status_code, 413, response.text)
                process.assert_not_called()
        self.assertEqual(list(self.uploads.iterdir()), [])

    def test_pdf_page_and_native_image_limits_precede_decoding(self):
        with pymupdf.open() as doc:
            doc.new_page(); doc.new_page()
            content = doc.tobytes()
        with patch.object(limits, 'MAX_PDF_PAGES', 1):
            response = self.client.post('/api/check', files={'file': ('pages.pdf', content)})
            self.assertEqual(response.status_code, 413, response.text)
        with pikepdf.new() as pdf:
            page = pdf.add_blank_page(page_size=(200, 200))
            image = pdf.make_stream(b'\0\0\0')
            image.Type = pikepdf.Name.XObject
            image.Subtype = pikepdf.Name.Image
            image.Width = image.Height = 10000
            image.BitsPerComponent = 8
            image.ColorSpace = pikepdf.Name.DeviceRGB
            page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im=image))
            page.Contents = pdf.make_stream(b'q 200 0 0 200 0 0 cm /Im Do Q')
            stream = io.BytesIO(); pdf.save(stream)
        response = self.client.post('/api/check', files={'file': ('bomb.pdf', stream.getvalue())})
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(list(self.uploads.iterdir()), [])
        self.assertEqual(list(self.jobs.iterdir()), [])

    def test_pixel_budget_applies_to_huge_and_narrow_pages(self):
        for width, height in ((1418, 1985), (14400, 14400), (14400, 1), (200, 300)):
            dpi = limits.bounded_render_dpi(pymupdf.Rect(0, 0, width, height), 10000)
            w, h = math.ceil(width * dpi / 72), math.ceil(height * dpi / 72)
            self.assertLessEqual(w * h, limits.MAX_RENDER_PIXELS)
            self.assertLessEqual(max(w, h), limits.MAX_RENDER_EDGE)
        for dpi in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                limits.bounded_render_dpi(pymupdf.Rect(0, 0, 100, 100), dpi)

    def test_pdf_processing_does_not_block_status_requests(self):
        report = self.upload(False)
        started, finish = threading.Event(), threading.Event()

        def slow_preflight(**kwargs):
            started.set()
            finish.wait(3)
            return dict(report)

        with TestClient(app.app) as client, patch.object(app.engine, 'run_preflight', side_effect=slow_preflight):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(client.post, '/api/check',
                                         files={'file': ('test.pdf', base.sample_pdf(False))})
                try:
                    self.assertTrue(started.wait(2))
                    self.assertEqual(client.get('/api/profiles').status_code, 200)
                    self.assertFalse(future.done(), 'Profile read must finish while PDF processing is still running')
                finally:
                    finish.set()
                self.assertEqual(future.result().status_code, 200)


class RequestBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, chunks, headers=(), handler=None):
        messages = []
        entered = []

        async def downstream(scope, receive, send):
            entered.append(True)
            if handler:
                return await handler(scope, receive, send)
            while (await receive()).get('more_body', False):
                pass
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'OK'})

        async def receive():
            return chunks.pop(0) if chunks else {'type': 'http.disconnect'}

        middleware = limits.RequestLimitsMiddleware(downstream)
        scope = {'type': 'http', 'method': 'POST', 'path': '/api/profiles/import', 'headers': headers}
        await middleware(scope, receive, self.sender(messages))
        return messages[0]['status'], entered

    @staticmethod
    def sender(messages):
        async def send(message):
            messages.append(message)
        return send

    async def test_declared_and_chunked_oversized_bodies_never_reach_the_app(self):
        status, entered = await self.invoke([], [(b'content-length', b'2000000')])
        self.assertEqual((status, entered), (413, []))
        for headers in ([], [(b'content-length', b'4')]):
            chunks = [{'type': 'http.request', 'body': b'x' * 600000, 'more_body': True},
                      {'type': 'http.request', 'body': b'x' * 600000, 'more_body': False}]
            status, entered = await self.invoke(chunks, headers)
            self.assertEqual((status, entered), (413, []))

    async def test_bounded_body_is_replayed_intact(self):
        received = bytearray()

        async def handler(scope, receive, send):
            while True:
                message = await receive(); received.extend(message.get('body', b''))
                if not message.get('more_body', False):
                    break
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'OK'})

        status, _ = await self.invoke([{'type': 'http.request', 'body': b'a' * 150000}], handler=handler)
        self.assertEqual(status, 200)
        self.assertEqual(received, b'a' * 150000)

    async def test_full_queue_returns_429_before_processing(self):
        async def unused(*args):
            self.fail('Overloaded request must not reach the application')

        middleware = limits.RequestLimitsMiddleware(unused)
        for _ in range(5):
            self.assertTrue(middleware.admitted.acquire(blocking=False))
        messages = []
        await middleware({'type': 'http', 'method': 'GET', 'path': '/api/imposition/preview/test'},
                         unused, self.sender(messages))
        self.assertEqual(messages[0]['status'], 429)
        for _ in range(5):
            middleware.admitted.release()

    async def test_concurrent_pdf_requests_run_serially_with_a_bounded_queue(self):
        active = peak = 0

        async def handler(scope, receive, send):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'OK'})

        middleware = limits.RequestLimitsMiddleware(handler)

        async def request():
            messages = []
            await middleware({'type': 'http', 'method': 'GET', 'path': '/api/inspect-pdf'},
                             None, self.sender(messages))
            return messages[0]['status']

        statuses = await asyncio.gather(*(request() for _ in range(9)))
        self.assertEqual(peak, 1)
        self.assertIn(429, statuses)
        self.assertTrue(all(s in (200, 429) for s in statuses))
        self.assertTrue(middleware.active.acquire(blocking=False))
        middleware.active.release()
        for _ in range(5):
            self.assertTrue(middleware.admitted.acquire(blocking=False))
        for _ in range(5):
            middleware.admitted.release()


if __name__ == '__main__':
    unittest.main()
