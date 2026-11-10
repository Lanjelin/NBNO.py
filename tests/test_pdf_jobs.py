import builtins
import contextlib
import io
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import web.app as web


class PdfJobLockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='nbno-pdf-job-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'digibok_123').mkdir()
        self.enterContext(patch.dict(os.environ, {'DOWNLOAD_DIR': str(self.root)}))
        self.enterContext(patch.object(web, 'pdf_lock', threading.Lock()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.book = self.enterContext(patch.object(web, 'Book', autospec=True)).return_value
        self.book.make_pdf.return_value = True
        self.enterContext(patch.object(web.subprocess, 'run'))
        process = Mock()
        process.stdout = ['OCR finished\n']
        process.wait.return_value = 0
        self.enterContext(patch.object(web.subprocess, 'Popen', return_value=process))
        self.original_print = builtins.print
        self.release_worker = threading.Event()
        self.threads = []
        self.thread_class = threading.Thread

        def make_thread(*args, **kwargs):
            thread = self.thread_class(*args, **kwargs)
            self.threads.append(thread)
            return thread

        self.enterContext(patch.object(web.threading, 'Thread', side_effect=make_thread))
        self.addCleanup(self.finish_workers)
        self.client = web.app.test_client()

    def finish_workers(self):
        self.release_worker.set()
        try:
            for thread in self.threads:
                if thread.ident is not None:
                    thread.join(timeout=5)
                    self.assertFalse(thread.is_alive(), 'PDF worker did not terminate')
        finally:
            builtins.print = self.original_print

    def assert_next_job_succeeds(self):
        response = self.client.post('/make_pdf/digibok_123')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'success': True})
        self.assertFalse(web.pdf_lock.locked())
        self.assertIs(builtins.print, self.original_print)

    def test_missing_folder_does_not_block_later_jobs(self):
        for query in ('', '?stream=1'):
            with self.subTest(query=query):
                response = self.client.get('/make_pdf/missing' + query)
                self.assertEqual(response.status_code, 404)
                self.assert_next_job_succeeds()

    def test_streaming_setup_failures_release_lock(self):
        for owner, attribute in ((web.queue, 'Queue'), (web.os, 'makedirs'),
                                 (web, 'Response'), (web.threading, 'Thread')):
            with self.subTest(stage=attribute):
                with patch.object(owner, attribute, side_effect=RuntimeError('setup failed')):
                    response = self.client.get('/make_pdf/digibok_123?stream=1')
                self.assertEqual(response.status_code, 500)
                self.assert_next_job_succeeds()

    def test_thread_start_failure_releases_lock_and_preserves_print(self):
        # Patch the real class used by the tracking factory, not a fake worker.
        with patch.object(self.thread_class, 'start', side_effect=RuntimeError('cannot start thread')):
            response = self.client.get('/make_pdf/digibok_123?stream=1')
        self.assertEqual(response.status_code, 500)
        self.assert_next_job_succeeds()

    def test_nonstreaming_failures_release_lock(self):
        for owner, attribute in ((web, 'Book'), (self.book, 'make_pdf'),
                                 (web.subprocess, 'run')):
            with self.subTest(stage=attribute):
                with patch.object(owner, attribute, side_effect=RuntimeError('job failed')):
                    response = self.client.post('/make_pdf/digibok_123')
                self.assertEqual(response.status_code, 500)
                self.assert_next_job_succeeds()

    def test_unsuccessful_pdf_result_releases_lock(self):
        with patch.object(self.book, 'make_pdf', return_value=False):
            response = self.client.post('/make_pdf/digibok_123')
        self.assertEqual(response.status_code, 500)
        self.assert_next_job_succeeds()

    def test_streaming_worker_failures_finish_stream_and_release_lock(self):
        for owner, attribute in ((web, 'Book'), (self.book, 'make_pdf'),
                                 (web.subprocess, 'Popen')):
            with self.subTest(stage=attribute):
                with patch.object(owner, attribute, side_effect=RuntimeError('worker failed')):
                    response = self.client.get('/make_pdf/digibok_123?stream=1', buffered=True)
                self.assertEqual(response.status_code, 200)
                frames = response.get_data(as_text=True)
                self.assertIn('event: log\ndata: {"msg": "Error while building PDF:"}', frames)
                self.assertIn('event: done\ndata: {}\n\n', frames)
                self.assert_next_job_succeeds()

    def start_blocked_job(self):
        entered = threading.Event()

        def build_pdf():
            entered.set()
            if not self.release_worker.wait(timeout=5):
                raise RuntimeError('test did not release PDF worker')
            return True

        self.book.make_pdf.side_effect = build_pdf
        response = self.client.get('/make_pdf/digibok_123?stream=1', buffered=False)
        self.addCleanup(response.close)
        self.assertTrue(entered.wait(timeout=5), 'PDF worker did not start')
        return response

    def test_running_worker_excludes_other_jobs_until_stream_completes(self):
        response = self.start_blocked_job()
        rejected = self.client.post('/make_pdf/digibok_123')
        self.assertEqual(rejected.status_code, 409)
        self.release_worker.set()
        frames = response.get_data(as_text=True)
        self.assertIn('event: log\ndata: {"msg": "OCR finished"}', frames)
        self.assertIn('event: done\ndata: {}\n\n', frames)
        self.assert_next_job_succeeds()

    def test_disconnected_client_does_not_release_running_workers_lock(self):
        response = self.start_blocked_job()
        response.close()
        rejected = self.client.post('/make_pdf/digibok_123')
        self.assertEqual(rejected.status_code, 409)
        self.finish_workers()
        self.assert_next_job_succeeds()


if __name__ == '__main__':
    unittest.main()
