"""TAC action uses the profile target and preserves unresolved findings."""

import json
import unittest
from pathlib import Path

import pikepdf

from tac_limiter import measure_pdf_tac
import test_regressions as base


class TacActionTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp

    def upload_tac(self, vector=False):
        path=self.root/'high_tac.pdf'
        with pikepdf.new() as pdf:
            page=pdf.add_blank_page(page_size=(200,200))
            if vector:
                page.Contents=pdf.make_stream(b'1 1 1 .466667 k 20 20 160 160 re f')
            else:
                image=pdf.make_stream(bytes([240,240,240,164])*2)
                image.Type=pikepdf.Name.XObject; image.Subtype=pikepdf.Name.Image
                image.Width=2; image.Height=1; image.BitsPerComponent=8
                image.ColorSpace=pikepdf.Name.DeviceCMYK
                page.Resources=pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im=image))
                page.Contents=pdf.make_stream(b'q 160 0 0 160 20 20 cm /Im Do Q')
            pdf.save(path)
        response=self.client.post('/api/check', files={'file':('high_tac.pdf',path.read_bytes(),'application/pdf')},
                                  data={'profile_id':'DIGITAL_200'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('MAX_INK_COVERAGE',{f['rule_id'] for f in response.json()['findings']})
        return response.json()['job_meta']['job_id']

    def test_image_excess_is_corrected_to_the_320_percent_profile(self):
        job_id=self.upload_tac()
        response=self.client.post('/api/limit-tac/'+job_id)
        self.assertEqual(response.status_code,200,response.text)
        data=response.json()
        self.assertEqual(data['target_max_tac'],320)
        self.assertEqual(data['images_clamped'],1)
        self.assertNotIn('MAX_INK_COVERAGE',{f['rule_id'] for f in data['findings']})
        meta=data['report']['job_meta']
        self.assertEqual(meta['tac_limited_max_percent'],320)
        self.assertLessEqual(measure_pdf_tac(meta['last_fixed_pdf_path'])['peak_percent'],320)
        download=self.client.get(data['download_url'])
        self.assertIn('_TAC320.pdf',download.headers['content-disposition'])
        self.assertEqual(download.content,Path(meta['last_fixed_pdf_path']).read_bytes())

    def test_vector_excess_remains_pending_in_the_reanalysed_report(self):
        job_id=self.upload_tac(vector=True)
        data=self.client.post('/api/limit-tac/'+job_id).json()
        self.assertEqual(data['images_clamped'],0)
        self.assertIn('MAX_INK_COVERAGE',{f['rule_id'] for f in data['findings']})
        self.assertEqual(data['triple_result']['technical']['status'],'FAIL')
        saved=json.loads((self.jobs/(job_id+'.json')).read_text(encoding='utf-8'))
        self.assertEqual(data['findings'],saved['findings'])
