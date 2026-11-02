import test from 'node:test';
import assert from 'node:assert/strict';
import {auditCashflows,realizeCash} from '../scripts/audit_historical_cashflows.mjs';

function fixture(){
  const start='2025-01-01',end='2025-02-01',event={ex_date:'2025-01-15',record_date:'2025-01-15',
    pay_date:'2025-02-15',amount_per_share:10,currency:'USD'};
  const asset={symbol:'AAA',type:'stock',currency:'USD',splits:[],history:[{date:start,close:100,adj_close:100},{date:end,close:90,adj_close:100}],
    distribution_index:{currency:'USD',complete_ex_date_index:true,coverage_start:start,coverage_end:end,
      records:[{ex_date:event.ex_date,amount_per_share:10}]}};
  return {policy:{dividendPolicy:'cash',cashYield:0,dividendWithholding:0},asset,
    scores:{origins:[{cut:start,horizons:[21,63,252].map(h=>({horizon_sessions:h,maturity:h===21?end:null,
      observations:[{symbol:'AAA',role:'stock',realized_proxy:0}]}))}]},
    market:{assets:[asset]},issuer:{outcome_only:true,forecast_input_eligible:false,assets:[{symbol:'AAA',
      issuer_distributions:{symbol:'AAA',source_layer:'issuer',records:[event]}}]}};
}
test('cash realization keeps unpaid entitlements as receivables and never scores a mismatched forecast target',()=>{
  const f=fixture(),r=auditCashflows(f.scores,f.market,f.issuer,f.policy),row=r.origins[0].horizons[0].rows[0];
  assert.equal(row.before.available,false);assert.equal(row.after.available,true);
  assert.ok(Math.abs(row.after.return)<1e-12);assert.equal(row.after.cash,0);assert.equal(row.after.receivable,.1);
  assert.equal(r.summaries[21].newly_reconciled,1);assert.equal(r.summaries[63].pending_rows,1);
  assert.equal(r.forecast_scoring_performed,false);assert.equal(r.certified_full_engine_cuts,0);
  assert.equal(row.broker_execution_verified,false);
});
test('incomplete issuer events, corporate adjustments and different policy assumptions cannot pass silently',()=>{
  const f=fixture();f.issuer.assets[0].issuer_distributions.records=[];
  const report=auditCashflows(f.scores,f.market,f.issuer,f.policy);
  assert.equal(report.summaries[21].blocked,1);assert.equal(report.recovery_queue[0].required_events[0].pay_date,null);
  assert.throws(()=>auditCashflows(f.scores,f.market,{...f.issuer,forecast_input_eligible:true},f.policy),/forecast/);
  assert.throws(()=>auditCashflows(f.scores,f.market,f.issuer,{...f.policy,cashYield:.05}),/convention/);
  f.asset.price_adjustments=[{date:'2025-03-01'}];
  assert.equal(realizeCash(f.asset,'2025-01-01','2025-02-01',f.policy).available,false);
});
