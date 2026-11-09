"""Exact Gaussian AR1 sensitivity identities, never predictive evidence."""
import copy
from math import isclose
import unittest

from scripts.confirmatory_power_feasibility import (
    SCHEMA, sum_variance, gaussian_power, minimum_detectable_effect,
    months_for_power, evaluate,
)


def contract():
    return {
        "schema": "full-engine-prospective-registration-v2",
        "status": "registered-methodology-inactive-confirmatory-inference",
        "activation": {"formal_inference_enabled": False,
                       "confirmatory_collection_open": False},
        "primary_tests": [
            {"id": f"{kind}:{h}"} for kind in ("return_mse", "ranking_ic")
            for h in (21, 63, 252)
        ] + [{"id": "net_economic_value:21"}],
        "multiplicity": {"method": "Holm step-down", "alpha": .05,
                         "direction": "one-sided positive advantage"},
        "bootstrap": {"block_lengths_months": [12,24], "draws": 10000,
                      "seed": 20261030, "minimum_complete_blocks": 4},
        "sampling": {"minimum_mature_eligible_months": 96},
        "economic_effect_thresholds": {"status": "unjustified-power-not-established",
            "return_mse": None, "ranking_ic": None, "net_economic_value": None},
    }


class GaussianPowerFeasibilityTests(unittest.TestCase):
    def test_exact_ar1_sum_variance(self):
        self.assertEqual(sum_variance(96, 0.), 96.)
        self.assertTrue(isclose(sum_variance(3, .5), 5.5))
        self.assertTrue(isclose(sum_variance(2, .5), 3.))
        self.assertTrue(isclose(sum_variance(1, .85), 1.))
        for phi in (0., .3, .6, .85):
            for n in (96, 192, 360):
                direct = n + 2*sum((n-lag)*phi**lag for lag in range(1,n))
                self.assertTrue(isclose(sum_variance(n, phi), direct, rel_tol=1e-12))
                self.assertGreaterEqual(sum_variance(n, phi), n)
        for args in ((0,0.), (96,-.1), (96,1.), (96,float("nan"))):
            with self.assertRaises(ValueError):
                sum_variance(*args)

    def test_zero_effect_is_the_first_step_nominal_size(self):
        for phi in (0., .3, .6, .85):
            self.assertTrue(isclose(gaussian_power(96, phi, 0., .05), .05/7))
        self.assertLess(gaussian_power(96,.6,.1,.05),
                        gaussian_power(192,.6,.1,.05))
        self.assertLess(gaussian_power(96,.6,.1,.05),
                        gaussian_power(96,.6,.25,.05))
        with self.assertRaises(ValueError):
            gaussian_power(96,.6,-.1,.05)

    def test_minimum_effect_exactly_inverts_target_power(self):
        for phi in (0.,.3,.6,.85):
            for n in (96,192,360):
                effect = minimum_detectable_effect(n,phi,.05)
                self.assertTrue(isclose(gaussian_power(n,phi,effect,.05),.8,
                                        rel_tol=1e-12,abs_tol=1e-12))
        self.assertGreater(minimum_detectable_effect(96,.6,.05),
                           minimum_detectable_effect(192,.6,.05))
        with self.assertRaises(ValueError):
            minimum_detectable_effect(96,.6,.05,target_power=.05/7)

    def test_minimum_month_search_is_not_an_unsupported_fraction(self):
        for phi in (0., .3, .6, .85):
            for effect in (.1, .25, .5):
                n = months_for_power(phi,effect,.05)
                self.assertIsInstance(n,int)
                self.assertGreaterEqual(gaussian_power(n,phi,effect,.05),.8)
                if n > 1:
                    self.assertLess(gaussian_power(n-1,phi,effect,.05),.8)
        self.assertIsNone(months_for_power(.85,.1,.05,max_months=96))
        with self.assertRaises(ValueError):
            months_for_power(.6,0.,.05)

    def test_frozen_contract_and_false_inference_flags(self):
        a = evaluate(contract())
        self.assertEqual(a["schema"],SCHEMA)
        self.assertEqual(len(a["rows"]),12)
        self.assertEqual(len(a["requirements"]),12)
        self.assertFalse(a["market_data_read"])
        self.assertFalse(a["real_market_effect_thresholds_registered"])
        self.assertFalse(a["formal_inference_enabled"])
        self.assertTrue(a["familywise_power_not_estimated"])
        bad = copy.deepcopy(contract())
        bad["economic_effect_thresholds"]["return_mse"] = .1
        with self.assertRaisesRegex(ValueError,"Economic effects"):
            evaluate(bad)
        bad = copy.deepcopy(contract())
        bad["multiplicity"]["alpha"] = .1
        with self.assertRaisesRegex(ValueError,"frozen confirmatory family"):
            evaluate(bad)


if __name__ == "__main__":
    unittest.main()
