import unittest
from copy import deepcopy

from scripts.research_gate import (
    check_archive, validate_event, event_features, maturation_status,
)


def archive():
    return {
        "collected_at": "2026-10-25T20:00:00Z",
        "price_as_of": "2026-10-23",
        "collection_mode": "current",
        "assets": [{
            "symbol": "SPY", "price_date": "2026-10-23",
            "financials": {"eps": {"filed": "2026-09-30", "value": 5.0}}
        }],
        "macro": [{
            "id": "CPI", "date": "2026-10-20",
            "observed_at": "2026-10-25T19:10:00Z",
        }],
    }


def event():
    return {
        "event_id": "cpi-1",
        "type": "CPI", "source_url": "https://example.org/cpi",
        "published_at_utc": "2026-10-22T12:30:00Z",
        "known_at_utc": "2026-10-22T12:31:00Z",
        "consensus_known_at_utc": "2026-10-21T16:00:00Z",
        "actual": 3.2, "consensus": 3.4,
        "asset_ids": ["SPY"],
    }


class ResearchGateTests(unittest.TestCase):
    def test_archive_downloaded_later_is_not_original_information(self):
        past = check_archive(archive(), "2026-10-23T21:00:00Z")
        self.assertFalse(past["eligible"])
        self.assertIn("snapshot_collected_after_forecast", past["issues"])
        now = check_archive(archive(), "2026-10-25T20:01:00Z")
        self.assertTrue(now["eligible"])

    def test_historical_request_does_not_become_point_in_time_by_relabeling(self):
        a = archive()
        a["collection_mode"] = "historical_request"
        self.assertFalse(check_archive(a, "2026-10-26T08:00:00Z")["eligible"])

    def test_future_macro_and_filing_are_rejected(self):
        a = archive()
        a["assets"][0]["financials"]["eps"]["filed"] = "2026-10-26"
        a["macro"][0]["observed_at"] = "2026-10-26T00:00:00Z"
        flags = check_archive(a, "2026-10-25T21:00:00Z")["issues"]
        self.assertTrue(any(x.startswith("future_filing") for x in flags))
        self.assertTrue(any(x.startswith("future_macro_download") for x in flags))

    def test_consensus_must_precede_publication(self):
        e = event()
        result = validate_event(e, "2026-10-22T12:00:00Z")
        self.assertFalse(result["event_known_before_forecast"])
        self.assertAlmostEqual(result["surprise"], -.2)
        e["consensus_known_at_utc"] = "2026-10-22T12:30:00Z"
        with self.assertRaisesRegex(ValueError, "Post-release"):
            validate_event(e)

    def test_future_news_never_becomes_prior_model_feature(self):
        es = [event()]
        self.assertEqual(event_features(es, "2026-10-22T12:00:00Z", ["SPY"]), [])
        self.assertEqual(len(event_features(es, "2026-10-22T12:35:00Z", ["SPY"])), 1)
        self.assertEqual(event_features(es, "2026-10-22T12:35:00Z", ["TLT"]), [])

    def test_original_prospective_forecast_is_immature_until_target(self):
        self.assertEqual(maturation_status("2026-10-25T20:00:00Z",
                         "2027-10-25", "2026-10-25"), "immature")
        self.assertEqual(maturation_status("2026-10-25T20:00:00Z",
                         "2027-10-25", "2027-10-26"), "eligible_for_outcome_matching")
        self.assertEqual(maturation_status("2026-10-25T20:00:00Z",
                         "2026-10-25", "2026-10-25",
                         original_archive=False), "unverified_origin")


if __name__ == "__main__":
    unittest.main()
