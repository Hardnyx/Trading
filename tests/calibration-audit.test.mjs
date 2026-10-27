import test from 'node:test';import assert from 'node:assert/strict';
import {calibrationAudit} from '../dist/assets/js/calibration-audit.mjs?v=0.23.0';
const row=(id,start,end,realized=.1)=>({id,status:'scored',maturity:end,realized,
 origin:{prospective:true,model_version:'0.23.0',price_as_of:start,settings:{model:'merton',driftMode:'fundamental',volatilityMode:'hybrid',mandate:{referenceCurrency:'USD'}}},
 prediction:{model:'merton',horizon:1,mean:.05,p05:-.1,p95:.2,lossProbability:.3}});
test('overlapping forecasts and repeated seeds do not inflate calibration sample',()=>{
 const rows=[row('a','2024-01-01','2025-01-01'),row('b','2024-06-01','2025-06-01'),row('c','2025-01-01','2026-01-01')];
 const g=calibrationAudit(rows).groups[0];assert.equal(g.scored,3);assert.equal(g.nonoverlapping,2);assert.deepEqual(g.selectedIds,['a','c']);
 assert.equal(g.status,'insufficient_nonoverlapping_windows');assert.equal(g.parameterPromotionAllowed,false);
 assert.ok(g.coverageLower<.9&&g.coverageUpper>=.9);assert.ok(Math.abs(g.bias-.05)<1e-12);
});
test('selection is independent of outcomes and models/horizons/currencies are not pooled',()=>{
 const a=row('a','2024-01-01','2025-01-01'),b=row('b','2024-06-01','2025-06-01');
 const first=calibrationAudit([a,b]).groups[0].selectedIds;a.realized=-.9;b.realized=.9;
 assert.deepEqual(calibrationAudit([b,a]).groups[0].selectedIds,first);
 const c=structuredClone(a);c.origin.model_version='old';const d=structuredClone(a);d.prediction.horizon=2;
 const e=structuredClone(a);e.origin.settings.mandate.referenceCurrency='PEN';
 assert.equal(calibrationAudit([a,c,d,e]).groups.length,4);
});
test('immature, retrospective and incomplete results never count as calibration evidence',()=>{
 const a=row('a','2024-01-01','2025-01-01');a.status='immature';const b=structuredClone(a);b.status='scored';b.origin.prospective=false;
 const c=row('c','2024-01-01','2025-01-01');c.prediction.lossProbability=NaN;
 assert.equal(calibrationAudit([a,b,c]).groups.length,0);
});
