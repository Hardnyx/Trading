import { studentMarginal } from './conditional-risk.mjs?v=0.30.0';

const ORDER=25, LIMIT=8.5, STEP=.0025, projections=new Map();

function marginalProjection(nu){
  if(!nu){const coefficients=Array(ORDER+1).fill(0);coefficients[1]=1;
    return {coefficients,variance:1,remainder:0};}
  const key=nu.toFixed(6);
  if(projections.has(key))return projections.get(key);
  const law=studentMarginal(nu),coefficients=Array(ORDER+1).fill(0);
  let variance=0;
  const intervals=Math.round(LIMIT/STEP);
  // Simpson integration splits each linear quantile-table segment in half.
  // Odd functions need only the positive half of the Gaussian integral.
  for(let j=1;j<=intervals;j++){
    const z=j*STEP,g=law(z),weight=(j===intervals?1:j%2?4:2)*STEP/3*
      2*Math.exp(-z*z/2)/Math.sqrt(2*Math.PI);
    variance+=weight*g*g;
    let previous=1,current=z;
    coefficients[1]+=weight*g*current;
    for(let k=2;k<=ORDER;k++){
      const next=(z*current-Math.sqrt(k-1)*previous)/Math.sqrt(k);
      if(k%2)coefficients[k]+=weight*g*next;
      previous=current;current=next;
    }
  }
  const projected=coefficients.reduce((s,c)=>s+c*c,0);
  if(projected>variance){const scale=Math.sqrt(variance/projected);
    coefficients.forEach((c,k)=>{coefficients[k]=c*scale;});}
  const result={coefficients,variance,remainder:Math.max(0,variance-projected)};
  projections.set(key,result);return result;
}

/**
 * Approximate linear innovation covariance AFTER the marginal transforms.
 * Mehler/Hermite expansion: E[H_k(Z_i)H_l(Z_j)] = delta_kl rho_ij^k.
 * Each retained Hadamard power is PSD. The unrepresented variance is kept
 * on the diagonal, so this is a PSD approximation, not a latent-correlation
 * recalibration or empirical validation. Units match the input covariance.
 * Reference: https://arxiv.org/abs/1608.00738
 */
export function copulaInnovationCovariance(latent,fits=[]){
  if(!fits.some(f=>f?.nu))return {covariance:latent,maxCorrelationShift:0,
    projectionRemainderMaximum:0,method:'Gaussian-linear-innovation-covariance'};
  const rows=latent.map((_,i)=>marginalProjection(fits[i]?.nu));
  let maxCorrelationShift=0;
  const covariance=latent.map((row,i)=>row.map((value,j)=>{
    if(i===j)return value*rows[i].variance;
    const scale=Math.sqrt(Math.max(0,latent[i][i]*latent[j][j]));
    if(!scale)return 0;
    const rho=Math.max(-1,Math.min(1,value/scale));
    let moment=0;
    for(let k=1;k<=ORDER;k+=2)
      moment+=rows[i].coefficients[k]*rows[j].coefficients[k]*rho**k;
    const implied=moment/Math.sqrt(rows[i].variance*rows[j].variance);
    maxCorrelationShift=Math.max(maxCorrelationShift,Math.abs(implied-rho));
    return scale*moment;
  }));
  return {covariance,maxCorrelationShift,
    projectionRemainderMaximum:Math.max(...rows.map(r=>r.remainder)),
    method:'Hermite-25-initial-innovation-covariance',
    note:'Covarianza lineal inicial inducida por las marginales; aproximación numérica PSD, no covarianza constante de todo el horizonte ni validación de dependencia extrema.'};
}
