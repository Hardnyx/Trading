import unittest
from scripts.summarize_price_risk import nonoverlapping, block_interval, holm_adjust, summarize


class RiskSummaryTest(unittest.TestCase):
    def test_overlaps_are_not_independent_and_small_samples_have_no_block_interval(self):
        rows = [{"origin_date": a, "maturity_date": b} for a, b in
                [("2026-01-01", "2026-01-08"), ("2026-01-02", "2026-01-09"), ("2026-01-08", "2026-01-15")]]
        self.assertEqual(len(nonoverlapping(rows)), 2)
        self.assertIsNone(block_interval([1, 2, 3]))

    def test_family_adjustment_cannot_make_an_individual_test_more_significant(self):
        p = [.002, .03, .5]
        adjusted = holm_adjust(p)
        self.assertTrue(all(a >= b for a, b in zip(adjusted, p)))
        self.assertAlmostEqual(adjusted[0], .006)

    @staticmethod
    def fixture():
        records = []
        for model in ("targeted_ewma", "flat_ewma", "dynamic_ewma"):
            for i in range(30):
                day = f"2026-01-{i+1:02d}"
                records.append(dict(target="PORTFOLIO:current_exposure", horizon=21, model=model,
                                    origin_date=day, maturity_date=day, var95_exception=i == 0,
                                    crps=.01, qlike=0., es_residual=0.))
        return dict(method="test", protocol={}, records=records)

    def test_few_tail_hits_and_no_rejection_never_become_predictive_validation(self):
        r = summarize(self.fixture())
        self.assertFalse(r["prospective"])
        self.assertFalse(r["production_eligible"])
        self.assertFalse(r["automatic_promotion"])
        self.assertTrue(all(not x["tail_count_sufficient_for_review"] for x in r["cells"]))
        self.assertTrue(all(x["binomial_iid95_interval"][1] > .05 for x in r["cells"]))
        self.assertTrue(all(x["interval_alpha"] == .025 for x in r["primary_comparisons"]))

    def test_missing_paired_outcome_cannot_disappear_from_a_benchmark_comparison(self):
        report = self.fixture()
        report["records"] = [r for r in report["records"] if not
                             (r["model"] == "flat_ewma" and r["origin_date"] == "2026-01-01")]
        with self.assertRaisesRegex(ValueError, "Unpaired"):
            summarize(report)
