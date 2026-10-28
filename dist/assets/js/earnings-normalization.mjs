import { finite } from './analytics.mjs?v=0.28.0';
import { earningsShareBasis } from './financial-freshness.mjs?v=0.28.0';

// An accounting bridge, not a claim that continuing earnings are recurring.
// Missing discontinued earnings cannot be interpreted as zero.
export function dilutedEarningsBridge(asset, asOf=asset.price_date){
 const f=asset.financials||{};
 const records=[f.eps,f.continuing_eps,f.discontinued_eps];
 const [reported,continuing,discontinued]=records.map(r=>r?.value);
 const failure=reason=>({available:false,reason,reported:finite(reported)?reported:null});
 if(!records.every(r=>finite(r?.value)&&r.filed&&r.filed<=asOf&&r.period_end&&r.period_end<=asOf))
  return failure('Faltan BPA total, continuado y discontinuado publicados al corte');
 if(records.some(r=>earningsShareBasis(asset,asOf,r).blocked))
  return failure('La base por acción no está reconciliada alrededor de un split');
 if(!records.every(r=>r.period_end===records[0].period_end&&r.method===records[0].method))
  return failure('Los tres BPA no comparten periodo y método');
 const components=records.map(r=>r.components||[]);
 if(!components.every(c=>[1,3].includes(c.length)&&c.every(r=>finite(r.val)&&r.start&&r.end&&r.filed&&r.filed<=asOf&&r.end<=asOf)))
  return failure('Faltan los componentes contables para auditar el puente');
 for(let i=0;i<records.length;i++){
  const c=components[i],r=records[i];
  const reconstructed=c.length===1?c[0].val:c[0].val+c[1].val-c[2].val;
  if(!['TTM','FY'].includes(r.method)||(r.method==='FY'&&c.length!==1)||
    c.map(x=>x.end).sort().at(-1)!==r.period_end||
    c.map(x=>x.filed).sort().at(-1)!==r.filed||
    Math.abs(reconstructed-r.value)>1e-8*Math.max(1,Math.abs(r.value)))
   return failure('Los componentes no reconstruyen el BPA declarado');
 }
 const periods=components.map(c=>c.map(r=>r.start+'/'+r.end).sort().join('|'));
 if(!periods.every(p=>p===periods[0]))
  return failure('La reconstrucción de los tres BPA usa intervalos distintos');
 const earliest=components.flat().map(r=>r.end).sort()[0];
 const crossesSplit=(asset.splits||[]).some(s=>s.date>earliest&&s.date<=asOf&&s.ratio!==1);
 if(crossesSplit){
  const accessions=new Set(components.flat().map(r=>r.accn));
  if(accessions.has(undefined)||accessions.size!==1)
   return failure('La base por acción no está reconciliada alrededor de un split');
 }
 const residual=reported-continuing-discontinued;
 const tolerance=Math.min(.05,Math.max(.005,Math.abs(reported)*.005));
 if(Math.abs(residual)>tolerance+1e-9)
  return {...failure('BPA total distinto de continuado más discontinuado'),residual,tolerance};
 return {available:true,reported,continuing,discontinued,residual,tolerance,
  period:records[0].period_end,method:records[0].method,
  filed:records.map(r=>r.filed).sort().at(-1),
  adjustment:continuing-reported,evidence:records,
  reason:'BPA total conciliado con operaciones continuadas y discontinuadas; no normaliza el ciclo ni otros extraordinarios'};
}
