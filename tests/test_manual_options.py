"""Regressions for options verified while documenting the production tools."""

import json
import unittest
from unittest.mock import patch

import app
import test_regressions as base


class DocumentedOptionTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp
    upload = base.RegressionTests.upload

    def test_cmyk_conversion_uses_the_profile_posted_by_the_browser(self):
        job_id = self.upload()['job_meta']['job_id']
        selected = 'PSOuncoated_v3_FOGRA52.icc'
        with patch.object(app, 'convert_rgb_images_to_cmyk', wraps=app.convert_rgb_images_to_cmyk) as convert:
            result = self.client.post('/api/convert-to-cmyk/' + job_id,
                                      data={'use_embedded_icc': 'false', 'custom_icc': selected})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(convert.call_args.kwargs['dst_icc_path'], str(app.ICC_DIR / selected))
        self.assertEqual(result.json()['images_converted'], 1)

    def test_invalid_form_icc_does_not_start_conversion(self):
        job_id = self.upload()['job_meta']['job_id']
        for values in [{'use_embedded_icc': 'invalid'},
                       {'use_embedded_icc': 'false', 'custom_icc': '../outside.icc'},
                       {'use_embedded_icc': 'false'}]:
            with self.subTest(values=values), patch.object(app, 'convert_rgb_images_to_cmyk') as convert:
                result = self.client.post('/api/convert-to-cmyk/' + job_id, data=values)
                self.assertEqual(result.status_code, 400, result.text)
                convert.assert_not_called()

    def test_cip3_auto_uses_the_saved_imposed_sheet(self):
        job_id = self.upload(with_image=False)['job_meta']['job_id']
        imposed = self.jobs / 'imposed.pdf'
        imposed.write_bytes(base.sample_pdf(False))
        job_file = self.jobs / (job_id + '.json')
        report = json.loads(job_file.read_text(encoding='utf-8'))
        report['job_meta']['imposed_pdf_path'] = str(imposed)
        job_file.write_text(json.dumps(report), encoding='utf-8')
        with patch.object(app, 'calculate_ink_zone_coverage', wraps=app.calculate_ink_zone_coverage) as calculate:
            result = self.client.post('/api/cip3/calculate/' + job_id, json={'source': 'auto'})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(calculate.call_args.kwargs['pdf_path'], str(imposed))
        self.assertEqual(result.json()['source_used'], 'Pliego_Imposicion')


if __name__ == '__main__':
    unittest.main()
