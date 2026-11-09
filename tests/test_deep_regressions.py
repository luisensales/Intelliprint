"""Document-level regressions from the November 2026 audit."""

import io
import json
import unittest
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pikepdf
import pymupdf
import qrcode

import app
import hotfolder_engine as hotfolder
import icc_manager
import profile_manager
from barcode_engine import fix_barcodes_in_pdf, inspect_barcodes_in_pdf
from font_vectorizer import outline_fonts_in_pdf
from imposition_engine import generate_imposed_pdf
from mirror_bleed_generator import generate_mirror_bleed
from preflight_engine import extract_pdf_spot_colors
from printer_marks_generator import add_printer_marks_to_pdf
from tac_limiter import limit_pdf_tac, measure_pdf_tac
from traceability_engine import get_press_operator_data, render_press_operator_html
import test_regressions as base


def raw_pdf(path, content=b"", image=None, inverted=False, font=False, spot=False):
    with pikepdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(200, 200))
        page.TrimBox = [10, 10, 190, 190]
        page.BleedBox = [0, 0, 200, 200]
        resources = pikepdf.Dictionary(ExtGState=pikepdf.Dictionary(GS=pikepdf.Dictionary(op=True, OP=True, OPM=1)))
        if font:
            resources.Font = pikepdf.Dictionary(F1=pdf.make_indirect(pikepdf.Dictionary(
                Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)))
        if spot:
            tint = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=[0, 1, 0, 0], N=1)
            resources.ColorSpace = pikepdf.Dictionary(S1=pikepdf.Array([
                pikepdf.Name.Separation, pikepdf.Name('/Barniz'), pikepdf.Name.DeviceCMYK, tint]))
        if image is not None:
            stream = pdf.make_stream(bytes(image))
            stream.Type = pikepdf.Name.XObject
            stream.Subtype = pikepdf.Name.Image
            stream.Width, stream.Height, stream.BitsPerComponent = 2, 1, 8
            stream.ColorSpace = pikepdf.Name.DeviceCMYK
            if inverted:
                stream.Decode = [1, 0] * 4
            resources.XObject = pikepdf.Dictionary(Im=stream)
        page.Resources = resources
        page.Contents = pdf.make_stream(content)
        pdf.save(path)


def native_pixels(path):
    with pymupdf.open(path) as doc:
        return list(pymupdf.Pixmap(doc, doc[0].get_images()[0][0]).samples)


class DeepRegressionTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp
    upload = base.RegressionTests.upload

    def test_icc_rejects_paths_and_non_profiles_without_creating_jobs(self):
        private = self.root / 'private.txt'
        private.write_bytes(b'NOT AN ICC PROFILE ' * 20)
        for selection in (str(private), '../private.txt', '..\\private.txt', 'CAT_ECICMYK_V2'):
            with self.subTest(selection=selection):
                response = self.client.post('/api/check', files={'file': ('input.pdf', self._plain_pdf(), 'application/pdf')},
                                            data={'icc_option': 'custom_selection', 'selected_icc': selection})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(list(self.uploads.iterdir()), [])
        self.assertEqual(list(self.jobs.iterdir()), [])
        fake = self.root / 'fake.icc'
        fake.write_bytes(private.read_bytes())
        with patch.object(icc_manager, 'ICC_DIR', self.root), self.assertRaises(ValueError):
            icc_manager.apply_icc_to_pdf(self.root / 'unused.pdf', 'fake.icc')

    def _plain_pdf(self):
        with pymupdf.open() as doc:
            doc.new_page(width=200, height=200)
            return doc.tobytes()

    def test_catalog_id_uses_the_actual_corresponding_icc(self):
        source = self.root / 'source.pdf'
        source.write_bytes(self._plain_pdf())
        icc_manager.apply_icc_to_pdf(source, 'CAT_PSO_COATED_V3')
        with pikepdf.open(source) as pdf:
            actual = pdf.Root.OutputIntents[0].DestOutputProfile.read_bytes()
        self.assertEqual(actual, (icc_manager.ICC_DIR / 'PSOcoated_v3.icc').read_bytes())

    def test_barcode_correction_keeps_a_readable_identical_payload(self):
        source, output = self.root / 'qr.pdf', self.root / 'qr_fixed.pdf'
        payload = 'https://example.invalid/intelliprint-regression'
        image = io.BytesIO()
        qrcode.make(payload).convert('RGB').save(image, format='PNG')
        with pymupdf.open() as doc:
            page = doc.new_page(width=400, height=400)
            page.insert_image(pymupdf.Rect(50, 50, 350, 350), stream=image.getvalue())
            doc.save(source)
        self.assertEqual(inspect_barcodes_in_pdf(source)['total_barcodes_found'], 1)
        result = fix_barcodes_in_pdf(source, output)
        self.assertEqual(result['codes_fixed'], 1)
        verified = inspect_barcodes_in_pdf(output)
        self.assertEqual({f['payload'] for f in verified['findings']}, {payload})
        with pymupdf.open(output) as doc:
            self.assertLess(min(doc[0].get_pixmap(colorspace=pymupdf.csGRAY).samples), 255)

    def test_tac_normalizes_decode_and_preserves_white(self):
        source, output = self.root / 'inverted.pdf', self.root / 'limited.pdf'
        raw_pdf(source, b'q 100 0 0 50 50 50 cm /Im Do Q', image=[0] * 4 + [255] * 4, inverted=True)
        result = limit_pdf_tac(source, output)
        self.assertTrue(result['success'])
        pixels = native_pixels(output)
        self.assertLessEqual(sum(pixels[:4]) * 100 / 255, 300)
        self.assertEqual(pixels[4:], [0] * 4)
        self.assertTrue(limit_pdf_tac(output, output)['success'])

    def test_font_outlining_preserves_plates_overprint_boxes_and_rotation(self):
        source, output = self.root / 'font.pdf', self.root / 'outlined.pdf'
        raw_pdf(source, b'0 1 0 0 k 20 20 40 40 re f /GS gs BT /F1 12 Tf 30 90 Td 0 0 0 1 k (Test) Tj ET /S1 cs 1 scn 100 20 40 40 re f', font=True, spot=True)
        with pikepdf.open(source, allow_overwriting_input=True) as pdf:
            pdf.pages[0].Rotate = 90
            pdf.save(source)
        icc_manager.apply_icc_to_pdf(source, 'ISOcoated_v2_eci.icc')
        result = outline_fonts_in_pdf(source, output)
        self.assertEqual(result['pages_vectorized'], 1)
        with pikepdf.open(source) as before, pikepdf.open(output) as after:
            self.assertEqual([s['name'] for s in extract_pdf_spot_colors(after)], ['Barniz'])
            operations = Counter(str(op) for _, op in pikepdf.parse_content_stream(after.pages[0]))
            self.assertGreater(operations['gs'], 0)
            self.assertEqual(operations['rg'], 0)
            for key in ('/MediaBox', '/TrimBox', '/BleedBox', '/Rotate'):
                self.assertEqual(before.pages[0][key], after.pages[0][key])
            self.assertEqual(before.Root.OutputIntents[0].DestOutputProfile.read_bytes(),
                             after.Root.OutputIntents[0].DestOutputProfile.read_bytes())
        with pymupdf.open(output) as doc:
            self.assertEqual(doc[0].get_fonts(), [])
            self.assertEqual(doc[0].rotation, 90)

    def test_all_rebuilding_operations_preserve_direct_output_intents(self):
        source = self.root / 'source.pdf'
        raw_pdf(source, b'BT /F1 12 Tf 20 30 Td (Test) Tj ET', font=True)
        icc_manager.apply_icc_to_pdf(source, 'ISOcoated_v2_eci.icc')
        with pikepdf.open(source, allow_overwriting_input=True) as pdf:
            intent = pdf.Root.OutputIntents[0]
            expected = intent.DestOutputProfile.read_bytes()
            pdf.Root.OutputIntents = pikepdf.Array([pikepdf.Dictionary({k: v for k, v in intent.items()})])
            pdf.save(source)
        for name, operation in (('mirror', generate_mirror_bleed), ('marks', add_printer_marks_to_pdf),
                                ('fonts', outline_fonts_in_pdf), ('imposition', generate_imposed_pdf)):
            with self.subTest(operation=name):
                output = self.root / f'{name}.pdf'
                operation(source, output)
                with pikepdf.open(output) as pdf:
                    self.assertEqual(pdf.Root.OutputIntents[0].DestOutputProfile.read_bytes(), expected)

    def test_verify_html_escapes_pdf_filename(self):
        name = '<img src=x onerror=alert(1)>.pdf'
        response = self.client.post('/api/check', files={'file': (name, self._plain_pdf(), 'application/pdf')})
        verify = self.client.get('/verify/' + response.json()['job_meta']['job_id'])
        self.assertEqual(verify.status_code, 200)
        self.assertNotIn('<img src=x', verify.text)
        self.assertIn('&lt;img', verify.text)

    def test_mass_batch_saves_a_new_verdict_and_certificate(self):
        report = self.upload()
        job_id = report['job_meta']['job_id']
        result = self.client.post('/api/batch/fix-all', json={'job_ids': [job_id]}).json()['results'][0]
        self.assertEqual(result['status'], 'success', result)
        saved = json.loads((self.jobs / f'{job_id}.json').read_text(encoding='utf-8'))
        actual = app.engine.run_preflight(saved['job_meta']['last_fixed_pdf_path'])
        self.assertEqual(saved['findings'], actual['findings'])
        self.assertEqual(result['errors_count'], actual['triple_result']['technical']['errors_count'])
        self.assertTrue((self.jobs / f'{job_id}_ficha_tecnica.pdf').is_file())

    def test_mass_batch_reports_each_failure_without_aborting_the_list(self):
        job_id = self.upload()['job_meta']['job_id']
        with patch.object(hotfolder, 'apply_full_batch_fix', side_effect=ValueError('failed')):
            result = hotfolder.batch_fix_jobs([job_id, 'missing'])
        self.assertEqual([r['status'] for r in result], ['error', 'error'])

    def test_full_batch_uses_the_tac_result_and_profile_limit(self):
        source, output = self.root / 'source.pdf', self.root / 'output.pdf'
        raw_pdf(source, b'q 100 0 0 100 50 50 cm /Im Do Q', image=[255] * 8)
        result = hotfolder.apply_full_batch_fix(source, output, profile_id='PERIODICO_TAC240')
        self.assertIn('tac', [step['action'] for step in result['steps']])
        self.assertLessEqual(measure_pdf_tac(output)['peak_percent'], 240)

    def test_profile_font_hairline_tac_and_spot_settings_are_enforced(self):
        source = self.root / 'criteria.pdf'
        raw_pdf(source, b'1 1 1 1 k 20 20 100 100 re f 0 0 0 1 K 0.3 w 20 150 m 150 150 l S BT /F1 12 Tf 20 170 Td (Test) Tj ET /S1 cs 1 scn 150 20 20 20 re f', font=True, spot=True)
        icc_manager.apply_icc_to_pdf(source, 'ISOcoated_v2_eci.icc')
        profile = profile_manager.create_custom_profile({'name': 'Strict', 'max_tac': 240, 'min_hairline_pt': 0.5,
                                                        'require_fonts_embedded': False, 'allow_spot_colors': False})
        report = app.engine.run_preflight(source, profile_id=profile['id'])
        rules = {f['rule_id'] for f in report['findings']}
        self.assertIn('MAX_INK_COVERAGE', rules)
        self.assertIn('HAIRLINE_DETECTED', rules)
        self.assertIn('SPOT_COLOR_NOT_ALLOWED', rules)
        self.assertNotIn('USED_FONTS_EMBEDDED', rules)

    def test_hotfolder_persists_downloadable_final_paths(self):
        with ExitStack() as stack:
            for name in ('IN_DIR', 'PROCESSING_DIR', 'APPROVED_DIR', 'REJECTED_DIR'):
                path = self.root / name
                path.mkdir()
                stack.enter_context(patch.object(hotfolder, name, path))
            stack.enter_context(patch.object(hotfolder, 'LOGS_FILE', self.root / 'events.json'))
            service = hotfolder.HotFolderService()
            service.auto_fix = service.generate_reports = False
            source = hotfolder.IN_DIR / 'source.pdf'
            source.write_bytes(self._plain_pdf())
            event = service.process_file_sync(source)
            saved = json.loads((self.jobs / f"{event['job_id']}.json").read_text(encoding='utf-8'))
            self.assertTrue(Path(saved['job_meta']['pdf_path']).is_file())
            self.assertEqual(self.client.get('/api/download-pdf/' + event['job_id']).status_code, 200)

    def test_repeating_cmyk_and_tac_is_successful(self):
        for action in ('convert-to-cmyk', 'limit-tac'):
            with self.subTest(action=action):
                job_id = self.upload(with_image=False)['job_meta']['job_id']
                for _ in range(2):
                    response = self.client.post(f'/api/{action}/{job_id}')
                    self.assertEqual(response.status_code, 200, response.text)

    def test_invalid_pdf_is_rejected_and_not_persisted(self):
        response = self.client.post('/api/check', files={'file': ('invalid.pdf', b'not a pdf', 'application/pdf')})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(list(self.uploads.iterdir()), [])
        response = self.client.post('/api/batch/upload', files={'files': ('invalid.pdf', b'not a pdf', 'application/pdf')})
        self.assertEqual(response.json()['jobs'][0]['status'], 'ERROR')
        self.assertEqual(list(self.jobs.iterdir()), [])
        self.assertEqual(list(self.uploads.iterdir()), [])

    def test_traceability_uses_canonical_verdict_authorization_and_measurement(self):
        report = {'triple_result': {'technical': {'status': 'PASS'}, 'release': {'status': 'AUTHORIZED'}}}
        data = get_press_operator_data(report)
        self.assertTrue(data['is_ready_for_press'])
        self.assertIsNone(data['max_tac_percent'])
        self.assertEqual(data['tac_status'], 'NOT_MEASURED')
        self.assertIn('No medido', render_press_operator_html(data))
        report['job_summary'] = {'max_tac_limit': 240, 'tac_measurement': {'measured': True, 'peak_percent': 390}}
        data = get_press_operator_data(report)
        self.assertEqual(data['max_tac_percent'], 390)
        self.assertEqual(data['tac_status'], 'WARNING')
        report['triple_result']['release']['status'] = 'PENDING_AUTHORIZATION'
        self.assertFalse(get_press_operator_data(report)['is_ready_for_press'])

    def test_invalid_profile_import_is_atomic_and_does_not_poison_later_imports(self):
        invalid = self.client.post('/api/profiles/import', json={'custom_profiles': [{'name': 'Missing ID'}]})
        self.assertEqual(invalid.status_code, 422)
        valid = {'id': 'CUSTOM_valid', 'name': 'Valid'}
        response = self.client.post('/api/profiles/import', json={'custom_profiles': [valid]})
        self.assertEqual(response.status_code, 200, response.text)
        before = profile_manager.CUSTOM_PROFILES_FILE.read_bytes()
        duplicate = self.client.post('/api/profiles/import', json={'custom_profiles': [valid, valid]})
        self.assertEqual(duplicate.status_code, 422)
        self.assertEqual(profile_manager.CUSTOM_PROFILES_FILE.read_bytes(), before)

    def test_legacy_invalid_records_do_not_break_valid_profiles(self):
        profile_manager.CUSTOM_PROFILES_FILE.write_text(json.dumps({'custom_profiles': [
            {'name': 'Missing ID'}, {'id': 'CUSTOM_valid', 'name': 'Valid'},
        ]}), encoding='utf-8')
        self.assertEqual([p['id'] for p in profile_manager.load_custom_profiles()], ['CUSTOM_valid'])
        self.assertEqual(self.client.post('/api/profiles/import', json={'custom_profiles': []}).status_code, 200)

    def test_unavailable_outline_engine_never_overwrites_the_input(self):
        source = self.root / 'font.pdf'
        raw_pdf(source, b'BT /F1 12 Tf 20 30 Td (Test) Tj ET', font=True)
        original = source.read_bytes()
        with patch('font_vectorizer.find_ghostscript', side_effect=RuntimeError('Unavailable')):
            with self.assertRaises(RuntimeError):
                outline_fonts_in_pdf(source, source)
        self.assertEqual(source.read_bytes(), original)

    def test_unused_legacy_spot_catalog_is_preserved_without_inventing_plate_use(self):
        from pdf_utils import used_spot_names
        source, output = self.root / 'legacy.pdf', self.root / 'outlined.pdf'
        raw_pdf(source, b'BT /F1 12 Tf 20 30 Td (Test) Tj ET', font=True)
        with pikepdf.open(source, allow_overwriting_input=True) as pdf:
            pdf.pages[0].Resources.ColorSpace = pikepdf.Dictionary(
                Unused=pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name('/Legacy'), pikepdf.Name.DeviceCMYK]))
            pdf.save(source)
        outline_fonts_in_pdf(source, output)
        with pikepdf.open(output) as pdf:
            self.assertEqual([s['name'] for s in extract_pdf_spot_colors(pdf)], ['Legacy'])
            self.assertEqual(used_spot_names(pdf), set())


if __name__ == '__main__':
    unittest.main()
