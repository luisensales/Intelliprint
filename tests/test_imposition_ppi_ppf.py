"""Physical-size, image-placement and PPF regressions from audit items 11–13."""

import json
import math
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pikepdf
import pymupdf

import app
from cip3_engine import calculate_ink_zone_coverage, generate_cip3_ppf, _render_ppf_preview
from imposition_engine import generate_imposed_pdf, calculate_imposition_plan
import test_regressions as base


def boxed_pdf(path, rotation=0, unit=1, offset=(0, 0), crop=False, booklet=False):
    ox, oy = offset
    with pikepdf.new() as pdf:
        for _ in range(4 if booklet else 1):
            page = pdf.add_blank_page(page_size=(240, 160))
            page.MediaBox = [ox, oy, ox + 240, oy + 160]
            page.TrimBox = [ox + 20, oy + 20, ox + 220, oy + 140]
            page.BleedBox = [ox + 10, oy + 10, ox + 230, oy + 150]
            if crop:
                page.CropBox = page.TrimBox
            page.Rotate = rotation
            page.UserUnit = unit
            page.Contents = pdf.make_stream(
                f"1 0 0 0 k {ox + 20} {oy + 30} 200 100 re f\n"
                f"0 1 0 0 k {ox} {oy} 8 8 re f\n".encode('ascii'))
        pdf.save(path)


class PdfFixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source, self.output = self.root / 'source.pdf', self.root / 'out.pdf'


