import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings

from PIL import Image
import pikepdf
import requests

import nbno


class PdfPreservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='nbno-pdf-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(warnings.catch_warnings())
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(patch.object(nbno, 'BASE_DIR', str(self.root)))
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({
            'metadata': [], 'sequences': [{'canvases': []}]
        }).encode()
        with patch.object(requests.Session, 'send', return_value=response):
            self.book = nbno.Book('digibok_123')
        self.addCleanup(self.book.session.close)
        self.sources = Path(self.book.sources_dir)
        self.sources.mkdir(parents=True)
        self.pdf_dir = Path(self.book.pdf_dir)
        self.pdf_dir.mkdir()
        self.output = self.pdf_dir / 'digibok_123.pdf'
        with Image.new('RGB', (10, 10), 'black') as image:
            image.save(self.output, 'PDF')
        self.original = self.output.read_bytes()
        for name, size in (('0001', (40, 60)), ('0002', (80, 20))):
            with Image.new('RGB', size, 'white') as image:
                image.save(self.sources / f'{name}.jpg')

    def assert_original_preserved(self):
        self.assertEqual(self.output.read_bytes(), self.original)
        self.assertEqual(set(self.pdf_dir.iterdir()), {self.output})

    def assert_replaced_with_expected_pages(self):
        with pikepdf.open(self.output) as pdf:
            self.assertEqual(len(pdf.pages), 2)
            for page, expected_ratio in zip(pdf.pages, (40 / 60, 80 / 20)):
                x0, y0, x1, y1 = map(float, page.MediaBox)
                self.assertAlmostEqual((x1 - x0) / (y1 - y0), expected_ratio)
        self.assertEqual(set(self.pdf_dir.iterdir()), {self.output})

    def test_img2pdf_success_replaces_existing_pdf(self):
        self.assertTrue(self.book.make_pdf())
        self.assert_replaced_with_expected_pages()

    def test_pillow_success_replaces_existing_pdf_without_img2pdf(self):
        with patch.dict(sys.modules, {'img2pdf': None}):
            self.assertTrue(self.book.make_pdf())
        self.assert_replaced_with_expected_pages()

    def test_corrupt_source_and_failed_recovery_preserve_existing_pdf(self):
        (self.sources / '0001.jpg').write_bytes(b'corrupt source image')
        with patch.object(self.book, 'download_page', return_value=(False, 403)):
            self.assertFalse(self.book.make_pdf())
        self.assert_original_preserved()

    def test_pillow_decode_failure_preserves_existing_pdf(self):
        page = self.sources / '0002.jpg'
        page.write_bytes(page.read_bytes()[:-10])
        with patch.dict(sys.modules, {'img2pdf': None}):
            self.assertFalse(self.book.make_pdf())
        self.assert_original_preserved()

    def test_replacement_failure_preserves_existing_pdf(self):
        with patch.object(nbno.os, 'replace', side_effect=PermissionError('read-only destination')):
            self.assertFalse(self.book.make_pdf())
        self.assert_original_preserved()


if __name__ == '__main__':
    unittest.main()
