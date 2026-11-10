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


class MapDownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='nbno-map-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch.object(nbno, 'BASE_DIR', str(self.root)))
        self.enterContext(patch.dict(os.environ, {'DOWNLOAD_DIR': str(self.root)}))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(warnings.catch_warnings())
        # Deliberately not manifest order, and not consecutive sheet numbers.
        self.map_sizes = {'0003_0001': (80, 40), '0001_0002': (60, 40), '0001_0001': (40, 60)}
        self.legacy_sizes = {
            'C3': (20, 90), '0010': (90, 30), 'I3': (20, 60), 'C1': (20, 30),
            '0002': (30, 60), 'I1': (20, 40), 'C2': (20, 80), '0007': (60, 30)
        }
        self.requested = []
        self.enterContext(patch.object(requests.Session, 'send', side_effect=self.respond))
        self.enterContext(patch.object(web.subprocess, 'run', return_value=SimpleNamespace(
            stdout='List of available languages (1):\neng\n'
        )))
        self.client = web.app.test_client()

    def sizes(self, kind):
        return self.map_sizes if kind == 'digikart' else self.legacy_sizes

    def respond(self, request, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response.request = request
        response.url = request.url
        if request.url.endswith('/manifest'):
            kind = request.url.rsplit('_', 2)[-2]
            sizes = self.sizes(kind)
            response._content = json.dumps({
                'label': 'Offline kart',
                'metadata': [{'label': 'Tittel', 'value': 'Offline kart'}],
                'sequences': [{'canvases': [
                    {'@id': 'urn:fixture_' + page + ('_00' if kind == 'digavis' else ''),
                     'width': size[0], 'height': size[1],
                     'images': [{'resource': {'service': {
                         '@id': f'https://fixture.invalid/{kind}/{page}'
                     }}}]}
                    for page, size in sizes.items()
                ]}]
            }).encode()
        else:
            kind, page = request.url.split('/')[-6:-4]
            self.requested.append((kind, page))
            buffer = io.BytesIO()
            with Image.new('RGB', self.sizes(kind)[page], 'white') as image:
                image.save(buffer, 'JPEG')
            response._content = buffer.getvalue()
        return response

    def book(self, kind='digikart'):
        book = nbno.Book(kind + '_123')
        self.addCleanup(book.session.close)
        book.max_workers = 1
        return book

    def assert_pdf_order(self, path, sizes):
        with pikepdf.open(path) as document:
            self.assertEqual(len(document.pages), len(sizes))
            for page, (width, height) in zip(document.pages, sizes):
                x0, y0, x1, y1 = map(float, page.MediaBox)
                self.assertAlmostEqual((x1 - x0) / (y1 - y0), width / height)

    def assert_map_files(self, sources, names):
        self.assertEqual({path.name for path in sources.glob('*.jpg')},
                         {name + '.jpg' for name in names})
        for name in names:
            with Image.open(sources / (name + '.jpg')) as image:
                self.assertEqual(image.size, self.map_sizes[name])

    def test_map_canvases_download_with_or_without_cover_option_and_resume(self):
        expected = ['0001_0001', '0001_0002', '0003_0001']
        for covers in (False, True):
            with self.subTest(covers=covers):
                book = self.book()
                book.set_folder_name('maps-' + str(covers))
                if covers:
                    book.download_covers()
                self.requested.clear()
                self.assertTrue(book.download())
                self.assertEqual(self.requested, [('digikart', page) for page in expected])
                folder = self.root / ('maps-' + str(covers))
                self.assert_map_files(folder / 'sources', expected)
                meta = json.loads((folder / 'metadata' / '.nbno_meta.json').read_text())
                self.assertEqual(meta['pages'], 3)
                self.assertTrue(book.make_pdf())
                self.assert_pdf_order(folder / 'pdf' / (folder.name + '.pdf'),
                                      [self.map_sizes[name] for name in expected])
                self.requested.clear()
                self.assertTrue(book.download())
                self.assertTrue(book.download_skipped)
                self.assertEqual(self.requested, [])

    def test_map_bounds_use_stable_positions_independent_of_setter_order(self):
        for stop_first in (False, True):
            with self.subTest(stop_first=stop_first):
                book = self.book()
                book.set_folder_name('bounds-' + str(stop_first))
                if stop_first:
                    book.set_to_page(2)
                    book.set_from_page(2)
                else:
                    book.set_from_page(2)
                    book.set_to_page(2)
                self.requested.clear()
                self.assertTrue(book.download())
                self.assertEqual(self.requested, [('digikart', '0001_0002')])
                self.assert_map_files(self.root / ('bounds-' + str(stop_first)) / 'sources',
                                      ['0001_0002'])

    def test_cli_map_bounds_and_pdf_work_with_cover_flag(self):
        with patch.object(sys, 'argv', [
            'nbno.py', '--id', 'digikart_123', '--cover', '--pdf', '--start', '2', '--stop', '3'
        ]):
            with self.assertRaises(SystemExit) as result:
                nbno.main()
        self.assertIn(result.exception.code, (None, 0))
        folder = self.root / 'digikart_123'
        expected = ['0001_0002', '0003_0001']
        self.assertCountEqual(self.requested, [('digikart', name) for name in expected])
        self.assert_map_files(folder, expected)
        self.assert_pdf_order(folder / 'digikart_123.pdf', [self.map_sizes[name] for name in expected])

    def test_book_and_newspaper_bounds_keep_page_numbers_and_cover_order(self):
        expected = ['C1', 'I1', '0007', '0010', 'I3', 'C2', 'C3']
        for kind in ('digibok', 'digavis'):
            with self.subTest(kind=kind):
                book = self.book(kind)
                book.set_from_page(7)
                book.set_to_page(10)
                book.download_covers()
                self.requested.clear()
                self.assertTrue(book.download())
                self.assertEqual(self.requested, [(kind, name) for name in expected])
                self.assertTrue(book.make_pdf())
                folder = self.root / (kind + '_123')
                self.assert_pdf_order(folder / 'pdf' / (folder.name + '.pdf'),
                                      [self.legacy_sizes[name] for name in expected])
                response = self.client.get('/pages/' + folder.name + '?include_cover=true')
                self.addCleanup(response.close)
                self.assertEqual(response.get_json(), [name + '.jpg' for name in expected])

    def test_web_map_preview_gallery_pdf_and_page_list_use_same_order(self):
        response = self.client.get('/preview?id=digikart_123')
        self.addCleanup(response.close)
        preview = response.get_json()
        self.assertEqual(preview['pages'], 3)
        self.assertEqual(preview['preview_page'], '0001_0001')
        self.assertEqual(preview['thumbnail'],
                         'https://fixture.invalid/digikart/0001_0001/full/!200,200/0/native.jpg')
        downloaded = self.client.get('/download', query_string={
            'id': 'digikart_123', 'name': 'Downloaded maps', 'cover': 'true'
        }, buffered=True)
        self.addCleanup(downloaded.close)
        self.assertIn('event: done\ndata: {}\n\n', downloaded.get_data(as_text=True))
        expected = ['0001_0001', '0001_0002', '0003_0001']
        folder = self.root / 'Downloaded_maps'
        self.assert_map_files(folder / 'sources', expected)
        made = self.client.post('/make_pdf/Downloaded_maps?include_cover=true')
        self.addCleanup(made.close)
        self.assertEqual(made.get_json(), {'success': True})
        pdf = folder / 'pdf' / 'Downloaded_maps.pdf'
        self.assert_pdf_order(pdf, [self.map_sizes[name] for name in expected])
        for flag in ('false', 'true'):
            response = self.client.get('/pages/Downloaded_maps?include_cover=' + flag)
            self.addCleanup(response.close)
            self.assertEqual(response.get_json(), [name + '.jpg' for name in expected])
        gallery = self.client.get('/')
        self.addCleanup(gallery.close)
        html = gallery.get_data(as_text=True)
        self.assertIn('src="/files/Downloaded_maps/sources/0001_0001.jpg?w=500"', html)
        self.assertIn('href="/files/Downloaded_maps/pdf/Downloaded_maps.pdf"', html)
        thumb = self.client.get('/files/Downloaded_maps/sources/0001_0001.jpg?w=20')
        self.addCleanup(thumb.close)
        with Image.open(io.BytesIO(thumb.data)) as image:
            self.assertEqual(image.size, (20, 30))

    def test_map_pages_stay_between_front_and_back_covers_in_pdf_and_previews(self):
        book = self.book()
        self.assertTrue(book.download())
        folder = self.root / 'digikart_123'
        for name in ('C1', 'I1', 'I3', 'C2', 'C3'):
            with Image.new('RGB', self.legacy_sizes[name], 'white') as image:
                image.save(folder / 'sources' / (name + '.jpg'), 'JPEG')
        expected = ['C1', 'I1', '0001_0001', '0001_0002', '0003_0001', 'I3', 'C2', 'C3']
        book.set_include_cover(True)
        self.assertTrue(book.make_pdf())
        sizes = [self.map_sizes[name] if name in self.map_sizes else self.legacy_sizes[name]
                 for name in expected]
        self.assert_pdf_order(folder / 'pdf' / 'digikart_123.pdf', sizes)
        response = self.client.get('/pages/digikart_123?include_cover=true')
        self.addCleanup(response.close)
        self.assertEqual(response.get_json(), [name + '.jpg' for name in expected])


if __name__ == '__main__':
    unittest.main()
