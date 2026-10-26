import unittest
import numpy as np
from scripts.tail_research import (
    ewma_var_oos, var_backtest, coexceedance, moving_block_cvar,
)


class TailResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng=np.random.default_rng(20261025)
        cls.market=rng.standard_t(6,560)*.009
        cls.stock=.9*cls.market+rng.standard_t(7,560)*.008

    def test_forecasts_are_chronologically_frozen(self):
        a=ewma_var_oos(self.stock,window=252,test_days=90)
        distorted=self.stock.copy()
        distorted[-1]=-3.
        b=ewma_var_oos(distorted,window=252,test_days=90)
        self.assertEqual(a[-1]["var5"],b[-1]["var5"])
        self.assertTrue(a[-1]["var5"]>b[-1]["realized"])
        self.assertTrue(b[-1]["exception"])
        self.assertNotEqual(a[-1]["realized"],b[-1]["realized"])

    def test_coverage_and_independence_scores_are_finite(self):
        forecasts=ewma_var_oos(self.stock,window=252,test_days=180)
        score=var_backtest(forecasts)
        self.assertEqual(score["days"],180)
        self.assertGreaterEqual(score["conditional_coverage_p"],0)
        self.assertLessEqual(score["conditional_coverage_p"],1)
        self.assertEqual(score["exceptions"],sum(r["exception"] for r in forecasts))
        self.assertEqual(score["tail_count_sufficient_for_es"],
                         score["exceptions"]>=20)

    def test_market_tail_dependence_exceeds_independent_baseline(self):
        a=coexceedance(self.stock,self.market)
        self.assertGreater(a["p_asset_tail_given_market_tail"],.05)
        self.assertGreater(a["joint_left_tail_days"],
                           a["independent_expected_joint_days"])

    def test_block_stress_is_reproducible_and_shifts_with_shocks(self):
        before=moving_block_cvar(self.stock,self.market,paths=200,horizon=21,seed=31)
        again=moving_block_cvar(self.stock,self.market,paths=200,horizon=21,seed=31)
        self.assertEqual(before,again)
        altered=self.stock.copy()
        altered[210:215]-=.25
        altered_result=moving_block_cvar(altered,self.market,paths=200,
                                         horizon=21,seed=31)
        self.assertNotEqual(before["cvar95_loss"],altered_result["cvar95_loss"])
        self.assertTrue(before["not_promoted"])


if __name__=="__main__":
    unittest.main()
