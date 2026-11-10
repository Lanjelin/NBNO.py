import builtins
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
import requests

import nbno
import web.app as web


class JobLoggingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='nbno-logging-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.enterContext(patch.dict(os.environ, {'DOWNLOAD_DIR': str(self.root)}))
        self.enterContext(patch.object(nbno, 'BASE_DIR', str(self.root)))
        self.enterContext(patch.object(web, 'pdf_lock', threading.Lock()))
        self.console = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.original_print = builtins.print
        self.entered = {mid: threading.Event() for mid in ('111', '222', '333')}
        self.release = {mid: threading.Event() for mid in self.entered}
        self.threads = []
        thread_class = threading.Thread

        def make_thread(*args, **kwargs):
            thread = thread_class(*args, **kwargs)
            self.threads.append(thread)
            return thread

        self.enterContext(patch.object(web.threading, 'Thread', side_effect=make_thread))
        self.enterContext(patch.object(requests.Session, 'send', side_effect=self.respond))
        self.enterContext(patch.object(web.subprocess, 'Popen', side_effect=self.start_ocr))
        self.ocr_failure = False
        self.addCleanup(self.finish_workers)
        buffer = io.BytesIO()
        with Image.new('RGB', (24, 32), 'white') as image:
            image.save(buffer, 'JPEG')
        self.jpeg = buffer.getvalue()
        sources = self.root / 'digibok_333' / 'sources'
        sources.mkdir(parents=True)
        (sources / '0001.jpg').write_bytes(self.jpeg)
        self.client = web.app.test_client()

    def finish_workers(self):
        for event in self.release.values():
            event.set()
        for thread in self.threads:
            if thread.ident is not None:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive(), 'job worker did not terminate')

    def respond(self, request, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response.request = request
        response.url = request.url
        if request.url.endswith('/manifest'):
            mid = request.url.rsplit('_', 1)[-1].split('/')[0]
            if mid == '444':
                raise requests.ConnectionError('private manifest failure 444')
            pages = 2 if mid == '222' else 1
            response._content = json.dumps({
                'metadata': [],
                'sequences': [{'canvases': [
                    {'@id': f'urn:fixture_{page:04}', 'width': 24, 'height': 32,
                     'images': [{'resource': {'service': {
                         '@id': f'https://fixture.invalid/{mid}/{page:04}'
                     }}}]}
                    for page in range(1, pages + 1)
                ]}]
            }).encode()
        else:
            mid = request.url.split('/')[3]
            self.entered[mid].set()
            if not self.release[mid].wait(timeout=5):
                raise RuntimeError('test did not release image request')
            response._content = self.jpeg
        return response

    def start_ocr(self, *args, **kwargs):
        if self.ocr_failure:
            raise OSError('offline OCR launch failure')

        def lines():
            self.entered['333'].set()
            if not self.release['333'].wait(timeout=5):
                raise RuntimeError('test did not release OCR output')
            yield 'private OCR output 333\n'

        return SimpleNamespace(stdout=lines(), wait=lambda: 0)

    def start_download(self, mid):
        response = self.client.get('/download?id=digibok_' + mid, buffered=False)
        self.addCleanup(response.close)
        self.assertTrue(self.entered[mid].wait(timeout=5), 'download did not reach image request')
        return response

    def frames(self, response):
        self.assertEqual(response.status_code, 200)
        events = []
        for block in response.get_data(as_text=True).strip().split('\n\n'):
            fields = dict(line.split(': ', 1) for line in block.splitlines())
            events.append((fields['event'], json.loads(fields['data'])))
        self.assertEqual([data for event, data in events if event == 'done'], [{}])
        return events

    def test_overlapping_downloads_keep_progress_and_console_output_isolated(self):
        first = self.start_download('111')
        second = self.start_download('222')
        self.assertIs(builtins.print, self.original_print)
        print('unrelated console output')
        self.release['111'].set()
        first_events = self.frames(first)
        self.assertIs(builtins.print, self.original_print)
        self.assertFalse(self.release['222'].is_set())
        self.release['222'].set()
        second_events = self.frames(second)
        self.assertEqual({data['total'] for event, data in first_events if event == 'progress'}, {1})
        self.assertEqual({data['total'] for event, data in second_events if event == 'progress'}, {2})
        for own, other, events in (('111', '222', first_events), ('222', '111', second_events)):
            text = json.dumps(events)
            self.assertIn('digibok_' + own, text)
            self.assertNotIn('digibok_' + other, text)
            self.assertNotIn('unrelated console output', text)
        self.assertIs(builtins.print, self.original_print)
        self.assertEqual(self.console.getvalue(), 'unrelated console output\n')
        log = (self.root / 'logs' / 'pdf_ocr.log').read_text()
        self.assertIn('digibok_111', log)
        self.assertIn('digibok_222', log)
        self.assertNotIn('unrelated console output', log)

    def test_pdf_and_download_keep_converter_and_ocr_output_in_own_stream(self):
        pdf = self.client.get('/make_pdf/digibok_333?stream=1', buffered=False)
        self.addCleanup(pdf.close)
        self.assertTrue(self.entered['333'].wait(timeout=5), 'PDF did not reach OCR')
        download = self.start_download('111')
        self.assertIs(builtins.print, self.original_print)
        self.release['333'].set()
        pdf_events = self.frames(pdf)
        self.assertFalse(web.pdf_lock.locked())
        self.assertIs(builtins.print, self.original_print)
        self.release['111'].set()
        download_events = self.frames(download)
        pdf_text = json.dumps(pdf_events)
        download_text = json.dumps(download_events)
        self.assertIn('digibok_333.pdf', pdf_text)
        self.assertIn('private OCR output 333', pdf_text)
        self.assertNotIn('digibok_111', pdf_text)
        self.assertNotIn('digibok_333.pdf', download_text)
        self.assertNotIn('private OCR output 333', download_text)
        self.assertEqual([event for event, _ in pdf_events if event == 'progress'], [])
        self.assertEqual([data['page'] for event, data in download_events if event == 'progress'], [1])
        self.assertTrue((self.root / 'digibok_333' / 'pdf' / 'digibok_333.pdf').is_file())
        self.assertEqual(self.console.getvalue(), '')

    def test_manifest_error_is_scoped_even_during_book_construction(self):
        download = self.start_download('111')
        failed = self.client.get('/download?id=digibok_444', buffered=True)
        self.assertIn('private manifest failure 444', json.dumps(self.frames(failed)))
        self.assertIs(builtins.print, self.original_print)
        self.release['111'].set()
        self.assertNotIn('private manifest failure 444', json.dumps(self.frames(download)))
        self.assertEqual(self.console.getvalue(), '')

    def test_worker_exception_reaches_own_stream_without_affecting_other_job(self):
        download = self.start_download('111')
        self.ocr_failure = True
        failed = self.client.get('/make_pdf/digibok_333?stream=1', buffered=True)
        self.assertIn('OSError: offline OCR launch failure', json.dumps(self.frames(failed)))
        self.assertFalse(web.pdf_lock.locked())
        self.assertIs(builtins.print, self.original_print)
        self.release['111'].set()
        self.assertNotIn('offline OCR launch failure', json.dumps(self.frames(download)))
        self.assertEqual(self.console.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