class GeometryAndPpfTests(PdfFixture):
    def impose(self, **options):
        return generate_imposed_pdf(self.source, self.output, sheet_size='SRA3',
            user_cols=1, user_rows=1, add_marks=False, add_reg_crosses=False,
            add_color_bar=False, add_slug=False, **options)

    def test_artwork_keeps_physical_size_with_bleed_crop_rotation_and_userunit(self):
        for rotation, unit, offset, crop in ((0, 1, (0, 0), False),
                (90, 1, (0, 0), True), (180, 1, (30, 40), True),
                (270, 2, (-30, -40), True), (0, 2, (30, 40), True)):
            with self.subTest(rotation=rotation, unit=unit, offset=offset, crop=crop):
                boxed_pdf(self.source, rotation, unit, offset, crop)
                original = self.source.read_bytes()
                self.impose()
                self.assertEqual(self.source.read_bytes(), original)
                with pymupdf.open(self.output) as doc:
                    artwork = next(d for d in doc[0].get_drawings() if d['rect'].width * d['rect'].height > 1000)
                    sides = sorted((artwork['rect'].width, artwork['rect'].height))
                    self.assertAlmostEqual(sides[0], 100 * unit, delta=.02)
                    self.assertAlmostEqual(sides[1], 200 * unit, delta=.02)
                    # The magenta square outside BleedBox must not be painted.
                    pix = doc[0].get_pixmap(colorspace=pymupdf.csCMYK)
                    samples = np.frombuffer(pix.samples, dtype=np.uint8).reshape(-1, 4)
                    self.assertGreater(int(np.count_nonzero(samples[:, 0])), 5000 * unit)
                    self.assertEqual(int(samples[:, 1].max()), 0)

    def test_booklet_clips_trim_without_scaling(self):
        boxed_pdf(self.source, rotation=90, crop=True, booklet=True)
        self.impose(mode='booklet')
        with pymupdf.open(self.output) as doc:
            self.assertEqual(len(doc), 2)
            for page in doc:
                artwork = [d for d in page.get_drawings() if d['fill'] and d['rect'].width * d['rect'].height > 1000]
                self.assertEqual(len(artwork), 2)
                for drawing in artwork:
                    self.assertAlmostEqual(sorted((drawing['rect'].width, drawing['rect'].height))[1], 200, delta=.02)

    def test_mixed_page_sizes_are_rejected_before_writing(self):
        with pymupdf.open() as doc:
            doc.new_page(width=200, height=200).insert_text((20, 20), 'A')
            doc.new_page(width=210, height=200).insert_text((20, 20), 'B')
            doc.save(self.source)
        self.output.write_bytes(b'previous output')
        with self.assertRaisesRegex(ValueError, '100%'):
            self.impose()
        self.assertEqual(self.output.read_bytes(), b'previous output')

    def test_asymmetric_bleed_marks_match_trim_and_rotate(self):
        boxed_pdf(self.source)
        with pikepdf.open(self.source, allow_overwriting_input=True) as pdf:
            pdf.pages[0].TrimBox = [20, 25, 215, 130]
            pdf.save(self.source)
        with patch('imposition_engine._decorate_sheet') as decorate:
            self.impose(orientation='portrait')
        data = decorate.call_args.kwargs
        insets = data['trim_insets_pt']
        self.assertEqual(insets, (10, 20, 15, 15))
        self.assertAlmostEqual(data['pw_pt'] - insets[0] - insets[2], 195, delta=.02)
        self.assertAlmostEqual(data['ph_pt'] - insets[1] - insets[3], 105, delta=.02)
        with patch.dict('imposition_engine.STANDARD_SHEET_SIZES_MM', SRA3=(75, 120)), \
                patch('imposition_engine._decorate_sheet') as decorate:
            self.impose(orientation='portrait')
        data = decorate.call_args.kwargs
        self.assertEqual(data['trim_insets_pt'], (20, 15, 15, 10))
        self.assertAlmostEqual(data['pw_pt'], 140, delta=.02)
        self.assertAlmostEqual(data['ph_pt'], 220, delta=.02)

    def test_oversize_original_does_not_generate_a_clipped_sheet(self):
        with pymupdf.open() as doc:
            doc.new_page(width=3000, height=3000).insert_text((20, 20), 'oversize')
            doc.save(self.source)
        with self.assertRaisesRegex(ValueError, '100%'):
            self.impose()
        self.assertFalse(self.output.exists())

    def make_ppf(self, title='Test'):
        data = calculate_ink_zone_coverage(str(self.source))
        path = self.root / 'job.ppf'
        generate_cip3_ppf(data, str(path), 'test', title, pdf_path=self.source)
        return path.read_bytes()

    def test_ppf_has_required_structure_and_decodable_real_cmyk_image(self):
        boxed_pdf(self.source)
        raw = self.make_ppf('Prueba (A) \\ \n /Injected def — impresión')
        text = raw.decode('ascii')
        self.assertTrue(text.startswith('%!PS-Adobe-3.0\n%%CIP3-File Version 3.0\n'))
        self.assertTrue(text.endswith('%%CIP3EndOfFile\n'))
        expected = ['CIP3BeginSheet', 'CIP3BeginFront', 'CIP3BeginPreviewImage',
                    'CIP3PreviewImage', 'CIP3EndPreviewImage', 'CIP3EndFront', 'CIP3EndSheet']
        self.assertEqual([x for x in text.splitlines() if x in expected], expected)
        for field in ('CIP3AdmJobName', 'CIP3AdmPSExtent', 'CIP3AdmSeparationNames',
                      'CIP3TransferFilmCurveData', 'CIP3TransferPlateCurveData'):
            self.assertIn('/' + field, text)
        self.assertNotIn('CIP3InkZoneProfile', text)
        self.assertNotIn('\n /Injected def', text)
        self.assertNotIn('showpage', text)
        width = int(re.search(r'/CIP3PreviewImageWidth (\d+)', text)[1])
        height = int(re.search(r'/CIP3PreviewImageHeight (\d+)', text)[1])
        payload = raw.split(b'\nCIP3PreviewImage\n', 1)[1].split(b'\nCIP3EndPreviewImage', 1)[0]
        self.assertEqual(int(re.search(r'/CIP3PreviewImageDataSize (\d+)', text)[1]), len(payload))
        self.assertTrue(payload.endswith(b'>'))
        pixels = np.frombuffer(bytes.fromhex(payload[:-1].decode('ascii')), np.uint8).reshape(height, width, 4)
        self.assertEqual(int(pixels[0, 0].max()), 0)  # White, zero ink.
        self.assertEqual(pixels[height // 2, width // 2].tolist(), [255, 0, 0, 0])
        self.assertIn(f'/CIP3PreviewImageMatrix [{width} 0 0 {-height} 0 {height}]', text)

    def test_ppf_does_not_flatten_spot_inks_or_overwrite_existing_output(self):
        with pikepdf.new() as pdf:
            page = pdf.add_blank_page(page_size=(100, 100))
            tint = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0]*4, C1=[1, 0, 0, 0], N=1)
            page.Resources = pikepdf.Dictionary(ColorSpace=pikepdf.Dictionary(
                Spot=pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name('/PantoneTest'), pikepdf.Name.DeviceCMYK, tint])))
            page.Contents = pdf.make_stream(b'/Spot cs 1 scn 10 10 80 80 re f')
            pdf.save(self.source)
        path = self.root / 'job.ppf'
        path.write_bytes(b'previous output')
        with self.assertRaisesRegex(ValueError, 'tintas planas'):
            self.make_ppf()
        self.assertEqual(path.read_bytes(), b'previous output')

    def test_thin_lines_survive_high_resolution_sampling(self):
        with pikepdf.new() as pdf:
            page = pdf.add_blank_page(page_size=(72, 72))
            # Four subpixel lines per preview pixel, known 20% cyan area.
            page.Contents = pdf.make_stream(b'1 0 0 0 k\n' + b'\n'.join(
                f'{x / 10} 0 .05 72 re f'.encode() for x in range(0, 720, 2)))
            pdf.save(self.source)
        with pymupdf.open(self.source) as doc:
            preview = _render_ppf_preview(doc[0])
        pixels = np.array(preview)
        self.assertGreater(float(pixels[:, :, 0].mean()), 20)
        self.assertLess(float(pixels[:, :, 0].mean()), 100)

    def test_small_pages_have_finite_zone_coverage(self):
        with pymupdf.open() as doc:
            page = doc.new_page(width=10, height=10)
            page.draw_rect(page.rect, color=None, fill=(1, 0, 0, 0))
            doc.save(self.source)
        data = calculate_ink_zone_coverage(str(self.source))
        self.assertEqual(len(data['zones']), 32)
        self.assertTrue(all(z['c_coverage'] == 100 for z in data['zones']))
        json.dumps(data, allow_nan=False)


