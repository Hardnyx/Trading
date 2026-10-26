import unittest
import numpy as np
from datetime import date, timedelta
from scripts.multifactor_research import (
    ridge_projection, aligned_multifactor, multifactor_walk_forward,
)


def asset(sym, log_returns):
    price=100.
    rows=[{"date":"2024-01-01","adj_close":price}]
    for i,r in enumerate(log_returns):
        price*=np.exp(r)
        rows.append({"date":(date(2024,1,2)+timedelta(days=i)).isoformat(),
                     "adj_close":float(price)})
    return {"symbol":sym,"history":rows}


class MultifactorResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng=np.random.default_rng(155)
        a=rng.normal(0,.01,410)
        b=rng.normal(0,.008,410)
        residual=rng.standard_t(8,410)*.004
        cls.spy=asset("SPY",a)
        cls.tlt=asset("TLT",b)
        cls.target=asset("AAA",.0002+1.3*a-.7*b+residual)
        cls.end=cls.target["history"][-1]["date"]

    def test_ridge_recovers_factor_exposure_without_future_data(self):
        dates,y,X=aligned_multifactor(self.target,[self.spy,self.tlt],self.end)
        intercept,beta,res=ridge_projection(y[:350],X[:350])
        self.assertAlmostEqual(beta[0],1.3,delta=.25)
        self.assertAlmostEqual(beta[1],-.7,delta=.3)
        self.assertAlmostEqual(float(np.mean(res)),0,places=8)

    def test_future_prices_do_not_change_prior_factor_estimates(self):
        past=self.target["history"][330]["date"]
        d1,y1,x1=aligned_multifactor(self.target,[self.spy,self.tlt],past)
        self.target["history"][-1]["adj_close"]*=10
        try:
            d2,y2,x2=aligned_multifactor(self.target,[self.spy,self.tlt],past)
        finally:
            self.target["history"][-1]["adj_close"]/=10
        self.assertEqual(d1,d2)
        self.assertTrue(np.array_equal(y1,y2))
        self.assertTrue(np.array_equal(x1,x2))

    def test_multifactor_shadows_not_promoted_and_chronology(self):
        r=multifactor_walk_forward(self.target,[self.spy,self.tlt],self.end,
                                   window=300,test_days=21,refit_every=21)
        self.assertTrue(r["not_promoted"])
        self.assertEqual(len(r["forecast_records"]),21)
        self.assertGreater(r["paired_days"],0)
        self.assertTrue(all(row["issued_after_close"]<row["date"]
                            for row in r["forecast_records"]))
        self.assertTrue(all(row["error_retained"] for row in r["forecast_records"]))

    def test_constant_factor_rejected(self):
        with self.assertRaisesRegex(ValueError,"Degenerate"):
            ridge_projection(np.arange(300,dtype=float),
                np.column_stack((np.ones(300),np.arange(300))))


if __name__=="__main__":
    unittest.main()
