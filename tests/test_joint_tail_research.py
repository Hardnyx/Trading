import unittest
import numpy as np
from scripts.joint_tail_research import (
    make_covariance, joint_score, rolling_joint_tail_challenger,
)


class JointTailResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng=np.random.default_rng(101)
        factors=rng.standard_t(5,720)/np.sqrt(5/3)
        cls.market=.01*factors
        cls.asset=.012*(.7*factors+.5*rng.standard_t(6,720))

    def test_density_compares_same_training_covariance(self):
        pair=np.column_stack((self.asset[:550],self.market[:550]))
        cov=make_covariance(pair)
        self.assertGreater(float(np.min(np.linalg.eigvalsh(cov))),0)
        m=pair.mean(axis=0)
        self.assertTrue(np.isfinite(joint_score(pair,m,cov)))
        self.assertTrue(np.isfinite(joint_score(pair,m,cov,5)))

    def test_rolling_training_ends_before_each_holdout(self):
        result=rolling_joint_tail_challenger(self.asset,self.market,
                                             train_window=400,test_days=80,
                                             refit_every=20)
        self.assertFalse(result["eligible_for_promotion"])
        self.assertEqual(result["test_days"],80)
        for f in result["folds"]:
            self.assertLess(f["training_end_index"],f["test_start_index"])
            self.assertIn(f["train_chosen_nu"],(4,6,8,12,20,40))
        self.assertTrue(np.isfinite(result["oos_logscore_gain_student_t"]))

    def test_future_shock_does_not_influence_preceding_fold_estimates(self):
        a=rolling_joint_tail_challenger(self.asset,self.market,
                                         train_window=400,test_days=80,
                                         refit_every=20)
        changed=self.asset.copy()
        changed[-1]-=1.
        b=rolling_joint_tail_challenger(changed,self.market,
                                        train_window=400,test_days=80,
                                        refit_every=20)
        self.assertEqual(a["folds"][0]["train_chosen_nu"],
                         b["folds"][0]["train_chosen_nu"])
        self.assertAlmostEqual(a["folds"][0]["holdout_logscore_t"],
                               b["folds"][0]["holdout_logscore_t"],places=9)


if __name__=="__main__":
    unittest.main()
