"""Keep the four manual editions complete and in sync with the public controls."""

import re
import unittest
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

import pymupdf
from fastapi.testclient import TestClient

import app
from didactic_engine import SCENARIOS_CATALOG
from manual_content import (
    BASE_DIR, MANUAL_EDITION, MANUAL_SOURCE, parse_manual, plain_text, read_manual,
)


class Controls(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.fields = {}
        self.select = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('input', 'select', 'textarea') and attrs.get('type') != 'hidden':
            key = ('name:' + attrs['name']) if attrs.get('type') == 'radio' else attrs.get('id')
            if key:
                values = self.fields.setdefault(key, set())
                if attrs.get('type') == 'radio':
                    values.add(attrs.get('value', ''))
                if tag == 'select':
                    self.select = key
        elif tag == 'option' and self.select and attrs.get('value'):
            self.fields[self.select].add(attrs['value'])

    def handle_endtag(self, tag):
        if tag == 'select':
            self.select = None


def canonical_fragments():
    for block in parse_manual():
        if 'text' in block:
            yield plain_text(block['text'])
        for row in block.get('rows', []):
            yield from (plain_text(cell) for cell in row)
        yield from (plain_text(item) for item in block.get('items', []))


def compact(text):
    return re.sub(r'\s+', '', text)


class ManualTests(unittest.TestCase):
    def test_every_public_static_field_and_select_option_is_documented(self):
        source = read_manual()
        documented = set(' '.join(re.findall(r'<!-- ui-controls: (.*?) -->', source)).split())
        values = {key: set(items.split(',')) for key, items in re.findall(r'<!-- ui-values: (.*?)=(.*?) -->', source)}
        controls = Controls((BASE_DIR / 'static/index.html').read_text(encoding='utf-8'))
        self.assertGreater(len(controls.fields), 50)
        self.assertEqual(set(controls.fields) - documented, set(), 'New controls need instructions in the manual')
        for key, options in controls.fields.items():
            if options:
                with self.subTest(control=key):
                    self.assertEqual(values.get(key), options)
        self.assertTrue({'rngShift', 'rngTac', 'chkHasBleed', 'rngCut', 'rngStroke', 'quiz'} <= documented)

    def test_all_twenty_scenarios_and_nine_chapters_are_present(self):
        source = read_manual()
        self.assertEqual(len(SCENARIOS_CATALOG), 20)
        for scenario in SCENARIOS_CATALOG:
            self.assertIn(scenario['title'], source)
        chapters = [b for b in parse_manual() if b['kind'] == 'heading' and b['level'] == 2]
        self.assertEqual(len(chapters), 9)
        self.assertNotRegex(source, r'\w\?\w|\ufffd')

    def test_full_web_manual_and_all_downloads(self):
        with TestClient(app.app) as client:
            info = client.get('/api/manual/info').json()
            self.assertEqual(info['version'], MANUAL_EDITION)
            self.assertEqual(info['web_url'], '/manual')
            page = client.get('/manual')
            self.assertEqual(page.status_code, 200)
            for block in parse_manual():
                if block['kind'] == 'heading':
                    self.assertIn('id="' + block['anchor'] + '"', page.text)
            self.assertIn('imprimir', page.text.lower())
            self.assertIn('class="embedded"', client.get('/manual?embed=1').text)
            for extension, filename in [('md', MANUAL_SOURCE.name), ('pdf', 'Manual_de_Usuario_IntelliPrint.pdf'), ('docx', 'Manual_de_Usuario_IntelliPrint.docx')]:
                with self.subTest(format=extension):
                    response = client.get('/api/manual/download/' + extension)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.content, (BASE_DIR / filename).read_bytes())
                    self.assertIn(MANUAL_EDITION, response.headers['content-disposition'])

    def test_word_contains_every_canonical_instruction_and_option(self):
        with zipfile.ZipFile(BASE_DIR / 'Manual_de_Usuario_IntelliPrint.docx') as archive:
            tree = ElementTree.fromstring(archive.read('word/document.xml'))
        text = compact(''.join(tree.itertext()))
        for fragment in canonical_fragments():
            with self.subTest(fragment=fragment[:70]):
                self.assertIn(compact(fragment), text)

    def test_pdf_contains_every_canonical_instruction_and_option(self):
        with pymupdf.open(BASE_DIR / 'Manual_de_Usuario_IntelliPrint.pdf') as document:
            self.assertGreaterEqual(len(document), 20)
            # Exclude running headers/footers so paragraphs spanning pages join.
            text = compact(''.join(page.get_text(clip=pymupdf.Rect(0, 45, page.rect.width, page.rect.height - 45))
                                   for page in document))
        for fragment in canonical_fragments():
            with self.subTest(fragment=fragment[:70]):
                self.assertIn(compact(fragment), text)


if __name__ == '__main__':
    unittest.main()
