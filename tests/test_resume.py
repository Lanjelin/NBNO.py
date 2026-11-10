import contextlib
import io
import json
import os
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
from web.app import app


class DownloadResumeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='nbno-resume-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'media.jpg store'
        self.root.mkdir()
        self.enterContext(patch.object(nbno, 'BASE_DIR', str(self.root)))
        self.enterContext(patch.dict(os.environ, {'DOWNLOAD_DIR': str(self.root)}))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(warnings.catch_warnings())
        buffer = io.BytesIO()
        with Image.new('RGB', (32, 48), 'white') as image:
            image.save(buffer, 'JPEG')
        self.jpeg = buffer.getvalue()
        self.requested_pages = []
        self.enterContext(patch.object(requests.Session, 'send', side_effect=self.respond))

    def respond(self, request, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response.request = request
        response.url = request.url
        if request.url.endswith('/manifest'):
            response._content = json.dumps({
                'metadata': [],
                'sequences': [{'canvases': [
                    {'@id': 'urn:fixture_' + page, 'width': 32, 'height': 48,
                     'images': [{'resource': {'service': {
                         '@id': 'https://fixture.invalid/' + page
                     }}}]}
                    for page in ('C1', '0001', '0002', 'C2')
                ]}]
            }).encode()
        else:
            self.requested_pages.append(request.url.split('/')[-5])
            response._content = self.jpeg
        return response

    def book(self, cli_mode=False):
        book = nbno.Book('digibok_123', cli_mode=cli_mode)
        self.addCleanup(book.session.close)
        return book

    def seed(self, sources, page):
        sources.mkdir(parents=True, exist_ok=True)
        path = sources / f'{page}.jpg'
        with Image.new('RGB', (16, 20), (20, 40, 60)) as image:
            image.save(path, 'JPEG')
        return path

    def assert_downloaded(self, path):
        with Image.open(path) as image:
            self.assertEqual(image.size, (32, 48))

    def test_resume_preserves_existing_pages_and_covers_in_all_layouts_and_roots(self):
        for cli_mode in (False, True):
            for relative in (False, True):
                with self.subTest(cli_mode=cli_mode, relative=relative):
                    base = self.root / f'{cli_mode}-{relative}'
                    folder = base / 'digibok_123'
                    sources = folder if cli_mode else folder / 'sources'
                    saved = [self.seed(sources, page) for page in ('C1', '0001')]
                    original = [path.read_bytes() for path in saved]
                    root = os.path.relpath(base) if relative else str(base)
                    self.requested_pages.clear()
                    with patch.object(nbno, 'BASE_DIR', root):
                        book = self.book(cli_mode=cli_mode)
                        book.download_covers()
                        self.assertTrue(book.download())
                    self.assertCountEqual(self.requested_pages, ['0002', 'C2'])
                    self.assertEqual([path.read_bytes() for path in saved], original)
                    self.assert_downloaded(sources / '0002.jpg')
                    self.assert_downloaded(sources / 'C2.jpg')

    def test_download_refreshes_files_added_and_removed_after_construction(self):
        book = self.book()
        sources = self.root / 'digibok_123' / 'sources'
        first = self.seed(sources, '0001')
        original = first.read_bytes()
        self.assertTrue(book.download())
        self.assertEqual(self.requested_pages, ['0002'])
        self.assertEqual(first.read_bytes(), original)
        first.unlink()
        self.requested_pages.clear()
        self.assertTrue(book.download())
        self.assertEqual(self.requested_pages, ['0001'])
        self.assert_downloaded(first)
        self.requested_pages.clear()
        self.assertTrue(book.download())
        self.assertTrue(book.download_skipped)
        self.assertEqual(self.requested_pages, [])

    def test_folder_switch_does_not_reuse_previous_page_selection(self):
        for cli_mode in (False, True):
            with self.subTest(cli_mode=cli_mode):
                base = self.root / str(cli_mode)
                first_folder = base / 'digibok_123'
                sources = first_folder if cli_mode else first_folder / 'sources'
                first = self.seed(sources, '0001')
                original = first.read_bytes()
                self.requested_pages.clear()
                with patch.object(nbno, 'BASE_DIR', str(base)):
                    book = self.book(cli_mode=cli_mode)
                    self.assertTrue(book.download())
                    self.assertEqual(self.requested_pages, ['0002'])
                    book.set_folder_name('New destination')
                    self.requested_pages.clear()
                    self.assertTrue(book.download())
                self.assertCountEqual(self.requested_pages, ['0001', '0002'])
                target = base / 'New destination'
                target_sources = target if cli_mode else target / 'sources'
                self.assert_downloaded(target_sources / '0001.jpg')
                self.assert_downloaded(target_sources / '0002.jpg')
                self.assertEqual(first.read_bytes(), original)

    def test_web_resume_ignores_jpegs_outside_sources_directory(self):
        folder = self.root / 'digibok_123'
        decoy = self.seed(folder, '0001')
        original = decoy.read_bytes()
        book = self.book()
        self.assertTrue(book.download())
        self.assertCountEqual(self.requested_pages, ['0001', '0002'])
        self.assertEqual(decoy.read_bytes(), original)
        self.assert_downloaded(folder / 'sources' / '0001.jpg')

    def test_empty_selection_is_not_success_because_unrelated_images_exist(self):
        self.seed(self.root / 'digibok_123' / 'sources', '9999')
        book = self.book()
        book.set_from_page(3)
        self.assertFalse(book.download())
        self.assertFalse(book.download_skipped)
        self.assertEqual(self.requested_pages, [])

    def test_cli_resume_can_build_pdf_without_downloading_existing_pages(self):
        folder = self.root / 'digibok_123'
        saved = [self.seed(folder, page) for page in ('0001', '0002')]
        original = [path.read_bytes() for path in saved]
        with patch.object(sys, 'argv', ['nbno.py', '--id', 'digibok_123', '--pdf']):
            with self.assertRaises(SystemExit) as result:
                nbno.main()
        self.assertIn(result.exception.code, (None, 0))
        self.assertEqual(self.requested_pages, [])
        self.assertEqual([path.read_bytes() for path in saved], original)
        with pikepdf.open(folder / 'digibok_123.pdf') as pdf:
            self.assertEqual(len(pdf.pages), 2)

    def test_web_custom_folder_resume_reports_only_new_pages(self):
        folder = self.root / 'Existing_book'
        saved = self.seed(folder / 'sources', '0001')
        original = saved.read_bytes()
        client = app.test_client()
        for expected in (['0002'], []):
            with self.subTest(expected=expected):
                self.requested_pages.clear()
                response = client.get('/download', query_string={
                    'id': 'digibok_123', 'name': 'Existing book'
                }, buffered=True)
                self.addCleanup(response.close)
                events = []
                for block in response.get_data(as_text=True).strip().split('\n\n'):
                    fields = dict(line.split(': ', 1) for line in block.splitlines())
                    events.append((fields['event'], json.loads(fields['data'])))
                self.assertEqual([data for event, data in events if event == 'done'], [{}])
                self.assertEqual(self.requested_pages, expected)
                progress = [data for event, data in events if event == 'progress']
                self.assertEqual([(data['page'], data['total']) for data in progress],
                                 [(1, 1)] if expected else [])
                self.assertEqual(saved.read_bytes(), original)
                self.assert_downloaded(folder / 'sources' / '0002.jpg')
        self.assertFalse((self.root / 'digibok_123').exists())


if __name__ == '__main__':
    unittest.main()
