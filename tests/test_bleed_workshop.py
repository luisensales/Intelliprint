"""Visible bleed/crop-mark regressions for the complete one-click workflow."""

import json
import tempfile
import unittest
from pathlib import Path

import pikepdf
import pymupdf

import app
from geometry_fixer import fix_pdf_boxes_and_bleed
from mirror_bleed_generator import generate_mirror_bleed
from printer_marks_generator import add_printer_marks_to_pdf
import test_regressions as base


def orange_pdf(path, rotation=0, origin=(0, 0), unit=1, white=False):
    x, y = origin
    with pikepdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(300, 420))
        page.MediaBox = [x, y, x + 300, y + 420]
        page.Rotate = rotation
        page.UserUnit = unit
        fill = '0 0 0 0' if white else '0 .6 1 0'
        page.Contents = pdf.make_stream(
            f'{fill} k {x} {y} 300 420 re f 0 0 0 1 k {x+50} {y+100} 100 60 re f'.encode())
        page.Annots = pikepdf.Array([pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link,
            Rect=[x + 50, y + 100, x + 150, y + 160], Border=[0, 0, 0],
            A=pikepdf.Dictionary(S=pikepdf.Name.URI, URI='https://example.invalid/')))])
        pdf.save(path)


def pixel(path, x, y):
    """Sample PDF coordinates even with negative origins, rotation and UserUnit."""
    with pymupdf.open(path) as pdf:
        page = pdf[0]
        media = page.mediabox
        ux, uy = x - media.x0, media.y1 - y
        w, h = media.width, media.height
        positions = {0:(ux,uy),90:(h-uy,ux),180:(w-ux,h-uy),270:(uy,w-ux)}
        sx, sy = positions[page.rotation]
        unit = page.rect.width / (h if page.rotation in (90,270) else w)
        pixmap = page.get_pixmap(colorspace=pymupdf.csCMYK)
        return pixmap.pixel(round(sx*unit) - pixmap.x, round(sy*unit) - pixmap.y)


class BleedTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_coloured_bleed_and_marks_keep_artwork_size_colour_and_annotations(self):
        for rotation, origin, unit in [(0, (0, 0), 1), (90, (-20, 15), 1), (270, (30, -40), 2)]:
            with self.subTest(rotation=rotation, origin=origin, unit=unit):
                source, boxes, bled, marked = [self.root / (name + '.pdf') for name in ('source', 'boxes', 'bled', 'marked')]
                orange_pdf(source, rotation, origin, unit)
                fix_pdf_boxes_and_bleed(source, boxes)
                self.assertTrue(generate_mirror_bleed(boxes, bled)['success'])
                self.assertTrue(add_printer_marks_to_pdf(bled, marked)['success'])
                x, y = origin
                original_colour = pixel(source, x + 10, y + 10)
                bleed = 3 * 72 / 25.4 / unit
                # Four edges and four corners must contain the ORIGINAL CMYK.
                for path in (bled, marked):
                    for bx, by in [(x-bleed/2,y+210), (x+300+bleed/2,y+210),
                                   (x+150,y-bleed/2), (x+150,y+420+bleed/2),
                                   (x-bleed/2,y-bleed/2), (x+300+bleed/2,y-bleed/2),
                                   (x-bleed/2,y+420+bleed/2), (x+300+bleed/2,y+420+bleed/2)]:
                        self.assertEqual(pixel(path, bx, by), original_colour)
                    # The black rectangle still starts at its original coordinate.
                    self.assertEqual(pixel(path, x+47, y+125), original_colour)
                    self.assertEqual(pixel(path, x+54, y+125), pixel(source, x+54, y+125))
                    with pikepdf.open(path) as result:
                        page = result.pages[0]
                        self.assertEqual(list(page.TrimBox), [x,y,x+300,y+420])
                        self.assertEqual(int(page.Rotate), rotation)
                        self.assertEqual(float(page.UserUnit), unit)
                        self.assertEqual(len(page.Annots), 1)
                    with pymupdf.open(path) as result:
                        self.assertEqual(result[0].get_images(), [])

    def test_marks_are_aligned_with_trim_and_outside_the_bleed(self):
        source, marked = self.root/'source.pdf', self.root/'marked.pdf'
        orange_pdf(source)
        generate_mirror_bleed(source, source)
        add_printer_marks_to_pdf(source, marked)
        bleed, gap = 3 * 72 / 25.4, 72 / 25.4
        with pymupdf.open(marked) as pdf:
            page = pdf[0]
            inverse = ~page.transformation_matrix
            marks = []
            for drawing in page.get_drawings():
                if drawing['type'] == 's' and len(drawing['items']) == 1 and drawing['items'][0][0] == 'l':
                    _, a, b = drawing['items'][0]
                    a, b = a * inverse, b * inverse
                    if abs(a.x-b.x) < .01 and any(abs(a.x-edge) < .01 for edge in (0,300)):
                        marks.append((a,b))
                        self.assertTrue(max(a.y,b.y) <= -bleed-gap+.01 or min(a.y,b.y) >= 420+bleed+gap-.01)
                    elif abs(a.y-b.y) < .01 and any(abs(a.y-edge) < .01 for edge in (0,420)):
                        marks.append((a,b))
                        self.assertTrue(max(a.x,b.x) <= -bleed-gap+.01 or min(a.x,b.x) >= 300+bleed+gap-.01)
            self.assertEqual(len(marks), 8)

    def test_repeating_both_actions_preserves_boxes_and_existing_real_bleed(self):
        source, first, second = [self.root/(name+'.pdf') for name in ('source','first','second')]
        orange_pdf(source)
        generate_mirror_bleed(source, first)
        add_printer_marks_to_pdf(first, first, job_filename='source.pdf')
        generate_mirror_bleed(first, second)
        add_printer_marks_to_pdf(second, second, job_filename='source.pdf')
        with pikepdf.open(first) as a, pikepdf.open(second) as b:
            for box in ('/MediaBox','/TrimBox','/BleedBox'):
                self.assertEqual(a.pages[0][box], b.pages[0][box])
        for point in [(-4,210), (304,210), (150,-4), (150,424), (49,125), (51,125)]:
            self.assertEqual(pixel(first,*point), pixel(second,*point))

    def test_a_white_design_keeps_its_white_bleed(self):
        source, target = self.root/'white.pdf', self.root/'bled.pdf'
        orange_pdf(source, white=True)
        generate_mirror_bleed(source, target)
        self.assertEqual(pixel(target,-4,210), (0,0,0,0))

    def test_existing_real_bleed_takes_precedence_over_the_reflection(self):
        source, target = self.root/'real.pdf', self.root/'bled.pdf'
        orange_pdf(source)
        with pikepdf.open(source,allow_overwriting_input=True) as pdf:
            p=pdf.pages[0]
            p.TrimBox=[10,10,290,410]
            p.Contents=pdf.make_stream(b'1 0 0 0 k 0 0 300 420 re f 0 .6 1 0 k 10 10 280 400 re f')
            pdf.save(source)
        generate_mirror_bleed(source,target)
        self.assertEqual(pixel(source,6,200),pixel(target,6,200))


