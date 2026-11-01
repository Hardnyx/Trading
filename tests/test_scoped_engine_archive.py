import gzip
import json
from pathlib import Path
import unittest

from scripts.archive_scoped_pilot import summarize
from scripts.historical_sources import ROOT


class ScopedCohortArchive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = Path('data/historical/scoped-engine-pilot-v1')
        cls.inputs = (ROOT / cls.folder / 'inputs.json.gz').read_bytes()
        cls.results = (ROOT / cls.folder / 'results.json.gz').read_bytes()

    def test_exact_archives_bind_snapshots_and_keep_execution_separate_from_validation(self):
        summary = summarize(self.inputs, self.results, self.folder)
        full = json.loads(gzip.decompress(self.results))
        self.assertEqual(summary['executed_development_cuts'], 2)
        self.assertEqual(summary['certified_full_engine_cuts'], 0)
        self.assertFalse(summary['production_eligible'])
        self.assertFalse(summary['prospective'])
        self.assertEqual(summary['predictive_validation'], 'not-established')
        self.assertEqual(len(summary['schedule']), 48)
        for r, original in zip(summary['results'], full['results']):
            self.assertEqual(r['decision']['positions'], original['proposal']['positions'])
            self.assertEqual(len(r['forecasts']), original['proposal']['selection']['simulated'])
            self.assertIsNotNone(r['decision']['robust_status'])

    def test_different_input_cannot_be_attached_to_existing_decisions(self):
        bundle = json.loads(gzip.decompress(self.inputs))
        bundle['origins'][0]['snapshot']['assets'][0]['price'] += 1
        changed = gzip.compress(json.dumps(bundle).encode())
        with self.assertRaisesRegex(ValueError, 'identity'):
            summarize(changed, self.results, self.folder)

    def test_changed_scope_missing_dates_or_source_manifest_are_rejected(self):
        for kind in ('scope', 'dates', 'sources'):
            full = json.loads(gzip.decompress(self.results))
            if kind == 'scope':
                full['production_eligible'] = True
            elif kind == 'dates':
                full['results'].pop()
            else:
                full['production_sources'][0]['sha256'] = 'forged'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                summarize(self.inputs, gzip.compress(json.dumps(full).encode()), self.folder)


if __name__ == '__main__':
    unittest.main()
