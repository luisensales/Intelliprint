"""Regression coverage for audit items 14–16."""

import hashlib
import json
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import pymupdf

import app
import hotfolder_engine as hotfolder
from traceability_engine import get_press_operator_data, render_press_operator_html
import test_regressions as base


class OperatorEvidenceTests(unittest.TestCase):
    def report(self):
        return {'job_meta': {'job_id': 'test', 'current_sha256': 'a' * 64},
                'job_summary': {}, 'findings': [],
                'triple_result': {'technical': {'status': 'FAIL'}}}

    def test_failed_rules_never_have_green_conformity_badges(self):
        report = self.report()
        report['job_summary'] = {'max_tac_limit': 240, 'min_hairline_threshold': .5,
            'tac_measurement': {'measured': True, 'peak_percent': 350},
            'bleed_detected_mm': 0, 'bleed_status': 'FAIL',
            'rules_evaluated': {'HAIRLINE_DETECTED': 'FAIL'}}
        report['findings'] = [{'rule_id': rule} for rule in
            ('DOCUMENT_OUTPUT_ICC', 'MAX_INK_COVERAGE', 'BLEED_GEOMETRY_3MM', 'HAIRLINE_DETECTED')]
        data = get_press_operator_data(report)
        html = render_press_operator_html(data)
        self.assertNotIn('ICC OK', html)
        self.assertNotIn('TAC OK', html)
        self.assertNotIn('✓', html)
        self.assertIn('ICC no conforme', html)
        self.assertIn('TAC excedido', html)
        self.assertIn('350.0%', html)
        self.assertIn('Límite del perfil: 240%', html)
        self.assertIn('No conforme · 0.0 mm', html)
        self.assertFalse(data['hairlines_ok'])
        self.assertIsNone(data['barcodes_pure_k'])

    def test_missing_evidence_is_unknown_instead_of_conformity(self):
        data = get_press_operator_data(self.report())
        self.assertIsNone(data['bleed_mm'])
        self.assertIsNone(data['hairlines_ok'])
        self.assertIsNone(data['barcodes_pure_k'])
        html = render_press_operator_html(data)
        self.assertIn('No declarado', html)
        self.assertIn('No verificado', html)
        self.assertIn('No medido', html)
        self.assertNotIn('ICC OK', html)
        self.assertNotIn('TAC OK', html)
        self.assertNotIn('Conforme', html)

    def test_passing_rules_and_not_required_bleed_use_measured_profile_criteria(self):
        report = self.report()
        report['job_summary'] = {'icc_detected': {'icc_valid': True, 'detected_family': 'CMYK'},
            'required_color_family': 'CMYK', 'max_tac_limit': 240,
            'tac_measurement': {'measured': True, 'peak_percent': 230},
            'bleed_status': 'NOT_REQUIRED', 'min_hairline_threshold': .5,
            'rules_evaluated': {'HAIRLINE_DETECTED': 'PASS'}}
        data = get_press_operator_data(report)
        html = render_press_operator_html(data)
        self.assertIn('ICC OK', html)
        self.assertIn('TAC OK (estimado)', html)
        self.assertIn('No requerido', html)
        self.assertIn('mín. 0.5 pt', html)
        self.assertEqual(data['barcode_status'], 'NOT_VERIFIED')

    def test_barcode_evidence_must_match_the_current_file(self):
        report = self.report()
        inspection = {'status': 'OK', 'total_barcodes_found': 1}
        report['job_meta']['barcode_inspection'] = {'sha256': 'a'*64, 'report': inspection}
        self.assertTrue(get_press_operator_data(report)['barcodes_pure_k'])
        inspection['status'] = 'WARNING'
        self.assertFalse(get_press_operator_data(report)['barcodes_pure_k'])
        inspection['status'], inspection['total_barcodes_found'] = 'OK', 0
        self.assertEqual(get_press_operator_data(report)['barcode_status'], 'NOT_DETECTED')
        report['job_meta']['current_sha256'] = 'b'*64
        self.assertEqual(get_press_operator_data(report)['barcode_status'], 'NOT_VERIFIED')

    def test_incomplete_graphics_do_not_approve_hairlines(self):
        report = self.report()
        report['job_summary']['rules_evaluated'] = {'HAIRLINE_DETECTED': 'PASS'}
        report['findings'] = [{'rule_id': 'GRAPHICS_NOT_VERIFIED'}]
        self.assertIsNone(get_press_operator_data(report)['hairlines_ok'])

    def test_authorization_applies_only_to_the_signed_digest(self):
        report = self.report()
        report['triple_result'] = {'technical': {'status': 'PASS'}, 'release': {'status': 'AUTHORIZED'}}
        self.assertFalse(get_press_operator_data(report)['is_ready_for_press'])
        report['job_meta']['authorized_sha256'] = 'a'*64
        self.assertTrue(get_press_operator_data(report)['is_ready_for_press'])
        report['job_meta']['current_sha256'] = 'b'*64
        self.assertFalse(get_press_operator_data(report)['is_ready_for_press'])
        report['job_meta'] = {}
        self.assertFalse(get_press_operator_data(report)['is_ready_for_press'])


class DocumentIdentityTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp
    upload = base.RegressionTests.upload

    def saved(self, job_id):
        return json.loads((self.jobs / (job_id + '.json')).read_text(encoding='utf-8'))

    def assert_download_identity(self, report):
        meta = report['job_meta']
        downloaded = self.client.get('/api/download-pdf/' + meta['job_id'])
        self.assertEqual(downloaded.status_code, 200)
        digest = hashlib.sha256(downloaded.content).hexdigest()
        self.assertEqual(meta['sha256'], digest)
        self.assertEqual(meta['current_sha256'], digest)
        self.assertEqual(meta['file_size_mb'], round(len(downloaded.content)/1024**2, 2))
        return digest

    def test_initial_icc_change_preserves_upload_hash_and_updates_download_hash(self):
        original = base.sample_pdf(False)
        response = self.client.post('/api/check', files={'file': ('test.pdf', original, 'application/pdf')},
            data={'icc_option': 'custom_selection', 'selected_icc': 'ISOcoated_v2_eci.icc'})
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertEqual(report['job_meta']['original_sha256'], hashlib.sha256(original).hexdigest())
        self.assertNotEqual(report['job_meta']['original_sha256'], self.assert_download_identity(report))

    def test_correction_updates_identity_certificate_and_removes_old_authorization(self):
        initial = self.upload()
        job_id = initial['job_meta']['job_id']
        released = self.client.post('/api/release', data={'job_id': job_id,
            'operator_name': 'Test', 'decision': 'approved'})
        self.assertEqual(released.status_code, 200, released.text)
        self.assertEqual(released.json()['release_result']['sha256'], initial['job_meta']['current_sha256'])
        self.assertEqual(self.saved(job_id)['job_meta']['authorized_sha256'], initial['job_meta']['current_sha256'])
        corrected = self.client.post('/api/convert-to-cmyk/' + job_id)
        self.assertEqual(corrected.status_code, 200, corrected.text)
        report = corrected.json()['report']
        digest = self.assert_download_identity(report)
        self.assertNotEqual(digest, initial['job_meta']['current_sha256'])
        self.assertEqual(report['job_meta']['original_sha256'], initial['job_meta']['original_sha256'])
        self.assertEqual(report['triple_result']['release']['status'], 'PENDING_AUTHORIZATION')
        self.assertNotIn('authorized_sha256', report['job_meta'])
        self.assertEqual(report['job_meta']['applied_fixes_history'][-1]['sha256'], digest)
        certificate = self.client.get('/api/download-certificate/' + job_id)
        with pymupdf.open(stream=certificate.content) as doc:
            text = ''.join(page.get_text() for page in doc)
        self.assertIn('SHA-256 Original:', text)
        self.assertIn(report['job_meta']['original_sha256'], text)
        self.assertIn('SHA-256 PDF actual:', text)
        self.assertIn(digest, text)
        self.assertIn('SHA-256 Autorizado: No registrado', text)
        html = self.client.get('/verify/' + job_id).text
        self.assertIn(digest, html)
        self.assertIn('SHA-256 original:', html)
        self.assertIn('SHA-256 autorizado: No registrado', html)

    def test_workshop_returns_the_complete_verified_report_with_current_identity(self):
        initial = self.upload()
        job_id = initial['job_meta']['job_id']
        flags = dict(trapping=False, hairlines=False, fonts=False, geometry=False, mirror_bleed=False,
                     cmyk_images=True, spot_colors=False, icc=False, tac=False, printer_marks=False)
        response = self.client.post('/api/batch-fix/' + job_id, params=flags)
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()['report']
        digest = self.assert_download_identity(report)
        self.assertEqual(report, self.saved(job_id))
        self.assertNotEqual(digest, initial['job_meta']['current_sha256'])
        self.assertEqual(response.json()['errors_count'], report['triple_result']['technical']['errors_count'])

    @staticmethod
    def mutate_pdf(source, destination, **options):
        with pymupdf.open(source) as doc:
            doc[0].insert_text((20, 280), 'changed')
            doc.save(destination)
        return {'status': 'success', 'steps_count': 1}

    def test_mass_correction_updates_identity_in_the_saved_report(self):
        initial = self.upload(False)
        job_id = initial['job_meta']['job_id']
        with patch.object(hotfolder, 'apply_full_batch_fix', self.mutate_pdf):
            results = hotfolder.batch_fix_jobs([job_id])
        self.assertEqual(results[0]['status'], 'success', results)
        report = self.saved(job_id)
        self.assert_download_identity(report)
        self.assertEqual(report['job_meta']['original_sha256'], initial['job_meta']['original_sha256'])
        self.assertNotEqual(report['job_meta']['current_sha256'], initial['job_meta']['current_sha256'])

    def test_hotfolder_preserves_original_and_final_hashes(self):
        with ExitStack() as stack:
            for name in ('IN_DIR', 'PROCESSING_DIR', 'APPROVED_DIR', 'REJECTED_DIR'):
                path = self.root / name
                path.mkdir()
                stack.enter_context(patch.object(hotfolder, name, path))
            stack.enter_context(patch.object(hotfolder, 'LOGS_FILE', self.root / 'events.json'))
            stack.enter_context(patch.object(hotfolder, 'apply_full_batch_fix', self.mutate_pdf))
            service = hotfolder.HotFolderService()
            service.auto_fix, service.generate_reports = True, False
            source = hotfolder.IN_DIR / 'test.pdf'
            original = base.sample_pdf(False)
            source.write_bytes(original)
            result = service._process_file_in_worker(source, 'hash_test')
        self.assertIsNotNone(result)
        report = self.saved('hash_test')
        self.assertEqual(report['job_meta']['original_sha256'], hashlib.sha256(original).hexdigest())
        self.assert_download_identity(report)
        self.assertNotEqual(report['job_meta']['original_sha256'], report['job_meta']['current_sha256'])

    def test_barcode_inspection_is_bound_to_the_file_and_expires_after_a_change(self):
        initial = self.upload()
        job_id = initial['job_meta']['job_id']
        with patch.object(app, 'inspect_barcodes_in_pdf', return_value={
                'status': 'OK', 'total_barcodes_found': 1, 'errors_count': 0, 'warnings_count': 0}):
            response = self.client.get('/api/barcodes/inspect/' + job_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_press_operator_data(self.saved(job_id))['barcode_status'], 'PASS')
        self.client.post('/api/convert-to-cmyk/' + job_id)
        report = self.saved(job_id)
        self.assertNotIn('barcode_inspection', report['job_meta'])
        self.assertEqual(get_press_operator_data(report)['barcode_status'], 'NOT_VERIFIED')

    def test_rejection_does_not_display_the_signed_file_as_authorized(self):
        job_id = self.upload(False)['job_meta']['job_id']
        for decision in ('approved', 'rejected'):
            response = self.client.post('/api/release', data={
                'job_id': job_id, 'operator_name': 'Test', 'decision': decision})
            self.assertEqual(response.status_code, 200, response.text)
        report = self.saved(job_id)
        self.assertNotIn('authorized_sha256', report['job_meta'])
        data = get_press_operator_data(report)
        self.assertEqual(data['authorized_sha256'], 'No registrado')
        self.assertFalse(data['is_ready_for_press'])

    def test_release_accepts_only_the_three_explicit_decisions(self):
        job_id = self.upload(False)['job_meta']['job_id']
        for decision, expected in (('approved', 'AUTHORIZED'),
                                   ('approved_with_warnings', 'AUTHORIZED'), ('rejected', 'REJECTED')):
            with self.subTest(decision=decision):
                response = self.client.post('/api/release', data={
                    'job_id': job_id, 'operator_name': 'Test', 'decision': decision})
                self.assertEqual(response.status_code, 200, response.text)
                release = response.json()['release_result']
                self.assertEqual(release['status'], expected)
                self.assertEqual(release['decision'], decision)
                self.assertTrue(release['label'].startswith('Autorizado' if expected == 'AUTHORIZED' else 'Rechazado'))
                saved = self.saved(job_id)
                self.assertEqual(saved['triple_result']['release'], release)
                self.assertEqual('authorized_sha256' in saved['job_meta'], expected == 'AUTHORIZED')

    def test_invalid_release_decisions_leave_job_and_certificate_unchanged(self):
        invalid = ('not_approved', 'unapproved', 'approved_extra', 'APPROVED', ' approved', 'approved ', 'true', '')
        for initial_decision in (None, 'approved'):
            job_id = self.upload(False)['job_meta']['job_id']
            if initial_decision:
                response = self.client.post('/api/release', data={
                    'job_id': job_id, 'operator_name': 'Test', 'decision': initial_decision})
                self.assertEqual(response.status_code, 200)
            job_file = self.jobs / (job_id + '.json')
            certificate = self.jobs / (job_id + '_ficha_tecnica.pdf')
            before_job = job_file.read_bytes()
            before_certificate = certificate.read_bytes() if certificate.exists() else None
            with patch.object(app, 'generate_preflight_certificate_pdf') as generate:
                for decision in invalid:
                    with self.subTest(initial=initial_decision, decision=decision):
                        response = self.client.post('/api/release', data={
                            'job_id': job_id, 'operator_name': 'Test', 'decision': decision})
                        self.assertEqual(response.status_code, 422, response.text)
                        self.assertEqual(job_file.read_bytes(), before_job)
                        self.assertEqual(certificate.read_bytes() if certificate.exists() else None, before_certificate)
                generate.assert_not_called()

    def test_certificate_does_not_infer_authorization_from_not_approved(self):
        report = self.upload(False)
        report['triple_result']['release'] = {'decision': 'not_approved', 'operator': 'Test'}
        path = self.jobs / 'invalid_decision_certificate.pdf'
        app.generate_preflight_certificate_pdf(report, path)
        with pymupdf.open(path) as doc:
            text = ''.join(page.get_text() for page in doc)
        self.assertNotIn('AUTORIZADO TIRADA', text)
        self.assertIn('PENDIENTE / RECHAZADO', text)


if __name__ == '__main__':
    unittest.main()
