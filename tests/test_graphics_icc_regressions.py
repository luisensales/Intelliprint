"""Render and API regressions for scoped corrections, graphics scans and ICCs."""

import io
import json
import struct
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import pikepdf
import pymupdf

import app
import icc_manager
from overprint_fixer import (apply_overprint_to_dark_text, apply_overprint_to_technical_inks,
                             fix_rich_black_small_text, fix_white_overprint)
from pdf_graphics import new_graphics_state
from preflight_engine import scan_content_stream
import test_regressions as base


def make_pdf(path, content, customize=None):
    with pikepdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(300, 300))
        font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font,
            Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font),
            ExtGState=pikepdf.Dictionary(
                Both=pikepdf.Dictionary(op=True, OP=True, OPM=1),
                Fill=pikepdf.Dictionary(op=True, OP=False, OPM=1),
                Stroke=pikepdf.Dictionary(op=False, OP=True, OPM=1),
                OPOnly=pikepdf.Dictionary(OP=True, OPM=1),
                None_=pikepdf.Dictionary(op=False, OP=False, OPM=0)))
        page.Contents = pdf.make_stream(content)
        if customize:
            customize(pdf, page)
        pdf.save(path)


def scan(path):
    data = defaultdict(int, incidents=[], min_hairline_threshold=.25)
    with pikepdf.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            scan_content_stream(list(pikepdf.parse_content_stream(page)), page.resources,
                                number, data, new_graphics_state(page))
    return data


def pixel(path, x=110, y=230):
    with pymupdf.open(path) as pdf:
        pix = pdf[0].get_pixmap(colorspace=pymupdf.csCMYK, dpi=72)
        offset = (y * pix.width + x) * 4
        return tuple(pix.samples[offset:offset + 4])


def text_details(path):
    with pymupdf.open(path) as pdf:
        spans = [span for block in pdf[0].get_text('dict')['blocks'] if 'lines' in block
                 for line in block['lines'] for span in line['spans']]
        chars = [(char['c'], char['origin']) for block in pdf[0].get_text('rawdict')['blocks']
                 if 'lines' in block for line in block['lines'] for span in line['spans']
                 for char in span['chars']]
        return spans, chars


def text_ink_peaks(path, span):
    with pymupdf.open(path) as pdf:
        pix = pdf[0].get_pixmap(colorspace=pymupdf.csCMYK, dpi=150,
                               clip=pymupdf.Rect(span['bbox']), alpha=False)
        return tuple(max(pix.samples[channel::4]) for channel in range(4))


def attach_intent(pdf, data=None, label='FOGRA', channels=None):
    intent = pikepdf.Dictionary(Type=pikepdf.Name.OutputIntent, S=pikepdf.Name.GTS_PDFX,
                               OutputConditionIdentifier=label)
    if data is not None:
        stream = pdf.make_stream(data)
        if channels is not None:
            stream.N = channels
        intent.DestOutputProfile = stream
    pdf.Root.OutputIntents = pikepdf.Array([intent])
    return intent


class GraphicsRegressionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source, self.output = self.root / 'source.pdf', self.root / 'output.pdf'

    def test_rich_black_correction_preserves_larger_text_and_vector_color(self):
        make_pdf(self.source, b'.6 .4 .4 .7 k BT /F1 10 Tf 20 240 Td (Small) Tj '
                 b'/F1 24 Tf 0 -60 Td (Large) Tj ET 100 50 80 30 re f')
        before_spans, before_chars = text_details(self.source)
        before_vector = pixel(self.source)
        result = fix_rich_black_small_text(self.source, self.output)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['texts_fixed'], 1)
        after_spans, after_chars = text_details(self.output)
        self.assertEqual(before_chars, after_chars)
        self.assertEqual(pixel(self.output), before_vector)
        before_colors = {s['text']: s['color'] for s in before_spans}
        after_colors = {s['text']: s['color'] for s in after_spans}
        inks = text_ink_peaks(self.output, next(s for s in after_spans if s['text'] == 'Small'))
        self.assertEqual(inks[:3], (0, 0, 0))
        self.assertGreater(inks[3], 200)
        self.assertEqual(after_colors['Large'], before_colors['Large'])
        self.assertEqual(scan(self.output)['rich_black_small_text'], 0)

    def test_consecutive_text_and_quote_spacing_keep_their_positions(self):
        make_pdf(self.source, b'.6 .4 .4 .7 k BT /F1 10 Tf 20 240 Td 16 TL '
                 b'(First) Tj (Second) Tj (Third) \' 3 2 (Fourth) " (Fifth) Tj ET '
                 b'100 50 80 30 re f')
        _, before = text_details(self.source)
        original_vector = pixel(self.source)
        result = fix_rich_black_small_text(self.source, self.output)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['texts_fixed'], 5)
        self.assertEqual(text_details(self.output)[1], before)
        self.assertEqual(pixel(self.output), original_vector)

    def test_shared_form_changes_only_the_small_instance(self):
        def resources(pdf, page):
            form = pdf.make_stream(b'BT /F1 10 Tf 10 40 Td (Test) Tj ET')
            form.Type, form.Subtype, form.BBox = pikepdf.Name.XObject, pikepdf.Name.Form, [0, 0, 100, 100]
            page.Resources.XObject = pikepdf.Dictionary(F=form)
        make_pdf(self.source, b'.6 .4 .4 .7 k q /F Do Q q 2 0 0 2 100 100 cm /F Do Q', resources)
        before, positions = text_details(self.source)
        result = fix_rich_black_small_text(self.source, self.output)
        self.assertEqual(result['texts_fixed'], 1, result)
        after, after_positions = text_details(self.output)
        self.assertEqual(positions, after_positions)
        inks = text_ink_peaks(self.output, after[0])
        self.assertEqual(inks[:3], (0, 0, 0))
        self.assertGreater(inks[3], 200)
        self.assertEqual(after[1]['color'], before[1]['color'])

    def test_dark_text_overprint_is_local_and_survives_original_q_Q(self):
        make_pdf(self.source, b'0 g q BT /F1 10 Tf 20 240 Td (First) Tj ET Q '
                 b'BT /F1 10 Tf 20 200 Td (Second) Tj ET 1 g 20 20 40 40 re f')
        result = apply_overprint_to_dark_text(self.source, self.output)
        self.assertEqual(result['text_ops_fixed'], 2, result)
        data = scan(self.output)
        self.assertEqual(data['black_text_overprint'], 2)
        self.assertEqual(data['black_text_knockout'], 0)
        self.assertEqual(data['white_overprint'], 0)

    def test_scan_combined_operators_checks_stroke_and_hairline(self):
        for operator in (b'S', b'B', b'B*', b'b', b'b*'):
            with self.subTest(operator=operator):
                make_pdf(self.source, b'/Both gs 0 g 1 G .1 w 20 20 40 40 re ' + operator)
                data = scan(self.source)
                self.assertEqual(data['white_overprint'], 1)
                self.assertEqual(data['hairlines_count'], 1)

    def test_form_inherits_overprint_color_width_and_matrix(self):
        def resources(pdf, page):
            form = pdf.make_stream(b'20 20 40 40 re B')
            form.Type, form.Subtype, form.BBox = pikepdf.Name.XObject, pikepdf.Name.Form, [0, 0, 200, 200]
            form.Matrix = [.5, 0, 0, .5, 0, 0]
            page.Resources.XObject = pikepdf.Dictionary(F=form)
        make_pdf(self.source, b'/Both gs 0 g 1 G .4 w /F Do', resources)
        data = scan(self.source)
        self.assertEqual(data['white_overprint'], 1)
        self.assertEqual(data['hairlines_count'], 1)
        result = fix_white_overprint(self.source, self.output)
        self.assertEqual(result['objects_fixed'], 1, result)
        self.assertEqual(scan(self.output)['white_overprint'], 0)

    def test_white_stroke_correction_preserves_the_fill_overprint(self):
        make_pdf(self.source, b'/Both gs 0 g 1 G 1 w 20 20 40 40 re B '
                 b'BT /F1 10 Tf 20 240 Td (Still overprinting) Tj ET')
        result = fix_white_overprint(self.source, self.output)
        self.assertEqual(result['objects_fixed'], 1, result)
        data = scan(self.output)
        self.assertEqual(data['white_overprint'], 0)
        self.assertEqual(data['black_text_overprint'], 1)

    def test_text_render_modes_examine_only_the_components_that_paint(self):
        for mode, expected in ((0, 0), (1, 1), (2, 1), (3, 0), (4, 0), (5, 1), (6, 1), (7, 0)):
            with self.subTest(mode=mode):
                make_pdf(self.source, b'/Both gs 0 g 1 G BT /F1 10 Tf ' + str(mode).encode() +
                         b' Tr 20 240 Td (Test) Tj ET')
                self.assertEqual(scan(self.source)['white_overprint'], expected)
                result = fix_white_overprint(self.source, self.output)
                self.assertEqual(result['objects_fixed'], expected, result)
                self.assertEqual(scan(self.output)['white_overprint'], 0)

    def test_OP_without_op_applies_to_both_fill_and_stroke(self):
        make_pdf(self.source, b'/OPOnly gs 1 g 20 20 40 40 re f')
        self.assertEqual(scan(self.source)['white_overprint'], 1)
        self.assertEqual(fix_white_overprint(self.source, self.output)['objects_fixed'], 1)
        self.assertEqual(scan(self.output)['white_overprint'], 0)

    def test_repeated_white_and_rich_corrections_are_idempotent(self):
        make_pdf(self.source, b'/Both gs 1 G 0 g 1 w 20 20 40 40 re S '
                 b'.6 .4 .4 .7 k BT /F1 10 Tf 20 240 Td (Small) Tj ET')
        self.assertTrue(fix_white_overprint(self.source, self.output)['success'])
        self.assertEqual(fix_white_overprint(self.output, self.output)['objects_fixed'], 0)
        self.assertEqual(fix_rich_black_small_text(self.output, self.output)['texts_fixed'], 1)
        self.assertEqual(fix_rich_black_small_text(self.output, self.output)['texts_fixed'], 0)

    def test_technical_ink_overprint_does_not_spread_to_white_objects(self):
        def resources(pdf, page):
            function = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=[0, 1, 0, 0], N=1)
            page.Resources.ColorSpace = pikepdf.Dictionary(V=pikepdf.Array([
                pikepdf.Name.Separation, pikepdf.Name('/Barniz'), pikepdf.Name.DeviceCMYK, function]))
        make_pdf(self.source, b'/V cs 1 scn 20 20 40 40 re f 1 g 100 20 40 40 re f', resources)
        result = apply_overprint_to_technical_inks(self.source, self.output)
        self.assertEqual(result['ops_fixed'], 1, result)
        data = scan(self.output)
        self.assertEqual(data['varnish_knockout'], 0)
        self.assertEqual(data['white_overprint'], 0)

    def test_failed_correction_does_not_overwrite_the_previous_output(self):
        make_pdf(self.source, b'Q')
        self.output.write_bytes(b'previous output')
        for fixer in (fix_white_overprint, fix_rich_black_small_text, apply_overprint_to_dark_text):
            result = fixer(self.source, self.output)
            self.assertFalse(result['success'])
            self.assertEqual(self.output.read_bytes(), b'previous output')


