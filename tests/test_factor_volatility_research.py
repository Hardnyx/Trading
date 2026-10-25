import unittest
from datetime import date,timedelta
import math
import numpy as np
from scripts.factor_volatility_research import (aligned_logs,fit_market_projection,
                                                 residual_walk_forward)

def sample(n=565):
    spy=100.;asset=100.; hs=[]; ha=[]
    start=date(2024,1,1)
    for t in range(n):
        m=.002*math.cos(t*1.51)+.008*math.sin(.77*t)
        e=.003*math.sin(t*2.31)+.0015*math.cos(t*.31)
        spy*=math.exp(m)
        asset*=math.exp(1.4*m+e)
        day=(start+timedelta(days=t)).isoformat()
        hs.append({"date":day,"adj_close":spy})
        ha.append({"date":day,"adj_close":asset})
    return {"symbol":"AAA","history":ha},{"symbol":"SPY","history":hs},ha[-1]["date"]


class ResidualRiskTests(unittest.TestCase):
    def test_market_ols_recovers_known_beta(self):
        a,spy,last=sample()
        _,y,m=aligned_logs(a,spy,last)
        alpha,beta=fit_market_projection(y,m)
        self.assertAlmostEqual(beta,1.4,delta=.1)
        self.assertAlmostEqual(float(np.mean(y-alpha-beta*m)),0,places=8)

    def test_forecast_cuts_and_future_revision_do_not_leak(self):
        a,spy,last=sample()
        cutoff=a["history"][-24]["date"]
        early=residual_walk_forward(a,spy,cutoff,train_window=500,
                                    test_days=20,refit_every=10)
        changed={"symbol":"AAA","history":[dict(row) for row in a["history"]]}
        for row in changed["history"]:
            if row["date"]>cutoff:row["adj_close"]*=200
        later=residual_walk_forward(changed,spy,cutoff,train_window=500,
                                    test_days=20,refit_every=10)
        self.assertEqual(early["forecast_records"],later["forecast_records"])
        self.assertTrue(all(row["issued_after_close"]<row["for_date"]
                            for row in early["forecast_records"]))
        self.assertTrue(all(row["training_through"]<row["for_date"]
                            for row in early["forecast_records"]
                            if row["training_through"]))

    def test_no_fabricated_beta_when_spy_missing(self):
        a,spy,last=sample()
        with self.assertRaises(ValueError):
            fit_market_projection(np.ones(300),np.zeros(300))

if __name__=="__main__":
    unittest.main()
