import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {inspectDailyArchives,auditDailyArchives}
 from '../scripts/daily_archive_readiness.mjs';

const valid=day=>({
 schema_version:1,price_as_of:day,requested_as_of:day,
 collected_at:day+'T22:30:00Z',collection_mode:'current',
 assets:[{symbol:'SPY',price_date:day,quote:{date:day,close:100}}]});
test('repeated weekend closings cannot inflate the number of original trading dates',()=>{
 const friday=valid('2026-11-06'),revised={...friday,collected_at:'2026-11-06T23:00:00Z'};
 const oldWeekend={...friday,collected_at:'2026-11-08T05:38:57Z',
  requested_as_of:'2026-11-08',collection_mode:'current'};
 const newWeekend={...oldWeekend,collection_mode:'stale_market_close'};
 const result=inspectDailyArchives([
  {path:'later',snapshot:revised},
  {path:'legacy-weekend',snapshot:oldWeekend},
  {path:'first',snapshot:friday},
  {path:'corrected-weekend',snapshot:newWeekend}]);
 assert.equal(result.archive_count,4);
 assert.equal(result.distinct_candidate_market_dates,1);
 assert.equal(result.original_post_close_candidate_archives,2);
 assert.equal(result.excluded_count,2);
 assert.equal(result.classification_counts['stale-market-close'],2);
 assert.equal(result.first_collection_candidates[0].path,'first');
 assert.equal(result.first_git_publication_verified_here,false);
 assert.equal(result.predictive_validation,'not-established');
});
test('readiness skips historic requests and pre-close quotes without amending originals',()=>{
 const day='2026-11-06';
 const rows=[{snapshot:{...valid(day),requested_as_of:'2026-11-05'}},
  {snapshot:{...valid(day),collected_at:'2026-11-06T15:00:00Z'}}];
 const result=inspectDailyArchives(rows);
 assert.equal(result.distinct_candidate_market_dates,0);
 assert.equal(result.classification_counts['historical-request'],1);
 assert.equal(result.classification_counts['pre-close-or-different-session'],1);
});
test('filesystem audit reads original bytes but leaves previously saved files intact',()=>{
 const root=mkdtempSync(join(tmpdir(),'trading-daily-readiness-'));
 try{
  const dir=join(root,'data','snapshots','2026-11');
  mkdirSync(dir,{recursive:true});
  const raw=JSON.stringify(valid('2026-11-06'))+'\n';
  const file=join(dir,'2026-11-06T223000000000Z.json');
  writeFileSync(file,raw);
  const result=auditDailyArchives(root);
  assert.equal(result.archive_count,1);
  assert.equal(result.distinct_candidate_market_dates,1);
  assert.equal(result.first_collection_candidates[0].market_date,'2026-11-06');
  const after=readFileSync(file,'utf8');
  assert.equal(after,raw);
 }finally{rmSync(root,{recursive:true,force:true})}
});
