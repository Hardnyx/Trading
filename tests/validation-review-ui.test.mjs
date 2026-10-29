import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {loadTemplates} from '../dist/assets/js/ui/templates.mjs?v=0.35.0';
import {reviewStatus,reviewDecisionWarning,validationReviewPanel} from '../dist/assets/js/ui/validation-review.mjs?v=0.35.0';
await loadTemplates(async url=>({ok:true,text:()=>readFile(url,'utf8')}));
const market={price_as_of:'2026-10-28',generated_at:'2026-10-29T02:41:05Z'},now=Date.parse('2026-10-29T18:00:00Z');
function report(){return {schema_version:1,protocol:'monthly-validation-review-v1',updated_at:'2026-10-29T17:00:00Z',
 price_cut:market.price_as_of,source_market_generated_at:market.generated_at,price_kernel_version:'1.0.0',health:'complete',issues:[],
 kernel:{sealed:2,series:{'1|PORTFOLIO:reference-decision':{nonoverlapping_origins:0,exception_rate:null,
  exact_binomial_95:null,crps_gain:null,missing_outcomes:0,cumulative:[]}}},
 signals:{sealed:1,current_cohort:'current',cohorts:{current:{horizons:{21:{mature_origins:0},63:{mature_origins:0},252:{mature_origins:0}}}}},
 monthly_review:{month:'2026-10',verdict:'accumulating',rejections:[]}};}
test('missing and stale monitoring cannot masquerade as zero observed risk',()=>{
 assert.match(reviewStatus(null,market,now).label,/NO DISPONIBLE/);
 const r=report();r.price_cut='2026-10-27';assert.match(reviewStatus(r,market,now).label,/DESACTUALIZADO/);
 r.price_cut=market.price_as_of;r.updated_at='2026-10-20T00:00:00Z';assert.equal(reviewStatus(r,market,now).warning,true);
 const html=validationReviewPanel(null,market,now);assert.match(html,/No comprobado/);assert.doesNotMatch(html,/NaN|undefined/);
});
test('an unripe registry renders pending results without fabricated charts or validation',()=>{
 const r=report(),html=validationReviewPanel(r,market,now);
 assert.match(html,/ACUMULANDO · SIN VALIDAR/);assert.match(html,/Pendiente/);assert.match(html,/Sin muestra/);
 assert.match(html,/no hay resultados maduros/);assert.doesNotMatch(html,/<svg|NaN|undefined/);
 assert.match(html,/SIN PRUEBAS EVALUABLES/);
 assert.equal(reviewDecisionWarning(r,market,now),'');
});
test('a rejection or incomplete evidence is visible in the decision without changing its weights',()=>{
 const r=report();r.monthly_review.verdict='review-required';const before=JSON.stringify(r);
 assert.match(reviewDecisionWarning(r,market,now),/rechazos.*suspenden nuevas promociones/);
 assert.equal(JSON.stringify(r),before);
 r.health='incomplete';assert.match(reviewStatus(r,market,now).label,/INCOMPLETA/);
 r.health='complete';r.monthly_review.verdict='not-rejected-unvalidated';assert.match(reviewStatus(r,market,now).label,/SIN RECHAZO · SIN VALIDAR/);
});
test('actual coverage and QLIKE curves use mature observations, retaining escaping of review evidence',()=>{
 const r=report(),s=r.kernel.series['1|PORTFOLIO:reference-decision'];
 Object.assign(s,{nonoverlapping_origins:2,exception_rate:0,exact_binomial_95:[0,.84],crps_gain:.01,
  cumulative:[{maturity_date:'2026-10-27',exceptions:0,observations:1,qlike_gain:null},
   {maturity_date:'2026-10-28',exceptions:0,observations:2,qlike_gain:.03}]});
 r.issues=[{code:'<script>alert(1)</script>'}];
 const html=validationReviewPanel(r,market,now);
 assert.match(html,/<svg/);assert.match(html,/Excepciones VaR95 acumuladas/);assert.match(html,/QLIKE acumulada/);
 assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>|NaN|undefined/);
});
