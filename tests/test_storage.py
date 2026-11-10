import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings

from PIL import Image
import pikepdf
import requests

import nbno
import web.app as web


class StoragePathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='nbno-storage-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch.object(nbno, 'BASE_DIR', str(self.root)))
        self.enterContext(patch.dict(os.environ, {'DOWNLOAD_DIR': str(self.root)}))
        self.enterContext(warnings.catch_warnings())
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        buffer = io.BytesIO()
        with Image.new('RGB', (32, 48), 'white') as image:
            image.save(buffer, 'JPEG')
        self.jpeg = buffer.getvalue()
        self.enterContext(patch.object(requests.Session, 'send', side_effect=self.respond))
        self.enterContext(patch.object(web.subprocess, 'run', return_value=SimpleNamespace(
            stdout='List of available languages (1):\neng\n'
        )))
        self.enterContext(patch.object(web.subprocess, 'Popen', return_value=SimpleNamespace(
            stdout=['Offline OCR boundary\n'], wait=lambda: 0
        )))
        self.client = web.app.test_client()

    def respond(self, request, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response.request = request
        response.url = request.url
        if request.url.endswith('/manifest'):
            response._content = json.dumps({
                'label': 'Bok med tittel',
                'metadata': [{'label': 'Tittel', 'value': 'Bok med tittel'}],
                'sequences': [{'canvases': [{
                    '@id': 'urn:fixture_0001', 'width': 32, 'height': 48,
                    'images': [{'resource': {'service': {
                        '@id': 'https://fixture.invalid/image'
                    }}}]
                }]}]
            }).encode()
        else:
            response._content = self.jpeg
        return response

    def assert_page_and_pdf(self, source, pdf):
        with Image.open(source) as image:
            self.assertEqual(image.size, (32, 48))
        with pikepdf.open(pdf) as document:
            self.assertEqual(len(document.pages), 1)
            x0, y0, x1, y1 = map(float, document.pages[0].MediaBox)
            self.assertAlmostEqual((x1 - x0) / (y1 - y0), 32 / 48)

    def download_custom_book(self):
        response = self.client.get('/download', query_string={
            'id': 'digibok_123', 'name': 'Min bok'
        }, buffered=True)
        self.addCleanup(response.close)
        self.assertIn('event: done\ndata: {}\n\n', response.get_data(as_text=True))
        folder = self.root / 'Min_bok'
        meta = json.loads((folder / 'metadata' / '.nbno_meta.json').read_text())
        self.assertEqual(meta['orig'], 'digibok_123')
        self.assertEqual(meta['custom_title'], 'Min bok')
        self.assertEqual((folder / 'metadata' / '.nbno_id').read_text(), 'digibok_123')
        self.assertFalse((self.root / 'digibok_123').exists())
        return folder

    def assert_gallery_and_files(self, folder):
        pdf = folder / 'pdf' / 'Min_bok.pdf'
        self.assert_page_and_pdf(folder / 'sources' / '0001.jpg', pdf)
        gallery = self.client.get('/')
        self.addCleanup(gallery.close)
        self.assertEqual(gallery.status_code, 200)
        self.assertIn('href="/files/Min_bok/pdf/Min_bok.pdf"', gallery.get_data(as_text=True))
        pages = self.client.get('/pages/Min_bok')
        self.addCleanup(pages.close)
        self.assertEqual(pages.get_json(), ['0001.jpg'])
        served = self.client.get('/files/Min_bok/pdf/Min_bok.pdf')
        self.addCleanup(served.close)
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.data, pdf.read_bytes())
        thumbnail = self.client.get('/files/Min_bok/sources/0001.jpg?w=16')
        self.addCleanup(thumbnail.close)
        with Image.open(io.BytesIO(thumbnail.data)) as image:
            self.assertEqual(image.size, (16, 24))
        self.assertFalse((self.root / 'digibok_123').exists())

    def test_cli_title_option_uses_flat_title_directory(self):
        with patch.object(sys, 'argv', ['nbno.py', '--id', 'digibok_123', '--title', '--pdf']):
            with self.assertRaises(SystemExit) as result:
                nbno.main()
        self.assertIn(result.exception.code, (None, 0))
        folder = self.root / 'Bok med tittel'
        self.assert_page_and_pdf(folder / '0001.jpg', folder / 'Bok med tittel.pdf')
        self.assertEqual({path.name for path in folder.iterdir()}, {'0001.jpg', 'Bok med tittel.pdf'})
        self.assertFalse((self.root / 'digibok_123').exists())

    def test_custom_download_and_nonstream_pdf_share_gallery_paths(self):
        folder = self.download_custom_book()
        response = self.client.post('/make_pdf/Min_bok')
        self.addCleanup(response.close)
        self.assertEqual(response.get_json(), {'success': True})
        self.assert_gallery_and_files(folder)

    def test_custom_download_and_streaming_pdf_share_gallery_paths(self):
        folder = self.download_custom_book()
        response = self.client.get('/make_pdf/Min_bok?stream=1', buffered=True)
        self.addCleanup(response.close)
        self.assertIn('event: done\ndata: {}\n\n', response.get_data(as_text=True))
        self.assert_gallery_and_files(folder)

    def test_explicit_folder_path_redirects_future_output_without_moving_files(self):
        book = nbno.Book('digibok_123')
        self.addCleanup(book.session.close)
        self.assertTrue(book.download())
        original = self.root / 'digibok_123' / 'sources' / '0001.jpg'
        original_bytes = original.read_bytes()
        target = self.root / 'Selected output'
        book.set_folder_path(str(target) + os.path.sep)
        self.assertTrue(book.download())
        self.assertTrue(book.make_pdf())
        self.assert_page_and_pdf(target / 'sources' / '0001.jpg',
                                 target / 'pdf' / 'digibok_123.pdf')
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertEqual((target / 'metadata' / '.nbno_id').read_text(), 'digibok_123')
        self.assertFalse((self.root / 'digibok_123' / 'pdf' / 'digibok_123.pdf').exists())


if __name__ == '__main__':
    unittest.main()
