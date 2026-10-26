import unittest
from copy import deepcopy
from scripts.news_garchx_research import dated_news_signal, compare_news_garchx


def ev(day="2026-10-10"):
    return {
        "event_id":"cpi",
        "type":"CPI",
        "source_url":"https://example.org/release",
        "published_at_utc":day+"T12:30:00Z",
        "known_at_utc":day+"T12:35:00Z",
        "consensus_known_at_utc":"2026-10-09T18:00:00Z",
        "actual":3.4,"consensus":3.0,"consensus_scale":0.2,
        "scope":"macro",
    }


class NewsGarchXTests(unittest.TestCase):
    def test_future_release_cannot_affect_prior_variance(self):
        e=ev()
        self.assertEqual(dated_news_signal([e],"2026-10-10T12:00:00Z","SPY"),0.)
        self.assertGreater(dated_news_signal([e],"2026-10-10T12:40:00Z","SPY"),0.)
        self.assertEqual(dated_news_signal([e],"2026-11-10T12:40:00Z","SPY"),0.)

    def test_missing_consensus_scale_does_not_create_fake_speech_score(self):
        e=ev()
        del e["consensus_scale"]
        self.assertEqual(dated_news_signal([e],"2026-10-11T10:00:00Z","SPY"),0.)

    def test_news_is_not_promoted_without_sufficient_verified_events(self):
        rows=[{
            "issued_after_close":f"2026-05-{(i%25)+1:02d}",
            "for_date":f"2026-05-{(i%25)+1:02d}",
            "gjr_variance_pct2":1.0,
            "standardized_surprise":1.5,
        } for i in range(100)]
        result=compare_news_garchx(rows,[],"SPY")
        self.assertEqual(result["status"],"insufficient_verified_surprises")
        self.assertTrue(result["not_promoted"])


if __name__=="__main__":
    unittest.main()