class ImagePlacementTests(PdfFixture):
    # Use a separate fixture helper; the tests below exercise full preflight output.
    def image_pdf(self, transforms, nested=False, inline=False):
        with pikepdf.new() as pdf:
            page = pdf.add_blank_page(page_size=(700, 700))
            image = pdf.make_stream(b'\x80' * (600 * 300))
            image.Type, image.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
            image.Width, image.Height, image.BitsPerComponent = 600, 300, 8
            image.ColorSpace = pikepdf.Name.DeviceGray
            resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im=image))
            content = b'\n'.join(('q ' + ' '.join(map(str, tr)) + ' cm /Im Do Q').encode() for tr in transforms)
            if inline:
                content = b'q 72 0 0 144 10 10 cm BI /W 1 /H 1 /BPC 8 /CS /G ID \x80 EI Q'
            if nested:
                form = pdf.make_stream(content)
                form.Type, form.Subtype = pikepdf.Name.XObject, pikepdf.Name.Form
                form.BBox, form.Resources = [0, 0, 700, 700], resources
                page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Fm=form))
                page.Contents = pdf.make_stream(b'/Fm Do')
            else:
                page.Resources, page.Contents = resources, pdf.make_stream(content)
            pdf.save(self.source)
        return app.engine.run_preflight(str(self.source))

    def test_every_reuse_is_checked_including_inside_a_form(self):
        result = self.image_pdf([(72, 0, 0, 72, 10, 10), (288, 0, 0, 144, 100, 100)], nested=True)
        inventory = result['job_summary']['images_inventory']
        self.assertEqual([x['effective_dpi'] for x in inventory], [300, 150])
        self.assertEqual(inventory[0]['xref'], inventory[1]['xref'])
        self.assertEqual(len([f for f in result['findings'] if f['rule_id'] == 'PRINT_IMAGE_EFFECTIVE_PPI']), 1)

    def test_minimum_axis_detects_anisotropic_low_resolution(self):
        result = self.image_pdf([(36, 0, 0, 144, 10, 10)])
        image = result['job_summary']['images_inventory'][0]
        self.assertEqual((image['dpi_x'], image['dpi_y'], image['effective_dpi']), (1200, 150, 150))
        self.assertTrue(any(f['rule_id'] == 'PRINT_IMAGE_EFFECTIVE_PPI' for f in result['findings']))

    def test_rotation_reflection_and_shear_use_axis_lengths(self):
        for tr in ((0, 72, -72, 0, 200, 10), (-72, 0, 0, 72, 200, 10),
                   (72, 0, 36, 36 * math.sqrt(3), 10, 10)):
            with self.subTest(transform=tr):
                image = self.image_pdf([tr])['job_summary']['images_inventory'][0]
                self.assertAlmostEqual(image['dpi_x'], 600, delta=.1)
                self.assertAlmostEqual(image['dpi_y'], 300, delta=.1)
                self.assertFalse(any(f['rule_id'] == 'PRINT_IMAGE_EFFECTIVE_PPI'
                                     for f in app.engine.run_preflight(str(self.source))['findings']))

    def test_inline_image_is_checked(self):
        image = self.image_pdf([], inline=True)['job_summary']['images_inventory'][0]
        self.assertEqual(image['xref'], 0)
        self.assertEqual(image['effective_dpi'], .5)
        self.assertEqual(image['dpi_y'], .5)


class PpfEndpointTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp
    upload = base.RegressionTests.upload

    def test_download_replaces_legacy_ppf_using_saved_imposed_pdf(self):
        job_id = self.upload(with_image=False)['job_meta']['job_id']
        imposed = self.jobs / 'imposed.pdf'
        boxed_pdf(imposed)
        job_file = self.jobs / (job_id + '.json')
        report = json.loads(job_file.read_text(encoding='utf-8'))
        report['job_meta']['imposed_pdf_path'] = str(imposed)
        report['job_meta']['imposition_source_sha256'] = report['job_meta']['current_sha256']
        job_file.write_text(json.dumps(report), encoding='utf-8')
        ppf = self.jobs / job_id / f'CIP3_{job_id}_32Z.ppf'
        ppf.parent.mkdir()
        ppf.write_bytes(b'%!PS-Adobe-3.0\n/CIP3Admin 10 dict def\nshowpage\n')
        response = self.client.get('/api/cip3/download/ppf/' + job_id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(b'%%CIP3-File Version 3.0', response.content)
        self.assertIn(b'/CIP3AdmPSExtent [240.00000000 160.00000000]', response.content)


if __name__ == '__main__':
    unittest.main()
