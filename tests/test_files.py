import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from web.app import app


class FileContainmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='nbno-files-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.downloads = self.root / 'data'
        self.book = self.downloads / 'digibok_123'
        (self.book / 'sources').mkdir(parents=True)
        (self.book / 'pdf').mkdir()
        self.jpeg = self.book / 'sources' / '0001.jpg'
        self.pdf = self.book / 'pdf' / 'digibok_123.pdf'
        with Image.new('RGB', (12, 8), (70, 130, 180)) as image:
            image.save(self.jpeg, 'JPEG')
            image.save(self.pdf, 'PDF')
        # A shared pathname prefix must not make a sibling part of the root.
        self.outside = self.root / 'data-other'
        self.outside.mkdir()
        with Image.new('RGB', (12, 8), 'red') as image:
            image.save(self.outside / 'secret.jpg', 'JPEG')
            image.save(self.outside / 'secret.pdf', 'PDF')
        self.enterContext(patch.dict(os.environ, {'DOWNLOAD_DIR': str(self.downloads)}))
        self.client = app.test_client()

    def get(self, path):
        response = self.client.get(path)
        self.addCleanup(response.close)
        return response

    def assert_thumbnail(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/jpeg')
        with Image.open(io.BytesIO(response.data)) as image:
            self.assertEqual(image.size, (6, 4))
            pixel = image.getpixel((3, 2))
            self.assertTrue(all(abs(actual - expected) <= 3
                                for actual, expected in zip(pixel, (70, 130, 180))))

    def test_original_jpeg_and_pdf_are_served(self):
        for subpath, source, mimetype in (
                ('digibok_123/sources/0001.jpg', self.jpeg, 'image/jpeg'),
                ('digibok_123/pdf/digibok_123.pdf', self.pdf, 'application/pdf')):
            with self.subTest(subpath=subpath):
                response = self.get('/files/' + subpath)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, mimetype)
                self.assertEqual(response.data, source.read_bytes())

    def test_in_collection_jpeg_is_resized(self):
        self.assert_thumbnail(self.get('/files/digibok_123/sources/0001.jpg?w=6'))

    def test_parent_traversal_is_rejected_for_resizing_and_original_files(self):
        for prefix in ('../data-other/', '%2e%2e/data-other/',
                       '%2e%2e%2fdata-other%2f',
                       'digibok_123/sources/../../../data-other/'):
            for filename, query in (('secret.jpg', ''), ('secret.jpg', '?w=6'), ('secret.pdf', '')):
                with self.subTest(prefix=prefix, filename=filename, query=query):
                    response = self.get('/files/' + prefix + filename + query)
                    self.assertEqual(response.status_code, 404)

    def test_file_and_directory_symlink_escapes_are_rejected(self):
        (self.downloads / 'escape.jpg').symlink_to(self.outside / 'secret.jpg')
        (self.downloads / 'escape.pdf').symlink_to(self.outside / 'secret.pdf')
        (self.downloads / 'outside').symlink_to(self.outside, target_is_directory=True)
        for subpath in ('escape.jpg', 'escape.jpg?w=6', 'escape.pdf',
                        'outside/secret.jpg', 'outside/secret.jpg?w=6', 'outside/secret.pdf'):
            with self.subTest(subpath=subpath):
                self.assertEqual(self.get('/files/' + subpath).status_code, 404)

    def test_internal_file_and_directory_symlinks_remain_usable(self):
        (self.downloads / 'alias.jpg').symlink_to(self.jpeg)
        (self.downloads / 'alias.pdf').symlink_to(self.pdf)
        (self.downloads / 'alias-book').symlink_to(self.book, target_is_directory=True)
        for subpath in ('alias.jpg?w=6', 'alias-book/sources/0001.jpg?w=6'):
            with self.subTest(subpath=subpath):
                self.assert_thumbnail(self.get('/files/' + subpath))
        response = self.get('/files/alias.pdf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.pdf.read_bytes())

    def test_symlinked_and_relative_download_roots_work(self):
        alias = self.root / 'collection-link'
        alias.symlink_to(self.downloads, target_is_directory=True)
        for root in (str(alias), os.path.relpath(self.downloads)):
            with self.subTest(root=root), patch.dict(os.environ, {'DOWNLOAD_DIR': root}):
                self.assert_thumbnail(self.get('/files/digibok_123/sources/0001.jpg?w=6'))
                response = self.get('/files/digibok_123/pdf/digibok_123.pdf')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, self.pdf.read_bytes())
                self.assertEqual(self.get('/files/../data-other/secret.jpg?w=6').status_code, 404)

    def test_missing_files_directories_and_malformed_paths_are_not_served(self):
        for subpath in ('missing.jpg?w=6', 'digibok_123/sources', '%00.jpg?w=6'):
            with self.subTest(subpath=subpath):
                self.assertEqual(self.get('/files/' + subpath).status_code, 404)


if __name__ == '__main__':
    unittest.main()
