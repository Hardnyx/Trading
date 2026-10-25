import test from "node:test";
import assert from "node:assert/strict";
import { estimateResidualDependence } from "../dist/assets/js/residual-dependence.mjs";
import { preparePaths } from "../dist/assets/js/path-model.mjs";
import { correlation } from "../dist/assets/js/analytics.mjs";

function synthetic() {
  const count = 420;
  const logPrices = { SPY: [], XLK: [], AAA: [], BBB: [], CASH: [] };
  const market = [], sector = [];
  for (let t = 0; t < count; t++) {
    // Bull and bear have different means. The state at t is measurable only
    // with returns up to t-1; the fit must not use future observations.
    const sign = t < 180 || t >= 310 ? 1 : -1;
    const m = sign * .006 + .003 * Math.sin(t * 1.37);
    const tech = .004 * Math.sin(t * .63) + .003 * Math.cos(t * .29);
    market.push(m);
    sector.push(tech);
    const examples = {
      SPY: m, XLK: 1.1*m + tech,
      AAA: (sign > 0 ? 1.5 : .6)*m + .9*tech + .002*Math.sin(t * 2.39),
      BBB: (sign > 0 ? .7 : 1.6)*m + 1.2*tech + .002*Math.cos(t * 1.77),
      CASH: 0,
    };
    for (const [symbol, v] of Object.entries(examples))
      logPrices[symbol].push(Math.exp(v));
  }
  return Object.entries(logPrices).map(([symbol, gross]) => {
    let close = 100;
    return {
      symbol, type: symbol === "CASH" ? "cash" : "etf",
      sector: ["AAA", "BBB"].includes(symbol) ? "Tecnología" : "Índice amplio",
      price_date: "2026-10-23", price: 0,
      assumptions: { expectedReturn: .05 },
      history: [{ date: "2025-01-01", close, adj_close: close }].concat(
        gross.map((g,t) => {
          close *= g;
          return {
            date: new Date(Date.UTC(2025, 0, 2+t)).toISOString().slice(0,10),
            close, adj_close: close,
          };
        }),
      ),
    };
  }).map(a=>({...a, price:a.history.at(-1).close, price_date:a.history.at(-1).date}));
}
function correlationAt(model,a,b) {
  const ids = model.rows.map(row=>row.symbol);
  return model.residualCorrelation[ids.indexOf(a)][ids.indexOf(b)];
}

test("systematic bull/bear and tech sector co-movement is removed from residual correlation",()=>{
  const data = synthetic();
  const assets = data.filter(a=>["AAA","BBB"].includes(a.symbol));
  const positions = assets.map(a=>({symbol:a.symbol,weight:.5}));
  const asOf = assets[0].price_date;
  const result = estimateResidualDependence(assets,positions,asOf,500,.94,data);
  assert.equal(result.available,true);
  assert.ok(result.regimeCounts.bull>=40);
  assert.ok(result.regimeCounts.bear>=40);
  assert.ok(result.rows.every(x=>Number.isFinite(x.betaMarketBull) &&
    Number.isFinite(x.betaMarketBear)));
  const residual = correlationAt(result,"AAA","BBB");
  assert.ok(Math.abs(residual)<.65, "after conditioning should not imply perfect dependence: "+residual);
  const raw = correlation(data[2].history.slice(1).map((r,i)=>Math.log(r.adj_close/data[2].history[i].adj_close)),
    data[3].history.slice(1).map((r,i)=>Math.log(r.adj_close/data[3].history[i].adj_close)));
  assert.ok(raw>.65);
  assert.ok(Math.abs(residual)<raw);
});

test("total covariance and market variance are retained for Monte Carlo",()=>{
  const data=synthetic(), assets=data.filter(a=>["AAA","BBB"].includes(a.symbol));
  const result=preparePaths(assets,{asOf:assets[0].price_date,model:"gbm"}, {},data);
  assert.equal(result.dependence.available,true);
  assert.ok(result.covariance[0][1]>.001, "systematic market covariance must remain");
  assert.ok(result.residualCorrelation[0][1] < .7);
  assert.ok(result.covariance[0][0]>0);
});

test("unobserved market factor falls back explicitly to total correlation",()=>{
  const assets=synthetic().filter(a=>["AAA","BBB"].includes(a.symbol));
  const result=preparePaths(assets,{asOf:assets[0].price_date}, {},assets);
  assert.equal(result.dependence.available,false);
  assert.equal(result.residualCorrelation,null);
  assert.match(result.dependence.explanation,/SPY/);
});

test("regime classification is prefix-only: later observations cannot change the past fit",()=>{
  const all=synthetic(), selected=all.filter(a=>["AAA","BBB"].includes(a.symbol));
  const first=estimateResidualDependence(selected,selected.map(a=>({symbol:a.symbol,weight:.5})),
    "2025-08-01",500,.94,all);
  const revised=structuredClone(all);
  for(const asset of revised) {
    for(const row of asset.history) if(row.date>"2025-08-01")row.adj_close*=1000;
  }
  const second=estimateResidualDependence(selected,selected.map(a=>({symbol:a.symbol,weight:.5})),
    "2025-08-01",500,.94,revised);
  assert.deepEqual(first.regimeCounts,second.regimeCounts);
  assert.deepEqual(first.residualCorrelation,second.residualCorrelation);
});
