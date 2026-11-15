"""Archived issuer bond pages: dated characteristic blocks, nothing after the cut."""
import unittest

from scripts.issuer_archive_profiles import parse

PAGE = """Expense Ratio: 0.15%
<div class="product-data-item col-effectiveDuration "><div class="caption">Effective Duration <button></button></div>
<div class="as-of-date">as of Dec 20, 2024</div><div class="data">1.82 yrs</div></div>
<div class="product-data-item col-ytm "><div class="caption">Average Yield to Maturity</div>
<div class="as-of-date">as of Jan 03, 2025</div><div class="data">4.40%</div></div>
<div class="product-data-item col-secYield "><div class="caption">30 Day SEC Yield</div>
<div class="as-of-date">as of Dec 19, 2024</div><div class="data">4.16%</div></div>"""


class IssuerProfileTests(unittest.TestCase):
    def test_dated_blocks_and_rejection_after_cut(self):
        profile, rejected = parse(PAGE, "2024-12-31")
        self.assertEqual(profile["effective_duration_years"], {"value": 1.82, "as_of": "2024-12-20", "raw": "1.82 yrs"})
        self.assertAlmostEqual(profile["sec_yield_30d"]["value"], .0416)
        self.assertAlmostEqual(profile["expense_ratio"]["value"], .0015)
        self.assertNotIn("yield_to_maturity", profile)
        self.assertEqual(rejected, ["Average Yield to Maturity"])


if __name__ == "__main__":
    unittest.main()
