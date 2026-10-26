import test from 'node:test';
import assert from 'node:assert/strict';
import {operatingMarginStress,minimaxRegret,pairedUtilityEvidence,variantInputs} from '../scripts/robust_portfolio_core.mjs';
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-10,`${a} != ${b}`);
function cyclical(){
 const fact=value=>({value,period_end:'2026-09-30',filed:'2026-10-22',method:'TTM'});
 return {symbol:'CYCLE',type:'stock',sector:'Tecnología',price:100,price_date:'2026-10-23',
  assumptions:{growth:.06,multiple:20,horizon:3,discount:.1},
  financials:{eps:fact(10),operating_income:fact(500),revenue:fact(1000),
   history:Array.from({length:12},(_,i)=>({period_end:`${2023+Math.floor(i/4)}-${['03','06','09','12'][i%4]}-20`,
    filed:`${2023+Math.floor(i/4)}-${['03','06','09','12'][i%4]}-25`,operating_margin:.2}))}};
}
test('margin stress uses comparable original filings and never raises depressed earnings',()=>{
 const a=cyclical(),frozen=JSON.stringify(a);
 const r=operatingMarginStress(a,'2026-10-23','2026-10-26');
 assert.equal(r.available,true);close(r.factor,.4);close(r.stressed_eps,4);
 assert.equal(JSON.stringify(a),frozen);
 a.financials.operating_income.value=100;
 close(operatingMarginStress(a,'2026-10-23','2026-10-26').factor,1);
});
test('future observations, short histories, incompatible periods and conflicting margins cannot normalize EPS',()=>{
 for(const mutate of [a=>a.financials.history.forEach(r=>r.filed='2026-10-27'),
  a=>a.financials.history=a.financials.history.slice(-7),
  a=>a.financials.revenue.period_end='2026-06-30',
  a=>a.financials.history.push({...a.financials.history[0],operating_margin:.9})]){
  const a=cyclical();mutate(a);
  assert.equal(operatingMarginStress(a,'2026-10-23','2026-10-26').available,false);
 }
});
test('duplicate revisions are not extra quarters and the median is symmetric for even samples',()=>{
 const a=cyclical();a.financials.history[0].operating_margin=.1;
 for(let i=6;i<12;i++)a.financials.history[i].operating_margin=.3;
 const first=operatingMarginStress(a,'2026-10-23','2026-10-26');close(first.median_operating_margin,.25);
 a.financials.history.push({...a.financials.history[0]});
 assert.equal(operatingMarginStress(a,'2026-10-23','2026-10-26').observations,12);
});
test('regret balances model disagreement instead of picking the highest single-model utility',()=>{
 const rows=[{id:'A',feasible:true,utilities:{bull:.20,bear:-.20}},
  {id:'B',feasible:true,utilities:{bull:.07,bear:.02}},
  {id:'C',feasible:true,utilities:{bull:0,bear:.04}},
  {id:'invalid',feasible:false,utilities:{bull:10,bear:10}}];
 const r=minimaxRegret(rows,['bull','bear']);
 assert.equal(r.best.id,'B');close(r.best.maxRegret,.13);
 assert.equal(minimaxRegret(rows.map(r=>({...r,feasible:false})),['bull']).best,null);
 assert.throws(()=>minimaxRegret([{id:'X',feasible:true,utilities:{bull:0}}],['bull','bear']),/Incomplete/);
});
test('paired Monte Carlo evidence retains exact deterministic gains and accounts for the verification family',()=>{
 const deterministic=pairedUtilityEvidence([.01,.01,.01],[0,0,0],100000,50);
 close(deterministic.ce_gain_dollars,1000);close(deterministic.lower_ce_gain_dollars,1000);
 const narrow=pairedUtilityEvidence([-.02,.02,.01],[0,0,0],100000,1);
 const wide=pairedUtilityEvidence([-.02,.02,.01],[0,0,0],100000,100);
 assert.ok(wide.lower_ce_gain_dollars<narrow.lower_ce_gain_dollars);
 assert.throws(()=>pairedUtilityEvidence([0,NaN],[0,0],100000),/Invalid/);
});
test('combined variant preserves asset order, risk state and reported market facts',()=>{
 const a=cyclical(),x={assets:[a],asOf:'2026-10-23',informationAsOf:'2026-10-26',riskFree:.04,
  covariance:[[.04]],options:{asOf:'2026-10-23',informationAsOf:'2026-10-26',research:{},assetAssumptions:{}}};
 const frozen=JSON.stringify(x),r=variantInputs(x,{id:'stress',noRerating:true,marginStress:true});
 assert.equal(JSON.stringify(x),frozen);assert.equal(r.covariance,x.covariance);
 assert.deepEqual(r.assets.map(a=>a.symbol),['CYCLE']);
 close(r.assets[0].financials.eps.value,4);
 close(r.anchors[0].forecast.assumptions.multiple,10);
});