class WorkshopTests(unittest.TestCase):
    setUp = base.RegressionTests.setUp

    def test_default_workshop_actually_uses_both_generated_results(self):
        source = self.root/'orange.pdf'
        orange_pdf(source)
        upload = self.client.post('/api/check', files={'file': ('orange.pdf',source.read_bytes(),'application/pdf')})
        self.assertEqual(upload.status_code,200,upload.text)
        job_id = upload.json()['job_meta']['job_id']
        options = {name:'false' for name in ('trapping','hairlines','fonts','cmyk_images','icc','tac')}
        response = self.client.post('/api/batch-fix/'+job_id,params=options)
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['success'],response.text)
        self.assertEqual([s['action'] for s in response.json()['steps_applied']], ['geometry','mirror_bleed','printer_marks'])
        report = json.loads((self.jobs/(job_id+'.json')).read_text(encoding='utf-8'))
        output = Path(report['job_meta']['last_fixed_pdf_path'])
        self.assertEqual(pixel(source,10,10),pixel(output,-4,210))
        download = self.client.get(response.json()['download_url'])
        self.assertEqual(download.content,output.read_bytes())

    def test_screen_profile_adds_neither_bleed_nor_print_marks(self):
        source = self.root/'screen.pdf'
        orange_pdf(source)
        upload = self.client.post('/api/check', files={'file': ('screen.pdf',source.read_bytes(),'application/pdf')},
                                  data={'profile_id':'PANTALLA_RGB'})
        job_id=upload.json()['job_meta']['job_id']
        options={name:'false' for name in ('trapping','hairlines','fonts','cmyk_images','icc','tac')}
        response=self.client.post('/api/batch-fix/'+job_id,params=options)
        self.assertTrue(response.json()['success'],response.text)
        self.assertNotIn('mirror_bleed',[s['action'] for s in response.json()['steps_applied']])
        self.assertNotIn('printer_marks',[s['action'] for s in response.json()['steps_applied']])


if __name__ == '__main__':
    unittest.main()
