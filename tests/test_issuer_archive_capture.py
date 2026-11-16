"""Issuer archive capture: only captures before the cut's New York close are eligible."""
import json
import unittest
from unittest import mock

from scripts import issuer_archive_capture as cap


class CloseLimitTests(unittest.TestCase):
    def test_close_is_seasonal(self):
        self.assertEqual(cap.close_utc("2025-03-31").hour, 20)
        self.assertEqual(cap.close_utc("2024-12-31").hour, 21)

    def test_a_capture_later_on_the_cut_day_is_ignored(self):
        rows = [["timestamp", "original"], ["20250328120000", "https://x/products/1/a"],
                ["20250331231841", "https://x/products/1/a"]]
        with mock.patch.object(cap, "fetch", return_value=json.dumps(rows).encode()) as fetch:
            self.assertEqual(cap.last_capture("https://x/products/1/a", "2025-03-31"),
                             ("20250328120000", "https://x/products/1/a"))
        self.assertIn("to=20250331200000", fetch.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