class IccRegressionTests(unittest.TestCase):
    def test_empty_or_fake_profiles_cannot_be_validated_by_the_label(self):
        with pikepdf.new() as pdf:
            for data in (None, b'NOT AN ICC PROFILE' * 20, b''):
                with self.subTest(data=data):
                    attach_intent(pdf, data, 'FOGRA PSO CMYK ISO Coated')
                    result = icc_manager.detect_pdf_output_intent(pdf)
                    self.assertTrue(result['has_output_intent'])
                    self.assertFalse(result['icc_valid'])
                    self.assertEqual(result['detected_family'], 'Desconocido')

    def test_real_color_space_overrides_a_misleading_profile_label(self):
        for filename, label, expected, channels in (
                ('sRGB2014.icc', 'FOGRA CMYK', 'RGB', 3),
                ('PSOcoated_v3.icc', 'sRGB for display', 'CMYK', 4)):
            with self.subTest(filename=filename), pikepdf.new() as pdf:
                attach_intent(pdf, (icc_manager.ICC_DIR / filename).read_bytes(), label, channels)
                result = icc_manager.detect_pdf_output_intent(pdf)
                self.assertTrue(result['icc_valid'], result)
                self.assertEqual(result['detected_family'], expected)

    def test_truncated_and_out_of_bounds_icc_tags_are_rejected(self):
        original = (icc_manager.ICC_DIR / 'sRGB2014.icc').read_bytes()
        bad_tag = bytearray(original)
        struct.pack_into('>I', bad_tag, 136, len(original) + 100)
        for data in (original[:-1], bytes(bad_tag), b'\0' * 36 + b'acsp' + b'\0' * 300):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                icc_manager.validate_icc_bytes(data)

    def test_profile_channel_declaration_must_match_binary_profile(self):
        with pikepdf.new() as pdf:
            attach_intent(pdf, (icc_manager.ICC_DIR / 'PSOcoated_v3.icc').read_bytes(), channels=3)
            result = icc_manager.detect_pdf_output_intent(pdf)
            self.assertFalse(result['icc_valid'])
            self.assertTrue(result['has_icc_stream'])

    def test_valid_later_intent_is_not_hidden_by_an_empty_first_one(self):
        with pikepdf.new() as pdf:
            first = attach_intent(pdf)
            good = attach_intent(pdf, (icc_manager.ICC_DIR / 'PSOcoated_v3.icc').read_bytes(), channels=4)
            pdf.Root.OutputIntents = [first, good]
            self.assertTrue(icc_manager.detect_pdf_output_intent(pdf)['icc_valid'])

    def test_pdf_bytes_are_supported_and_real_catalog_profiles_remain_available(self):
        with pikepdf.new() as pdf:
            pdf.add_blank_page()
            attach_intent(pdf, (icc_manager.ICC_DIR / 'sRGB2014.icc').read_bytes(), channels=3)
            stream = io.BytesIO(); pdf.save(stream)
        self.assertEqual(icc_manager.detect_pdf_output_intent(stream.getvalue())['detected_family'], 'RGB')
        self.assertEqual({p['id'] for p in icc_manager.get_available_icc_profiles()},
                         {p.name for p in icc_manager.ICC_DIR.glob('*.icc')})

    def test_catalog_uses_profile_bytes_even_when_the_filename_claims_cmyk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'FOGRA_CMYK.icc'
            path.write_bytes((icc_manager.ICC_DIR / 'sRGB2014.icc').read_bytes())
            with patch.object(icc_manager, 'ICC_DIR', Path(directory)):
                self.assertEqual(icc_manager.get_available_icc_profiles()[0]['family'], 'RGB')


class GraphicsApiTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp

    def upload_pdf(self, content, intent=None):
        path = self.root / 'source.pdf'
        make_pdf(path, content, intent)
        response = self.client.post('/api/check', files={'file': ('source.pdf', path.read_bytes())})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_missing_icc_stream_fails_the_preflight_and_preview_validation(self):
        report = self.upload_pdf(b'0 g 20 20 40 40 re f', lambda pdf, page: attach_intent(pdf))
        self.assertIn('DOCUMENT_OUTPUT_ICC', {f['rule_id'] for f in report['findings']})
        self.assertFalse(report['job_summary']['icc_detected']['icc_valid'])
        content = Path(report['job_meta']['pdf_path']).read_bytes()
        preview = self.client.post('/api/inspect-pdf', files={'file': ('source.pdf', content)})
        self.assertFalse(preview.json()['output_intent']['icc_valid'])

    def test_combined_stroke_is_reported_and_overprint_action_removes_the_white_fault(self):
        report = self.upload_pdf(b'/Both gs 0 g 1 G .1 w 20 20 40 40 re B')
        rules = {f['rule_id'] for f in report['findings']}
        self.assertTrue({'WHITE_OVERPRINT', 'HAIRLINE_DETECTED'} <= rules)
        response = self.client.post('/api/apply-overprint/' + report['job_meta']['job_id'])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(response.json()['white_objects_fixed'], 0)
        self.assertNotIn('WHITE_OVERPRINT', {f['rule_id'] for f in response.json()['report']['findings']})

    def test_unverifiable_graphics_are_reported_instead_of_silently_passing(self):
        report = self.upload_pdf(b'Q')
        self.assertIn('GRAPHICS_NOT_VERIFIED', {f['rule_id'] for f in report['findings']})
        self.assertEqual(report['triple_result']['technical']['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
