"""Regressions for process isolation, alternate colors and PDF graphics state."""

import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pikepdf
import pymupdf

import hotfolder_engine as hotfolder
import profile_manager
from pdf_utils import used_spot_names
from pdf_workers import run_pdf_task, shutdown_pdf_workers
from preflight_engine import IntelliPrintEngine
from security_limits import PDF_PROCESSING_SLOT
from spot_converter import convert_spot_colors_to_cmyk, extract_spot_cmyk_equivalent
import test_regressions as base


def spot(pdf, name='CommercialRed', family='/DeviceRGB', c0=(1, 1, 1), c1=(1, 0, 0), exponent=1):
    function = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=list(c0), C1=list(c1), N=exponent)
    return pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name('/' + name),
                          pikepdf.Name(family), function])


def fill_cmyk(path, x=30, y=150):
    with pymupdf.open(path) as doc:
        pix = doc[0].get_pixmap(colorspace=pymupdf.csCMYK, dpi=72)
        offset = (y * pix.width + x) * 4
        return tuple(pix.samples[offset:offset + 4])


class SpotConversionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source, self.output = self.root / 'source.pdf', self.root / 'output.pdf'

    def document(self, content, extra=None):
        with pikepdf.new() as pdf:
            page = pdf.add_blank_page(page_size=(200, 200))
            page.Resources = pikepdf.Dictionary(ColorSpace=pikepdf.Dictionary(S=spot(pdf)))
            page.Contents = pdf.make_stream(content)
            if extra:
                extra(pdf, page)
            pdf.save(self.source)

    def convert(self):
        result = convert_spot_colors_to_cmyk(self.source, self.output)
        self.assertTrue(result['success'], result)
        return result

    def test_rgb_red_and_blue_are_not_misidentified_as_lab(self):
        with pikepdf.new() as pdf:
            self.assertEqual(extract_spot_cmyk_equivalent(spot(pdf))[1], (0, 1, 1, 0))
            blue = spot(pdf, name='CommercialBlue', c1=(0, 0, 1))
            self.assertEqual(extract_spot_cmyk_equivalent(blue)[1], (1, 1, 0, 0))
            malformed = spot(pdf, c1=(1, 0, 0, 0))
            with self.assertRaises(ValueError):
                extract_spot_cmyk_equivalent(malformed)
        self.document(b'/S cs 1 scn 20 20 50 50 re f')
        self.convert()
        self.assertEqual(fill_cmyk(self.output), (0, 255, 255, 0))

    def test_tints_evaluate_c0_and_exponent_before_color_conversion(self):
        def resources(pdf, page):
            page.Resources.ColorSpace.S = spot(pdf, family='/DeviceCMYK',
                c0=(.1, .2, 0, 0), c1=(.9, .6, .2, .1), exponent=2)
        self.document(b'/S cs .5 scn 20 20 50 50 re f', resources)
        self.convert()
        actual = fill_cmyk(self.output)
        expected = (77, 77, 13, 6)
        self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(actual, expected)), actual)

    def test_q_Q_restore_a_spot_after_switching_to_gray(self):
        self.document(b'/S cs 1 scn q 0 g q 1 0 0 rg Q Q .5 scn 20 20 50 50 re f')
        result = self.convert()
        self.assertEqual(result['pages_modified'], 1)
        with pikepdf.open(self.output) as pdf:
            operations = list(pikepdf.parse_content_stream(pdf.pages[0]))
            self.assertFalse(any(str(op) in ('sc', 'scn') for _, op in operations))
            self.assertEqual(used_spot_names(pdf), set())
        self.assertEqual(fill_cmyk(self.output), (0, 127, 127, 0))

    def test_stroke_and_fill_keep_independent_stacks(self):
        def resources(pdf, page):
            page.Resources.ColorSpace.B = spot(pdf, name='CommercialBlue', c1=(0, 0, 1))
        self.document(b'/S cs 1 scn /B CS 1 SCN q 0 g 0 G Q .25 scn .75 SCN '
                      b'2 w 20 20 50 50 re B', resources)
        self.convert()
        with pikepdf.open(self.output) as pdf:
            commands = list(pikepdf.parse_content_stream(pdf.pages[0]))
            fills = [list(map(float, args)) for args, op in commands if str(op) == 'k']
            strokes = [list(map(float, args)) for args, op in commands if str(op) == 'K']
        self.assertEqual(fills[-1], [0, .25, .25, 0])
        self.assertEqual(strokes[-1], [.75, .75, 0, 0])

    def test_selecting_a_spot_also_preserves_its_initial_full_tint(self):
        self.document(b'/S cs 20 20 50 50 re f')
        self.convert()
        self.assertEqual(fill_cmyk(self.output), (0, 255, 255, 0))

    def test_shared_page_resources_are_not_mutated_before_other_pages_convert(self):
        with pikepdf.new() as pdf:
            resources = pikepdf.Dictionary(ColorSpace=pikepdf.Dictionary(S=spot(pdf)))
            for _ in range(2):
                page = pdf.add_blank_page(page_size=(200, 200))
                page.Resources = resources
                page.Contents = pdf.make_stream(b'/S cs .5 scn 20 20 50 50 re f')
            pdf.save(self.source)
        self.assertEqual(self.convert()['pages_modified'], 2)
        with pikepdf.open(self.output) as pdf:
            for page in pdf.pages:
                self.assertFalse(any(str(op) == 'scn' for _, op in pikepdf.parse_content_stream(page)))

    def test_form_uses_its_own_color_resources_even_when_names_collide(self):
        def resources(pdf, page):
            form = pdf.make_stream(b'/S cs 1 scn 20 20 50 50 re f')
            form.Type, form.Subtype, form.BBox = pikepdf.Name.XObject, pikepdf.Name.Form, [0, 0, 200, 200]
            form.Resources = pikepdf.Dictionary(ColorSpace=pikepdf.Dictionary(
                S=spot(pdf, name='CommercialBlue', c1=(0, 0, 1))))
            page.Resources.XObject = pikepdf.Dictionary(F=form)
        self.document(b'/F Do /S cs 1 scn 100 20 50 50 re f', resources)
        self.convert()
        self.assertEqual(fill_cmyk(self.output), (255, 255, 0, 0))
        self.assertEqual(fill_cmyk(self.output, 110), (0, 255, 255, 0))

    def test_shared_form_is_converted_for_each_inherited_color_state(self):
        def resources(pdf, page):
            page.Resources.ColorSpace.B = spot(pdf, name='CommercialBlue', c1=(0, 0, 1))
            form = pdf.make_stream(b'.5 scn 20 20 50 50 re f')
            form.Type, form.Subtype, form.BBox = pikepdf.Name.XObject, pikepdf.Name.Form, [0, 0, 200, 200]
            page.Resources.XObject = pikepdf.Dictionary(F=form)
        self.document(b'/S cs 1 scn q /F Do Q /B cs 1 scn q 1 0 0 1 80 0 cm /F Do Q', resources)
        self.convert()
        self.assertEqual(fill_cmyk(self.output), (0, 127, 127, 0))
        self.assertEqual(fill_cmyk(self.output, 110), (127, 127, 0, 0))

    def test_corrected_form_does_not_replace_an_uncorrected_invocation(self):
        def resources(pdf, page):
            form = pdf.make_stream(b'.5 scn 20 20 50 50 re f')
            form.Type, form.Subtype, form.BBox = pikepdf.Name.XObject, pikepdf.Name.Form, [0, 0, 200, 200]
            page.Resources.XObject = pikepdf.Dictionary(F=form)
        self.document(b'/S cs 1 scn q /F Do Q 0 g q 1 0 0 1 80 0 cm /F Do Q', resources)
        original_gray = fill_cmyk(self.source, 110)
        self.convert()
        self.assertEqual(fill_cmyk(self.output), (0, 127, 127, 0))
        self.assertEqual(fill_cmyk(self.output, 110), original_gray)

    def test_nested_forms_and_technical_inks_remain_valid(self):
        def resources(pdf, page):
            leaf = pdf.make_stream(b'/S cs 1 scn 20 20 50 50 re f')
            leaf.Type, leaf.Subtype, leaf.BBox = pikepdf.Name.XObject, pikepdf.Name.Form, [0, 0, 200, 200]
            leaf.Resources = pikepdf.Dictionary(ColorSpace=pikepdf.Dictionary(S=spot(pdf)))
            outer = pdf.make_stream(b'/Leaf Do')
            outer.Type, outer.Subtype, outer.BBox = pikepdf.Name.XObject, pikepdf.Name.Form, [0, 0, 200, 200]
            outer.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Leaf=leaf))
            page.Resources.XObject = pikepdf.Dictionary(Outer=outer)
            page.Resources.ColorSpace.V = spot(pdf, name='Barniz')
        self.document(b'/Outer Do /V cs 1 scn 100 20 50 50 re f', resources)
        result = self.convert()
        self.assertEqual([s['name'] for s in result['spots_converted']], ['CommercialRed'])
        with pikepdf.open(self.output) as pdf:
            self.assertEqual(used_spot_names(pdf), {'Barniz'})
        self.assertEqual(fill_cmyk(self.output), (0, 255, 255, 0))

    def test_unsupported_device_n_does_not_replace_an_existing_output(self):
        def resources(pdf, page):
            page.Resources.ColorSpace.S = pikepdf.Array([pikepdf.Name.DeviceN,
                pikepdf.Array([pikepdf.Name('/CommercialA'), pikepdf.Name('/CommercialB')]),
                pikepdf.Name.DeviceCMYK, pikepdf.Dictionary(FunctionType=2,
                    Domain=[0, 1, 0, 1], C0=[0, 0, 0, 0], C1=[1, 1, 0, 0], N=1)])
        self.document(b'/S cs .5 .5 scn 20 20 50 50 re f', resources)
        original = self.source.read_bytes()
        self.output.write_bytes(b'previous output')
        result = convert_spot_colors_to_cmyk(self.source, self.output)
        self.assertFalse(result['success'])
        self.assertIn('DeviceN', result['errors'][0])
        self.assertEqual(self.output.read_bytes(), b'previous output')
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(result['spots_converted'], [])

    def test_invalid_graphics_stack_is_rejected_atomically(self):
        self.document(b'/S cs 1 scn Q .5 scn 20 20 50 50 re f')
        result = convert_spot_colors_to_cmyk(self.source, self.output)
        self.assertFalse(result['success'])
        self.assertFalse(self.output.exists())

    def test_conversion_can_be_repeated_in_place(self):
        self.document(b'/S cs 1 scn 20 20 50 50 re f')
        for _ in range(2):
            result = convert_spot_colors_to_cmyk(self.source, self.source)
            self.assertTrue(result['success'], result)
        self.assertEqual(fill_cmyk(self.source), (0, 255, 255, 0))

    def test_image_using_the_original_spot_definition_is_not_rebound_to_cmyk(self):
        def resources(pdf, page):
            image = pdf.make_stream(bytes([255] * 4))
            image.Type, image.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
            image.Width = image.Height = 2
            image.BitsPerComponent = 8
            image.ColorSpace = page.Resources.ColorSpace.S
            page.Resources.XObject = pikepdf.Dictionary(Im=image)
        self.document(b'/S cs 1 scn 20 20 50 50 re f '
                      b'q 50 0 0 50 100 20 cm /Im Do Q', resources)
        original_image_color = fill_cmyk(self.source, 110)
        self.convert()
        with pikepdf.open(self.output) as pdf:
            self.assertEqual(str(pdf.pages[0].Resources.XObject.Im.ColorSpace[0]), '/Separation')
            self.assertEqual(pdf.pages[0].Resources.XObject.Im.read_bytes(), bytes([255] * 4))
        self.assertEqual(fill_cmyk(self.output, 110), original_image_color)


class SpotApiTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp

    def upload_spot(self, sampled=False):
        with pikepdf.new() as pdf:
            page = pdf.add_blank_page(page_size=(200, 200))
            definition = spot(pdf)
            if sampled:
                function = pdf.make_stream(bytes([255, 255, 255, 255, 0, 0]))
                function.FunctionType = 0
                function.Domain, function.Range = [0, 1], [0, 1] * 3
                function.Size, function.BitsPerSample = [2], 8
                definition[3] = function
            page.Resources = pikepdf.Dictionary(ColorSpace=pikepdf.Dictionary(S=definition))
            page.Contents = pdf.make_stream(b'/S cs 1 scn q 0 g Q .5 scn 20 20 50 50 re f')
            source = self.root / 'spot.pdf'
            pdf.save(source)
        response = self.client.post('/api/check', files={'file': ('spot.pdf', source.read_bytes())})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['job_meta']['job_id']

    def test_api_rechecks_and_downloads_the_converted_pdf(self):
        job_id = self.upload_spot()
        response = self.client.post('/api/convert-spots-to-cmyk/' + job_id)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['spots_converted'][0]['cmyk_base'], [0, 1, 1, 0])
        self.assertEqual(data['remaining_spots'], [])
        output = Path(data['report']['job_meta']['last_fixed_pdf_path'])
        self.assertEqual(fill_cmyk(output), (0, 127, 127, 0))
        self.assertEqual(self.client.get(data['download_url']).content, output.read_bytes())

    def test_failed_conversion_keeps_the_persisted_report_and_previous_output(self):
        job_id = self.upload_spot(sampled=True)
        job_file = self.jobs / (job_id + '.json')
        previous_report = job_file.read_bytes()
        output = self.jobs / (job_id + '_spots_converted.pdf')
        output.write_bytes(b'previous output')
        response = self.client.post('/api/convert-spots-to-cmyk/' + job_id)
        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(job_file.read_bytes(), previous_report)
        self.assertEqual(output.read_bytes(), b'previous output')


