import unittest
from scripts.build_event_registry import extract_filings
from scripts.research_gate import validate_event


class SecEventRegistryTests(unittest.TestCase):
    def test_filing_is_not_backdated_to_sec_release_when_archive_collected_later(self):
        archive={
            "collection_mode":"current",
            "collected_at":"2026-10-25T20:00:00Z",
            "assets":[{"symbol":"AAA","filings":[{
                "form":"10-Q","accession":"000001-26-01",
                "accepted_at":"2026-10-23T20:01:00Z",
                "url":"https://www.sec.gov/Archives/edgar/data/1/filing.htm",
            }]}],
        }
        e=extract_filings(archive)[0]
        self.assertEqual(e["known_at_utc"],"2026-10-25T20:00:00+00:00")
        self.assertFalse(validate_event(e,"2026-10-24T10:00:00Z")
                         ["event_known_before_forecast"])
        self.assertTrue(validate_event(e,"2026-10-26T10:00:00Z")
                        ["event_known_before_forecast"])
        self.assertFalse(e["numeric_surprise_available"])

    def test_no_retrospective_replay_certification(self):
        archive={"collection_mode":"historical_request",
                 "collected_at":"2026-10-25T20:00:00Z",
                 "assets":[]}
        self.assertEqual(extract_filings(archive),[])


if __name__=="__main__":
    unittest.main()
