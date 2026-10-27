import { finite } from './analytics.mjs?v=0.26.0';

// Observing filing dates today does not establish original historical vintages.
export function growthEvidence(asset, assumptions={}, research={}, context={}) {
 const asOf=context.asOf||asset.price_date;
 const history=asset.financials?.earnings_history;
 const known=history?.observed_at&&history.observed_at.slice(0,10)<=asOf&&
  history.through_filing_date<=asOf;
 const replay=known?asset.financials?.growth_research:null;
 const consensusUsed=context.consensusUsed&&['consensus','blend'].includes(research.basis);
 const manual=Object.hasOwn(assumptions,'growth')&&finite(assumptions.growth);
 const kind=research.basis==='drivers'?'drivers':consensusUsed?research.basis:
  manual?'manual':'catalog_convention';
 const labels={drivers:'Ventas, margen y dilución asumidos',consensus:'Consenso comparable observado',
  blend:'Mezcla propia y consenso comparable observado',manual:'Supuesto editado en la sesión',
  catalog_convention:'Convención del catálogo; sin estimación predictiva'};
 return {kind,source:labels[kind],sourceVintage:consensusUsed?context.consensusObservedAt:null,
  calibrated:false,historyObservedAt:known?history.observed_at:null,
  annualPeriods:known?new Set((history.records||[]).map(r=>r.period_end)).size:0,
  historyRecords:known?(history.records||[]).length:0,
  originalVintagesVerified:false,
  reconstructedOutcomes:replay?.outcomes||0,
  shrinkageCandidate:finite(replay?.latest_candidate?.annual_growth)?replay.latest_candidate.annual_growth:null,
  candidateObservations:replay?.latest_candidate?.training_observations||0,
  metrics:replay?.metrics||null,
  productionEligible:false};
}
