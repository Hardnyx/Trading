import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from scripts import refresh_data as module


class PublicDownloads(unittest.TestCase):
    def test_access_rejection_is_not_retried_or_repeated_for_another_path_on_the_same_host(self):
        module.ACCESS_FAILURES.clear()
        error = urllib.error.HTTPError('https://example.test/one', 403, 'Forbidden', None, None)
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'CACHE', Path(directory)), patch.object(module.urllib.request, 'urlopen', side_effect=error) as request:
            for path in ['one', 'two']:
                with self.assertRaises(urllib.error.HTTPError):
                    module.download(f'https://example.test/{path}', path)
            self.assertEqual(request.call_count, 1)
        module.ACCESS_FAILURES.clear()

    def test_compressed_public_responses_are_decoded_before_caching(self):
        payload = b'{"value":42}'
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return gzip.compress(payload)
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'CACHE', Path(directory)), patch.object(module.urllib.request, 'urlopen', return_value=Response()):
            self.assertEqual(module.download('https://example.test/data', 'data'), payload)
            self.assertEqual((Path(directory) / 'data').read_bytes(), payload)
