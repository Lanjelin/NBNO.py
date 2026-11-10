import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import requests

import nbno


class PageRetryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='nbno-page-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch.object(nbno, 'BASE_DIR', str(self.root)))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.tiles = {}
        self.colors = ((230, 30, 30), (30, 230, 30), (30, 30, 230), (230, 230, 30))
        regions = ('0,0,1024,1024', '1024,0,26,1024',
                   '0,1024,1024,6', '1024,1024,26,6')
        for region, color in zip(regions, self.colors):
            _, _, width, height = map(int, region.split(','))
            with Image.new('RGB', (width, height), color) as tile:
                buffer = io.BytesIO()
                tile.save(buffer, 'JPEG')
                self.tiles[region] = buffer.getvalue()
        self.last_region = regions[-1]
        self.requests = []
        self.outcome = lambda region, number: 200
        self.enterContext(patch.object(requests.Session, 'send', side_effect=self.respond))
        self.book = nbno.Book('digibok_123')
        self.addCleanup(self.book.session.close)
        Path(self.book.sources_dir).mkdir(parents=True)
        self.output = Path(self.book.sources_dir) / '0001.jpg'

    def respond(self, request, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response.request = request
        response.url = request.url
        if request.url.endswith('/manifest'):
            response._content = json.dumps({
                'metadata': [],
                'sequences': [{'canvases': [
                    {'@id': 'urn:fixture_' + name, 'width': 1050, 'height': 1030,
                     'images': [{'resource': {'service': {
                         '@id': 'https://fixture.invalid/' + name
                     }}}]}
                    for name in ('0001', 'C1')
                ]}]
            }).encode()
        else:
            region = request.url.split('/')[-4]
            self.requests.append(region)
            outcome = self.outcome(region, len(self.requests))
            if isinstance(outcome, Exception):
                raise outcome
            if isinstance(outcome, bytes):
                response._content = outcome
            else:
                response.status_code = outcome
                response._content = self.tiles[region] if outcome == 200 else b''
        return response

    def assert_complete_page(self):
        with Image.open(self.output) as image:
            self.assertEqual(image.size, (1050, 1030))
            for point, expected in zip(((512, 512), (1037, 512), (512, 1027), (1037, 1027)),
                                       self.colors):
                pixel = image.getpixel(point)
                self.assertTrue(all(abs(actual - target) <= 5
                                    for actual, target in zip(pixel, expected)), (point, pixel))

    def test_persistent_http_tile_failure_stops_and_preserves_existing_page(self):
        self.outcome = lambda region, number: 404 if region == self.last_region else 200
        self.output.write_bytes(b'existing page')
        self.assertFalse(self.book.download())
        self.assertEqual(len(self.requests), 12)
        self.assertEqual(self.output.read_bytes(), b'existing page')

    def test_persistent_invalid_tile_stops_without_creating_page(self):
        self.outcome = lambda region, number: b'invalid JPEG' if region == self.last_region else 200
        self.assertEqual(self.book.download_page('0001'), (False, 200))
        self.assertEqual(len(self.requests), 12)
        self.assertFalse(self.output.exists())

    def test_transient_failure_can_recover_on_final_attempt(self):
        self.outcome = lambda region, number: (
            404 if region == self.last_region and number <= 8 else 200
        )
        self.assertEqual(self.book.download_page('0001'), (True, 200))
        self.assertEqual(len(self.requests), 12)
        self.assert_complete_page()

    def test_partial_cover_is_skipped_without_page_retries(self):
        self.outcome = lambda region, number: 404 if region == self.last_region else 200
        self.assertEqual(self.book.download_page('C1'), (True, 200))
        self.assertEqual(len(self.requests), 4)
        self.assertFalse((Path(self.book.sources_dir) / 'C1.jpg').exists())

    def test_page_without_any_tiles_fails_without_page_retries(self):
        self.outcome = lambda region, number: 404
        self.assertEqual(self.book.download_page('0001'), (False, 200))
        self.assertEqual(len(self.requests), 4)
        self.assertFalse(self.output.exists())

    def test_forbidden_tile_stops_immediately_after_previous_successes(self):
        self.outcome = lambda region, number: 403 if number == 2 else 200
        self.assertEqual(self.book.download_page('0001'), (False, 403))
        self.assertEqual(len(self.requests), 2)
        self.assertFalse(self.output.exists())

    def test_transport_failure_after_success_is_not_mistaken_for_old_response(self):
        for error in (requests.Timeout('offline timeout'), requests.ConnectionError('offline connection')):
            with self.subTest(error=type(error).__name__):
                self.requests.clear()
                self.outcome = lambda region, number: error if number == 2 else 200
                self.assertEqual(self.book.download_page('0001'), (False, 408))
                self.assertEqual(len(self.requests), 2)
                self.assertFalse(self.output.exists())

    def test_retry_and_save_failure_release_opened_tile_images(self):
        opened = []
        open_image = Image.open

        def track_image(*args, **kwargs):
            image = open_image(*args, **kwargs)
            opened.append(image)
            return image

        self.outcome = lambda region, number: (
            404 if region == self.last_region and number <= 4 else 200
        )
        with patch.object(nbno.Image, 'open', side_effect=track_image), \
                patch.object(Image.Image, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.book.download_page('0001')
        self.assertEqual(len(self.requests), 8)
        for image in opened:
            with self.assertRaises(ValueError):
                image.getpixel((0, 0))
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