def worker_identity():
    return os.getpid(), threading.current_thread().name


def exit_worker(parent_pid):
    if os.getpid() == parent_pid:
        raise AssertionError('Never terminate the caller process')
    os._exit(17)


class PdfWorkerTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp

    @classmethod
    def tearDownClass(cls):
        shutdown_pdf_workers()

    def test_worker_has_a_separate_pid_and_executes_on_its_main_thread(self):
        pid, thread_name = run_pdf_task(worker_identity)
        self.assertNotEqual(pid, os.getpid())
        self.assertEqual(thread_name, 'MainThread')

    def test_background_worker_waits_for_the_http_pdf_resource_slot(self):
        run_pdf_task(worker_identity)  # Warm up the process before checking the resource gate.
        started = threading.Event()

        def background():
            started.set()
            return run_pdf_task(worker_identity)

        with ThreadPoolExecutor(max_workers=1) as executor:
            PDF_PROCESSING_SLOT.acquire()
            try:
                result = executor.submit(background)
                self.assertTrue(started.wait(2))
                with self.assertRaises(TimeoutError):
                    result.result(timeout=.05)
            finally:
                PDF_PROCESSING_SLOT.release()
            self.assertNotEqual(result.result(timeout=10)[0], os.getpid())

    def test_batch_preserves_order_errors_and_custom_profiles_across_processes(self):
        profile = profile_manager.create_custom_profile({'name': 'Worker profile', 'max_tac': 240})
        with patch.object(IntelliPrintEngine, 'run_preflight', side_effect=AssertionError('Parent PDF call')):
            results = hotfolder.process_batch_upload([
                ('first.pdf', base.sample_pdf(False)), ('invalid.pdf', b'not a PDF'),
                ('third.pdf', base.sample_pdf(False))], profile_id=profile['id'])
        self.assertEqual([r['filename'] for r in results], ['first.pdf', 'invalid.pdf', 'third.pdf'])
        self.assertEqual(results[1]['status'], 'ERROR')
        self.assertNotEqual(results[0]['status'], 'ERROR')
        self.assertNotEqual(results[2]['status'], 'ERROR')
        saved = json.loads((self.jobs / (results[0]['job_id'] + '.json')).read_text(encoding='utf-8'))
        self.assertEqual(saved['job_summary']['max_tac_limit'], 240)
        self.assertEqual(len(list(self.jobs.glob('*.json'))), 2)

    def hotfolder_directories(self, stack):
        for name in ('IN_DIR', 'PROCESSING_DIR', 'APPROVED_DIR', 'REJECTED_DIR'):
            directory = self.root / name
            directory.mkdir()
            stack.enter_context(patch.object(hotfolder, name, directory))
        stack.enter_context(patch.object(hotfolder, 'LOGS_FILE', self.root / 'events.json'))

    def test_hotfolder_pipeline_and_reports_run_outside_parent_threads(self):
        with ExitStack() as stack:
            self.hotfolder_directories(stack)
            service = hotfolder.HotFolderService()
            service.auto_fix = False
            source = hotfolder.IN_DIR / 'test.pdf'
            source.write_bytes(base.sample_pdf(False))
            stack.enter_context(patch.object(IntelliPrintEngine, 'run_preflight',
                                            side_effect=AssertionError('Parent PDF call')))
            event = service.process_file_sync(source)
            self.assertNotEqual(event['status'], 'ERROR', event)
            self.assertEqual(service.get_status()['recent_events'][0]['job_id'], event['job_id'])
            self.assertEqual(len(list(hotfolder.PROCESSING_DIR.iterdir())), 0)
            self.assertTrue(list(hotfolder.REJECTED_DIR.glob('*Certificado_Preflight.pdf')))

    def test_hotfolder_records_failure_and_quarantines_unfinished_input(self):
        with ExitStack() as stack:
            self.hotfolder_directories(stack)
            source = hotfolder.IN_DIR / 'test.pdf'
            source.write_bytes(base.sample_pdf(False))
            stack.enter_context(patch.object(hotfolder, 'run_pdf_task', side_effect=RuntimeError('worker lost')))
            service = hotfolder.HotFolderService()
            event = service.process_file_sync(source)
            self.assertEqual(event['status'], 'ERROR')
            self.assertFalse(source.exists())
            self.assertTrue(list(hotfolder.REJECTED_DIR.glob('ERROR_*.pdf')))
            self.assertEqual(service.events_log[0]['status'], 'ERROR')

    def test_native_worker_failure_does_not_kill_server_and_next_job_can_run(self):
        with self.assertRaises(RuntimeError):
            run_pdf_task(exit_worker, os.getpid())
        pid, thread_name = run_pdf_task(worker_identity)
        self.assertNotEqual(pid, os.getpid())
        self.assertEqual(thread_name, 'MainThread')


if __name__ == '__main__':
    unittest.main()
