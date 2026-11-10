import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web.app import app


class DeleteBookTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='nbno-delete-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.downloads = self.root / 'data'
        self.downloads.mkdir()
        self.book = self.downloads / 'digibok_123'
        (self.book / 'sources').mkdir(parents=True)
        (self.book / 'sources' / '0001.jpg').write_bytes(b'book page')
        self.sibling = self.root / 'outside.txt'
        self.sibling.write_bytes(b'outside collection')
        self.other = self.downloads / 'digibok_456'
        self.other.mkdir()
        (self.other / 'keep.txt').write_bytes(b'other book')
        self.enterContext(patch.dict(os.environ, {'DOWNLOAD_DIR': str(self.downloads)}))
        self.client = app.test_client()

    def assert_collection_preserved(self):
        self.assertEqual(self.sibling.read_bytes(), b'outside collection')
        self.assertEqual((self.book / 'sources' / '0001.jpg').read_bytes(), b'book page')
        self.assertEqual((self.other / 'keep.txt').read_bytes(), b'other book')

    def test_rejects_collection_root_and_parent(self):
        for name in ('.', '..', '%2e', '%2e%2e'):
            with self.subTest(name=name):
                response = self.client.delete(f'/delete/{name}')
                self.assertEqual(response.status_code, 400)
                self.assert_collection_preserved()

    def test_rejects_symlinks_to_outside_root_and_other_books(self):
        for name, target in (('outside-link', self.root),
                             ('root-link', self.downloads),
                             ('book-link', self.other)):
            with self.subTest(name=name):
                link = self.downloads / name
                link.symlink_to(target, target_is_directory=True)
                response = self.client.delete(f'/delete/{name}')
                self.assertEqual(response.status_code, 400)
                self.assertTrue(link.is_symlink())
                self.assert_collection_preserved()

    def test_deletes_only_the_requested_book(self):
        response = self.client.delete('/delete/digibok_123')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(self.book.exists())
        self.assertEqual(self.sibling.read_bytes(), b'outside collection')
        self.assertEqual((self.other / 'keep.txt').read_bytes(), b'other book')

    def test_allows_a_symlinked_download_root(self):
        alias = self.root / 'collection-link'
        alias.symlink_to(self.downloads, target_is_directory=True)
        with patch.dict(os.environ, {'DOWNLOAD_DIR': str(alias)}):
            response = self.client.delete('/delete/digibok_123')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(self.book.exists())
        self.assertTrue(alias.is_symlink())
        self.assertEqual(self.sibling.read_bytes(), b'outside collection')
        self.assertEqual((self.other / 'keep.txt').read_bytes(), b'other book')


if __name__ == '__main__':
    unittest.main()
