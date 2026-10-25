import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from scripts import refresh_data as module


def fixture():
    return {
        'generated_at': '2026-10-24T23:30:00+00:00',
        'requested_as_of': '2026-10-24',
        'price_as_of': '2026-10-23',
        'assets': [{'symbol': 'TEST', 'price': 10, 'price_date': '2026-10-23',
                    'history': [{'date': '2026-10-22', 'close': 9, 'adj_close': 9},
                                {'date': '2026-10-23', 'close': 10, 'adj_close': 10}],
                    'financials': {'eps': {'value': 1, 'filed': '2026-10-20'}}}],
        'macro': [{'id': 'DGS3MO', 'value': 4, 'date': '2026-10-23', 'history': [{'value': 4}]}],
        'sources': [], 'errors': [],
    }


class ObservationArchive(unittest.TestCase):
    def test_archive_keeps_observed_fundamentals_and_quote_without_repeating_histories(self):
        data = fixture()
        before = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as directory:
            path = module.archive_observation(data, directory)
            saved = json.loads(path.read_text())
            self.assertEqual(saved['collection_mode'], 'current')
            self.assertEqual(saved['assets'][0]['quote']['close'], 10)
            self.assertEqual(saved['assets'][0]['financials']['eps']['filed'], '2026-10-20')
            self.assertNotIn('history', saved['assets'][0])
            self.assertNotIn('history', saved['macro'][0])
            self.assertEqual(len(saved['source_snapshot_sha256']), 64)
        self.assertEqual(data, before)


    def test_public_snapshot_has_matching_deterministic_gzip_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "market.json"
            private = Path(directory) / "research" / "latest.json"
            snapshot = fixture()
            module.write_snapshot(snapshot, destination, private)
            compressed = destination.with_suffix(".json.gz")
            self.assertTrue(compressed.exists())
            self.assertEqual(gzip.decompress(compressed.read_bytes()), destination.read_bytes())
            before = compressed.read_bytes()
            module.write_snapshot(snapshot, destination, private)
            self.assertEqual(before, compressed.read_bytes())
            self.assertNotIn("analyst_estimates", destination.read_text())

    def test_existing_capture_cannot_be_rewritten_with_revised_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            data = fixture()
            path = module.archive_observation(data, directory)
            original = path.read_text()
            self.assertEqual(module.archive_observation(data, directory), path)
            data['assets'][0]['financials']['eps']['value'] = 999
            with self.assertRaisesRegex(ValueError, 'sobrescribir'):
                module.archive_observation(data, directory)
            self.assertEqual(path.read_text(), original)

    def test_past_requests_are_identified_as_retrospective_not_as_original_historical_cuts(self):
        data = fixture()
        data['requested_as_of'] = '2025-01-01'
        with tempfile.TemporaryDirectory() as directory:
            path = module.archive_observation(data, directory)
            self.assertEqual(json.loads(path.read_text())['collection_mode'], 'historical_request')
            self.assertTrue(path.name.startswith('2026-10-24'))

    def test_archive_rejects_nonfinite_numbers_and_naive_collection_times(self):
        with tempfile.TemporaryDirectory() as directory:
            data = fixture()
            data['assets'][0]['price'] = float('nan')
            with self.assertRaises(ValueError):
                module.archive_observation(data, directory)
            data = fixture()
            data['generated_at'] = '2026-10-24T23:30:00'
            with self.assertRaises(ValueError):
                module.archive_observation(data, directory)
